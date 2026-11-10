use std::collections::HashMap;
use serde::{Deserialize, Serialize};
use crate::{
    belief_map::BeliefMap,
    dead_reckoning::DeadReckoning,
    hazard::{DangerAlert, HazardDetector},
    path_planner::PathPlanner,
    sensor_model::{SensorSpec, SensorType},
};

// ── Wire protocol ────────────────────────────────────────────────────────────

/// Mission lifecycle.  The operator starts the search (GO) and can halt it.
/// Waypoints are only planned, and subject-sensor readings only counted,
/// while `Active` — so a halted robot gets no goals from anyone.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum MissionState {
    /// Configured (or reset), waiting for GO.
    Idle,
    /// Searching.
    Active,
    /// Operator HALT — hold position.
    Halted,
    /// Driving back to the launch point.
    Returning,
    /// Contact declared — search over.
    Complete,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Action {
    /// GO: start the search.
    Start,
    Halt,
    Resume,
    ReturnHome,
    /// New search with the same configuration (fresh belief, back to Idle).
    Abort,
}

#[derive(Debug, Deserialize)]
#[serde(tag = "type", rename_all = "lowercase")]
pub enum IncomingMsg {
    /// (Re)configure the grid and optionally override per-sensor specs.
    /// Any omitted sensor falls back to its built-in default.
    Config {
        width:         usize,
        height:        usize,
        cell_size_m:   f64,
        last_known_x:  f64,
        last_known_y:  f64,
        prior_sigma_m: Option<f64>,
        sensor_specs:  Option<HashMap<SensorType, SensorSpec>>,
    },
    /// Mission command from the operator (dashboard GO/HALT…, or radio).
    Command { action: Action },
    /// One sensor reading from the current robot position.
    Sensor {
        sensor_type: SensorType,
        detection:   bool,
        confidence:  f64,
    },
    /// Raw IMU sample.
    Imu {
        ax: f64,
        ay: f64,
        az: f64,   // vertical accel (m/s²) — ~9.81 when flat+stationary
        gz: f64,
        dt: f64,
    },
    /// Directly set robot world position (simulation / GPS fix).
    Teleport { x: f64, y: f64 },
    /// Return current state without modifying it.
    Query,
    /// Hard reset to default engine state.
    Reset,
}

// ── Output types ─────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize)]
pub struct Contact {
    pub cell_x:            usize,
    pub cell_y:            usize,
    pub world_x:           f64,
    pub world_y:           f64,
    pub probability:       f64,
    pub sensors:           Vec<String>,
    pub combined_confidence: f64,
}

#[derive(Debug, Serialize)]
pub struct StateSnapshot {
    pub mission:         MissionState,
    /// Bumps on every (re)configuration so clients can tell searches apart.
    pub mission_id:      u32,
    pub cell_size_m:     f64,
    pub grid:            Vec<Vec<f64>>,
    pub robot_x:         f64,
    pub robot_y:         f64,
    pub robot_cell:      [usize; 2],
    pub next_waypoint:   Option<[usize; 2]>,
    pub entropy:         f64,
    pub max_probability: f64,
    pub sweep_count:     usize,
    pub contact:         Option<Contact>,
    pub elevation:       f64,
    pub hazard_alerts:   Vec<DangerAlert>,
}

// ── Engine ───────────────────────────────────────────────────────────────────

const CONTACT_THRESHOLD: f64 = 0.20;

pub struct GhostEngine {
    pub map:         BeliefMap,
    pub dr:          DeadReckoning,
    pub hazard:      HazardDetector,
    pub sweep_count: usize,
    pub contact:     Option<Contact>,
    /// Per-sensor spec overrides; falls back to SensorType::default_spec().
    specs:   HashMap<SensorType, SensorSpec>,
    /// Accumulates sensor triggers between position changes for contact fusion.
    pending: Vec<(SensorType, f64)>,
    pub mission:    MissionState,
    pub mission_id: u32,
    /// Last configuration, so Abort can start a fresh search on the same grid.
    last_config: Option<MissionConfig>,
}

#[derive(Debug, Clone)]
struct MissionConfig {
    width: usize,
    height: usize,
    cell_size_m: f64,
    last_known_x: f64,
    last_known_y: f64,
    prior_sigma_m: Option<f64>,
    sensor_specs: Option<HashMap<SensorType, SensorSpec>>,
}

impl Default for GhostEngine {
    fn default() -> Self { Self::new() }
}

impl GhostEngine {
    pub fn new() -> Self {
        Self {
            map:         BeliefMap::new(20, 20, 2.0),
            dr:          DeadReckoning::new(0.0, 0.0),
            hazard:      HazardDetector::new(),
            sweep_count: 0,
            contact:     None,
            specs:       HashMap::new(),
            pending:     Vec::new(),
            mission:     MissionState::Idle,
            mission_id:  0,
            last_config: None,
        }
    }

