use serde::Serialize;

#[derive(Debug, Clone, Serialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum HazardType {
    /// Rapid downward altitude rate — cliff or sudden drop ahead.
    CliffEdge,
    /// Robot levelled out after a sharp descent — depression, high SAR priority.
    RavineBottom,
    /// Sustained lateral gravity component — steep slope, unstable footing.
    SteepSlope,
    /// Rapid upward altitude rate — wall, boulder, or sudden rise.
    Obstacle,
}

#[derive(Debug, Clone, Serialize)]
pub struct DangerAlert {
    pub hazard:        HazardType,
    pub world_x:       f64,
    pub world_y:       f64,
    pub elevation:     f64,
    pub altitude_rate: f64,  // m/s — negative = descending
    pub description:   String,
}

// Thresholds — calibrated for 10 Hz IMU with quadratic vel integration
const CLIFF_FALL_RATE:    f64 = -0.50;   // m/s downward
const OBSTACLE_RISE_RATE: f64 =  0.50;   // m/s upward
const STEEP_G_FRAC:       f64 =  0.30;   // lateral accel > 0.30 g ≈ 17° slope
const RAVINE_ALT_MIN:     f64 = -0.30;   // must have been descending at this rate
const RAVINE_RECOVERY:    f64 =  0.08;   // improvement in alt_rate to call bottom
const HAZARD_RADIUS_M:    f64 =  5.0;    // influence radius for path-planner penalty

pub struct HazardDetector {
    pub alerts:    Vec<DangerAlert>,
    prev_alt_rate: f64,
}

impl Default for HazardDetector {
    fn default() -> Self { Self::new() }
}

impl HazardDetector {
    pub fn new() -> Self {
        Self { alerts: Vec::new(), prev_alt_rate: 0.0 }
    }

    /// Call on every IMU update with current dead-reckoning state.
    pub fn check(
        &mut self,
        pos_x:         f64,
        pos_y:         f64,
        altitude:      f64,
        altitude_rate: f64,
        lateral_g:     f64,  // horizontal accel magnitude (m/s²) — slope proxy
    ) {
        let prev = self.prev_alt_rate;
        self.prev_alt_rate = altitude_rate;

        if altitude_rate < CLIFF_FALL_RATE {
            self.push(DangerAlert {
                hazard:        HazardType::CliffEdge,
                world_x:       pos_x,
                world_y:       pos_y,
                elevation:     altitude,
                altitude_rate,
                description:   format!("Cliff/drop: {:.2} m/s descent", altitude_rate),
            });
        } else if altitude_rate > OBSTACLE_RISE_RATE {
            self.push(DangerAlert {
                hazard:        HazardType::Obstacle,
                world_x:       pos_x,
                world_y:       pos_y,
                elevation:     altitude,
                altitude_rate,
                description:   format!("Wall/rise: {:.2} m/s ascent", altitude_rate),
            });
        } else if prev < RAVINE_ALT_MIN && altitude_rate - prev > RAVINE_RECOVERY {
            // Was descending fast, now levelling — ravine bottom
            self.push(DangerAlert {
                hazard:        HazardType::RavineBottom,
                world_x:       pos_x,
                world_y:       pos_y,
                elevation:     altitude,
                altitude_rate,
                description:   "Ravine/depression — elevated SAR priority".to_string(),
            });
        } else if lateral_g > STEEP_G_FRAC * 9.81 {
            self.push(DangerAlert {
                hazard:        HazardType::SteepSlope,
                world_x:       pos_x,
                world_y:       pos_y,
                elevation:     altitude,
                altitude_rate,
                description:   format!("Steep slope: lateral {:.2} m/s²", lateral_g),
            });
        }
    }

    fn push(&mut self, alert: DangerAlert) {
        // Deduplicate: drop stale alert of same type within 2 m
        self.alerts.retain(|a| {
            !(a.hazard == alert.hazard
                && (a.world_x - alert.world_x).abs() < 2.0
                && (a.world_y - alert.world_y).abs() < 2.0)
        });
        if self.alerts.len() >= 20 {
            self.alerts.remove(0);
        }
        log::warn!("[HAZARD] {} @ ({:.1},{:.1}) elev={:.2}m",
            alert.description, alert.world_x, alert.world_y, alert.elevation);
        self.alerts.push(alert);
    }

    /// Passability weight for path planner: 0.05–1.0.
    /// Lower means worse to route through; fades linearly over HAZARD_RADIUS_M.
    pub fn terrain_weight(&self, world_x: f64, world_y: f64) -> f64 {
        let mut weight = 1.0_f64;
        for a in &self.alerts {
            let d = ((a.world_x - world_x).powi(2) + (a.world_y - world_y).powi(2)).sqrt();
            if d >= HAZARD_RADIUS_M { continue; }
            let cell_w = match a.hazard {
                HazardType::CliffEdge    => 0.05,
                HazardType::Obstacle     => 0.10,
                HazardType::SteepSlope   => 0.25,
                HazardType::RavineBottom => 0.80,  // passable, but flag for SAR
            };
            let fade = 1.0 - d / HAZARD_RADIUS_M;
            weight = weight.min(1.0 - (1.0 - cell_w) * fade);
        }
        weight.max(0.05)
    }

    /// SAR priority multiplier for waypoint scoring.
    /// Ravine bottoms get a boost — subjects fall into depressions and shelter there.
    pub fn sar_priority(&self, world_x: f64, world_y: f64) -> f64 {
        let mut boost = 1.0_f64;
        for a in &self.alerts {
            if a.hazard != HazardType::RavineBottom { continue; }
            let d = ((a.world_x - world_x).powi(2) + (a.world_y - world_y).powi(2)).sqrt();
            if d < 6.0 {
                boost = boost.max(1.5 - d * 0.08);
            }
        }
        boost
    }
}
