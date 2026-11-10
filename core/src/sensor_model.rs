use std::fmt;
use serde::{Deserialize, Serialize};

/// Detection physics — the three numbers that fully describe a sensor's
/// capability.  Public and serializable so specs can be overridden from
/// config at runtime (no recompile needed to tune for a new platform).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SensorSpec {
    pub max_range_m: f64,  // beyond this distance: Pd = 0
    pub peak_pd:     f64,  // P(detect | subject at 0 m)
    pub pfa:         f64,  // P(detect | no subject) — false-alarm rate
}

impl SensorSpec {
    /// P(detect | subject present) at distance d — quadratic falloff.
    pub fn pd(&self, dist_m: f64) -> f64 {
        if dist_m >= self.max_range_m { return 0.0; }
        let t = dist_m / self.max_range_m;
        self.peak_pd * (1.0 - t * t)
    }

    /// Likelihood ratio for a positive detection.
    pub fn lr_positive(&self, dist_m: f64) -> f64 {
        if dist_m >= self.max_range_m { return 1.0; }
        self.pd(dist_m) / self.pfa
    }

    /// Likelihood ratio for a negative (no-detection) report.
    pub fn lr_negative(&self, dist_m: f64) -> f64 {
        if dist_m >= self.max_range_m { return 1.0; }
        (1.0 - self.pd(dist_m)) / (1.0 - self.pfa)
    }
}

/// Sensor identity — matches the JSON wire-protocol `sensor_type` tag.
/// Derive Hash + Eq so it can serve as a HashMap key (for per-sensor spec
/// overrides stored in GhostEngine).
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum SensorType {
    Thermal,
    Ir,
    Acoustic,
    Vision,
}

impl SensorType {
    /// Built-in defaults.  Override at runtime via Config { sensor_specs }.
    pub fn default_spec(&self) -> SensorSpec {
        match self {
            Self::Thermal  => SensorSpec { max_range_m: 10.0, peak_pd: 0.90, pfa: 0.05 },
            Self::Ir       => SensorSpec { max_range_m:  3.0, peak_pd: 0.95, pfa: 0.02 },
            Self::Acoustic => SensorSpec { max_range_m: 20.0, peak_pd: 0.75, pfa: 0.08 },
            Self::Vision   => SensorSpec { max_range_m: 15.0, peak_pd: 0.85, pfa: 0.03 },
        }
    }
}

impl fmt::Display for SensorType {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(match self {
            Self::Thermal  => "thermal",
            Self::Ir       => "ir",
            Self::Acoustic => "acoustic",
            Self::Vision   => "vision",
        })
    }
}