    fn configure(&mut self, c: MissionConfig) {
        self.map = BeliefMap::new(c.width, c.height, c.cell_size_m);
        self.map.init_gaussian_prior(
            c.last_known_x, c.last_known_y, c.prior_sigma_m.unwrap_or(15.0));
        let pos = (self.dr.pos_x, self.dr.pos_y);   // keep the odometry-fed pose
        self.dr           = DeadReckoning::new(pos.0, pos.1);
        self.hazard       = HazardDetector::new();
        self.sweep_count  = 0;
        self.contact      = None;
        self.specs        = c.sensor_specs.clone().unwrap_or_default();
        self.pending.clear();
        self.mission      = MissionState::Idle;
        self.mission_id  += 1;
        log::info!("mission #{} configured: {}×{} @ {}m/cell, LKP=({},{}) — waiting for GO",
            self.mission_id, c.width, c.height, c.cell_size_m, c.last_known_x, c.last_known_y);
        self.last_config  = Some(c);
    }

    fn command(&mut self, action: Action) {
        use MissionState::*;
        if action == Action::Abort {
            match self.last_config.clone() {
                Some(c) => self.configure(c),
                None => self.mission = Idle,
            }
            return;
        }
        let next = match (action, self.mission) {
            (Action::Start,      Idle)               => Active,
            (Action::Halt,       Active | Returning)  => Halted,
            (Action::Resume,     Halted | Returning)  => Active,
            (Action::ReturnHome, Active | Halted)    => Returning,
            (a, s) => {
                log::warn!("command {a:?} ignored while {s:?}");
                return;
            }
        };
        log::info!("mission #{}: {:?} → {:?}", self.mission_id, self.mission, next);
        self.mission = next;
    }

    pub fn handle(&mut self, msg: IncomingMsg) {
        match msg {
            IncomingMsg::Config {
                width, height, cell_size_m,
                last_known_x, last_known_y,
                prior_sigma_m, sensor_specs,
            } => self.configure(MissionConfig {
                width, height, cell_size_m, last_known_x, last_known_y,
                prior_sigma_m, sensor_specs,
            }),

            IncomingMsg::Command { action } => self.command(action),

            IncomingMsg::Imu { ax, ay, az, gz, dt } => {
                self.dr.update(ax, ay, az, gz, dt);
                self.hazard.check(
                    self.dr.pos_x, self.dr.pos_y,
                    self.dr.altitude, self.dr.altitude_rate, self.dr.lateral_g,
                );
            }

            IncomingMsg::Teleport { x, y } => {
                self.dr.teleport(x, y);
                log::debug!("teleport → ({x:.1}, {y:.1})");
            }

            // Subject sensors only count while searching: readings before GO
            // (people around the launch point) or while halted would plant
            // false peaks.
            IncomingMsg::Sensor { .. } if self.mission != MissionState::Active => {}

            IncomingMsg::Sensor { sensor_type, detection, confidence } => {
                let cell = self.dr.grid_cell(
                    self.map.cell_size_m, self.map.width, self.map.height,
                );
                // Resolve spec: per-engine override → built-in default
                let spec = self.specs
                    .get(&sensor_type)
                    .cloned()
                    .unwrap_or_else(|| sensor_type.default_spec());

                let factors = PathPlanner::likelihood_factors(
                    &self.map, cell, &spec, detection, confidence,
                );
                self.map.update_likelihoods(&factors);
                self.map.mark_swept(cell.0, cell.1);
                self.sweep_count += 1;

                if detection {
                    self.pending.push((sensor_type, confidence));
                }
                self.check_contact();

                log::debug!(
                    "sweep #{} cell({},{}) detection={} → entropy={:.3}",
                    self.sweep_count, cell.0, cell.1, detection,
                    self.map.entropy()
                );
            }

            IncomingMsg::Query | IncomingMsg::Reset => {
                if matches!(msg, IncomingMsg::Reset) {
                    let id = self.mission_id;
                    *self = GhostEngine::new();
                    self.mission_id = id + 1;
                }
            }
        }
    }

