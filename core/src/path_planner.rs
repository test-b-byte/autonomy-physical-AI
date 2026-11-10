use crate::{belief_map::BeliefMap, sensor_model::SensorSpec};

pub struct PathPlanner;

impl PathPlanner {
    /// Next cell to visit: maximises P(c) × hazard_weight(c) × sar_boost(c)
    /// / (1 + 0.08 × manhattan_dist).  Skips already-swept cells.
    ///
    /// `hazard_weights` and `sar_boosts` are row-major slices (y*width+x).
    /// Pass empty slices when no hazard data is available.
    pub fn next_waypoint(
        map:            &BeliefMap,
        robot_cell:     (usize, usize),
        hazard_weights: &[f64],
        sar_boosts:     &[f64],
    ) -> Option<(usize, usize)> {
        let (rx, ry) = robot_cell;
        let mut best   = f64::NEG_INFINITY;
        let mut target = None;

        for y in 0..map.height {
            for x in 0..map.width {
                if map.is_swept(x, y) { continue; }
                let p = map.get(x, y);
                if p < 1e-15 { continue; }

                let idx = y * map.width + x;
                let hw  = hazard_weights.get(idx).copied().unwrap_or(1.0);
                let sb  = sar_boosts.get(idx).copied().unwrap_or(1.0);

                let dist = ((x as isize - rx as isize).unsigned_abs()
                    + (y as isize - ry as isize).unsigned_abs()) as f64;
                let score = p * hw * sb / (1.0 + 0.08 * dist);

                if score > best {
                    best   = score;
                    target = Some((x, y));
                }
            }
        }
        target
    }

    /// Per-cell likelihood-ratio factors for one sensor sweep.
    ///
    /// For each cell c:
    ///   factor(c) = LR_positive(dist)  if detection == true
    ///             = LR_negative(dist)  if detection == false
    ///
    /// `confidence` ∈ [0,1] blends the LR toward 1.0 (no information) for
    /// low-confidence readings (partial occlusion, sensor uncertainty).
    pub fn likelihood_factors(
        map:        &BeliefMap,
        robot_cell: (usize, usize),
        spec:       &SensorSpec,
        detection:  bool,
        confidence: f64,
    ) -> Vec<f64> {
        let (rx, ry) = robot_cell;
        let cell_m   = map.cell_size_m;
        let conf     = confidence.clamp(0.0, 1.0);

        (0..map.height)
            .flat_map(|y| {
                (0..map.width).map(move |x| {
                    let dx   = (x as f64 - rx as f64) * cell_m;
                    let dy   = (y as f64 - ry as f64) * cell_m;
                    let dist = (dx * dx + dy * dy).sqrt();
                    let raw  = if detection {
                        spec.lr_positive(dist)
                    } else {
                        spec.lr_negative(dist)
                    };
                    1.0 + conf * (raw - 1.0)
                })
            })
            .collect()
    }
}
