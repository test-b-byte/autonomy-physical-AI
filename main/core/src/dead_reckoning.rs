/// GPS-free position estimate via IMU integration.
/// Uses gyro-integrated heading + trapezoidal velocity/position integration.
/// Zero-velocity detection from accelerometer magnitude damps drift when
/// the robot is stationary.
#[derive(Debug, Clone)]
pub struct DeadReckoning {
    pub pos_x:         f64,    // metres from origin
    pub pos_y:         f64,
    pub vel_x:         f64,    // m/s
    pub vel_y:         f64,
    pub heading:       f64,    // radians, 0 = +x axis, CCW positive
    pub altitude:      f64,    // metres, integrated from az
    pub altitude_rate: f64,    // m/s — positive = rising
    pub lateral_g:     f64,    // horizontal accel magnitude (m/s²) — slope proxy
    alt_vel:           f64,
}

impl DeadReckoning {
    pub fn new(start_x: f64, start_y: f64) -> Self {
        Self {
            pos_x: start_x, pos_y: start_y,
            vel_x: 0.0, vel_y: 0.0,
            heading: 0.0,
            altitude: 0.0, altitude_rate: 0.0, lateral_g: 0.0,
            alt_vel: 0.0,
        }
    }

    /// Process one IMU sample.
    ///
    /// ax, ay : body-frame horizontal acceleration (m/s², gravity removed)
    /// az     : body-frame vertical acceleration (m/s², ~9.81 when flat+stationary)
    /// gz     : yaw rate (rad/s, +CCW)
    /// dt     : sample interval (s)
    pub fn update(&mut self, ax: f64, ay: f64, az: f64, gz: f64, dt: f64) {
        self.heading = (self.heading + gz * dt).rem_euclid(std::f64::consts::TAU);

        let (sh, ch) = self.heading.sin_cos();
        let world_ax = ch * ax - sh * ay;
        let world_ay = sh * ax + ch * ay;

        let mag   = (ax * ax + ay * ay).sqrt();
        let decay = if mag < 0.08 { 0.80 } else { 1.0 };

        self.vel_x     = self.vel_x * decay + world_ax * dt;
        self.vel_y     = self.vel_y * decay + world_ay * dt;
        self.pos_x    += self.vel_x * dt;
        self.pos_y    += self.vel_y * dt;
        self.lateral_g = mag;

        // Vertical: net accel = az − 9.81 (removes gravity component).
        // Cliff: reaction force drops → az < 9.81 → altitude falls.
        // Impact: az spikes > 9.81 → altitude rises briefly.
        let vert_net   = az - 9.81;
        let alt_damp   = if vert_net.abs() < 0.15 { 0.85 } else { 1.0 };
        self.alt_vel       = self.alt_vel * alt_damp + vert_net * dt;
        self.altitude     += self.alt_vel * dt;
        self.altitude_rate = self.alt_vel;
    }

    /// Hard-set position (used by sim / external fix).
    pub fn teleport(&mut self, x: f64, y: f64) {
        self.pos_x = x;
        self.pos_y = y;
        self.vel_x = 0.0;
        self.vel_y = 0.0;
    }

    /// Convert world position to grid cell, clamped to map bounds.
    pub fn grid_cell(&self, cell_size_m: f64, width: usize, height: usize) -> (usize, usize) {
        let cx = (self.pos_x / cell_size_m).max(0.0) as usize;
        let cy = (self.pos_y / cell_size_m).max(0.0) as usize;
        (cx.min(width.saturating_sub(1)), cy.min(height.saturating_sub(1)))
    }
}