    pub fn snapshot(&self) -> StateSnapshot {
        let cell = self.dr.grid_cell(
            self.map.cell_size_m, self.map.width, self.map.height,
        );

        let n = self.map.width * self.map.height;
        let mut hazard_weights = Vec::with_capacity(n);
        let mut sar_boosts     = Vec::with_capacity(n);
        for i in 0..n {
            let wx = (i % self.map.width) as f64 * self.map.cell_size_m;
            let wy = (i / self.map.width) as f64 * self.map.cell_size_m;
            hazard_weights.push(self.hazard.terrain_weight(wx, wy));
            sar_boosts.push(self.hazard.sar_priority(wx, wy));
        }

        // Goals only while searching: HALT / RTB / complete / idle stop navigation.
        let wp = if self.mission == MissionState::Active {
            PathPlanner::next_waypoint(&self.map, cell, &hazard_weights, &sar_boosts)
        } else {
            None
        };
        let (_, _, max_p) = self.map.peak();

        StateSnapshot {
            mission:         self.mission,
            mission_id:      self.mission_id,
            cell_size_m:     self.map.cell_size_m,
            grid:            self.map.as_grid(),
            robot_x:         self.dr.pos_x,
            robot_y:         self.dr.pos_y,
            robot_cell:      [cell.0, cell.1],
            next_waypoint:   wp.map(|(x, y)| [x, y]),
            entropy:         self.map.entropy(),
            max_probability: max_p,
            sweep_count:     self.sweep_count,
            contact:         self.contact.clone(),
            elevation:       self.dr.altitude,
            hazard_alerts:   self.hazard.alerts.clone(),
        }
    }

    // ── private ──────────────────────────────────────────────────────────────

    fn check_contact(&mut self) {
        if self.contact.is_some() { return; }

        let (px, py, p) = self.map.peak();
        if p < CONTACT_THRESHOLD { return; }

        let combined = if self.pending.is_empty() {
            p
        } else {
            1.0 - self.pending.iter().map(|(_, c)| 1.0 - c).product::<f64>()
        };

        let sensors: Vec<String> = self.pending.iter()
            .map(|(s, _)| s.to_string())
            .collect();

        log::warn!(
            "CONTACT declared at cell({},{}) p={:.3} conf={:.3} sensors={:?}",
            px, py, p, combined, sensors
        );

        self.mission = MissionState::Complete;
        self.contact = Some(Contact {
            cell_x: px, cell_y: py,
            world_x: px as f64 * self.map.cell_size_m,
            world_y: py as f64 * self.map.cell_size_m,
            probability: p,
            combined_confidence: combined,
            sensors,
        });
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn configured() -> GhostEngine {
        let mut e = GhostEngine::new();
        e.handle(serde_json::from_str(r#"{"type":"config","width":10,"height":10,
            "cell_size_m":0.5,"last_known_x":2.5,"last_known_y":2.5,"prior_sigma_m":1.5}"#).unwrap());
        e
    }

    fn cmd(e: &mut GhostEngine, json_action: &str) {
        e.handle(serde_json::from_str(&format!(r#"{{"type":"command","action":"{json_action}"}}"#)).unwrap());
    }

    #[test]
    fn waits_for_go() {
        let mut e = configured();
        assert_eq!(e.mission, MissionState::Idle);
        assert!(e.snapshot().next_waypoint.is_none(), "no goals before GO");
        e.handle(IncomingMsg::Sensor { sensor_type: SensorType::Ir, detection: true, confidence: 0.9 });
        assert_eq!(e.sweep_count, 0, "readings before GO are ignored");
        cmd(&mut e, "start");
        assert_eq!(e.mission, MissionState::Active);
        assert!(e.snapshot().next_waypoint.is_some());
    }

    #[test]
    fn halt_stops_goals_and_resume_restores() {
        let mut e = configured();
        cmd(&mut e, "start");
        cmd(&mut e, "halt");
        assert_eq!(e.mission, MissionState::Halted);
        assert!(e.snapshot().next_waypoint.is_none());
        cmd(&mut e, "start");                       // GO doesn't un-halt: RESUME does
        assert_eq!(e.mission, MissionState::Halted);
        cmd(&mut e, "resume");
        assert_eq!(e.mission, MissionState::Active);
        cmd(&mut e, "return_home");
        assert_eq!(e.mission, MissionState::Returning);
        assert!(e.snapshot().next_waypoint.is_none());
        cmd(&mut e, "halt");
        assert_eq!(e.mission, MissionState::Halted);
    }

    #[test]
    fn abort_starts_fresh_on_same_grid() {
        let mut e = configured();
        cmd(&mut e, "start");
        e.handle(IncomingMsg::Sensor { sensor_type: SensorType::Ir, detection: false, confidence: 0.9 });
        assert_eq!(e.sweep_count, 1);
        cmd(&mut e, "abort");
        assert_eq!(e.mission, MissionState::Idle);
        assert_eq!(e.sweep_count, 0);
        assert_eq!(e.mission_id, 2);
        assert_eq!(e.snapshot().cell_size_m, 0.5);
    }

    #[test]
    fn contact_completes() {
        let mut e = configured();
        cmd(&mut e, "start");
        e.handle(IncomingMsg::Teleport { x: 2.5, y: 2.5 });
        for _ in 0..20 {
            e.handle(IncomingMsg::Sensor { sensor_type: SensorType::Ir, detection: true, confidence: 0.95 });
        }
        assert!(e.contact.is_some());
        assert_eq!(e.mission, MissionState::Complete);
        assert!(e.snapshot().next_waypoint.is_none());
    }
}
