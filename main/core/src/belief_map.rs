/// 2-D probability grid over the search area.
/// Each cell holds P(subject | cell), maintained in log-space
/// internally but exposed as linear probabilities.
#[derive(Debug, Clone)]
pub struct BeliefMap {
    pub width:       usize,
    pub height:      usize,
    pub cell_size_m: f64,
    cells: Vec<f64>,      // row-major: index = y * width + x
    pub swept: Vec<bool>,
}

impl BeliefMap {
    pub fn new(width: usize, height: usize, cell_size_m: f64) -> Self {
        let n = width * height;
        let uniform = 1.0 / n as f64;
        Self {
            width, height, cell_size_m,
            cells: vec![uniform; n],
            swept: vec![false; n],
        }
    }

    /// Gaussian prior centred on last-known position (world metres).
    pub fn init_gaussian_prior(&mut self, lkp_x: f64, lkp_y: f64, sigma_m: f64) {
        let sigma_c = sigma_m / self.cell_size_m;
        let cx = lkp_x / self.cell_size_m;
        let cy = lkp_y / self.cell_size_m;

        let mut sum = 0.0_f64;
        for y in 0..self.height {
            for x in 0..self.width {
                let dx = x as f64 - cx;
                let dy = y as f64 - cy;
                let p = (-(dx * dx + dy * dy) / (2.0 * sigma_c * sigma_c)).exp();
                self.cells[y * self.width + x] = p;
                sum += p;
            }
        }
        self.normalize_raw(sum);
    }

    pub fn get(&self, x: usize, y: usize) -> f64 {
        self.cells[y * self.width + x]
    }

    /// Multiply every cell by its likelihood factor then renormalise.
    /// `factors` must have length `width * height`.
    pub fn update_likelihoods(&mut self, factors: &[f64]) {
        debug_assert_eq!(factors.len(), self.cells.len());
        let mut sum = 0.0_f64;
        for (c, &f) in self.cells.iter_mut().zip(factors.iter()) {
            *c *= f.max(0.0);
            sum += *c;
        }
        self.normalize_raw(sum);
    }

    pub fn mark_swept(&mut self, x: usize, y: usize) {
        self.swept[y * self.width + x] = true;
    }

    pub fn is_swept(&self, x: usize, y: usize) -> bool {
        self.swept[y * self.width + x]
    }

    /// Serialise as row-major 2-D vec for JSON / dashboard.
    pub fn as_grid(&self) -> Vec<Vec<f64>> {
        (0..self.height)
            .map(|y| (0..self.width).map(|x| self.get(x, y)).collect())
            .collect()
    }

    /// Shannon entropy of the current distribution (nats).
    pub fn entropy(&self) -> f64 {
        self.cells.iter()
            .filter(|&&p| p > 1e-15)
            .map(|&p| -p * p.ln())
            .sum()
    }

    /// Cell with highest probability; returns (x, y, probability).
    pub fn peak(&self) -> (usize, usize, f64) {
        let (idx, &p) = self.cells.iter().enumerate()
            .max_by(|(_, a), (_, b)| a.partial_cmp(b).unwrap())
            .unwrap();
        (idx % self.width, idx / self.width, p)
    }

    fn normalize_raw(&mut self, sum: f64) {
        if sum > 1e-15 {
            for c in self.cells.iter_mut() { *c /= sum; }
        } else {
            let u = 1.0 / self.cells.len() as f64;
            for c in self.cells.iter_mut() { *c = u; }
        }
    }
}
