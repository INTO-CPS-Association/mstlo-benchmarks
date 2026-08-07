use rand::{RngExt, SeedableRng};
use rand_chacha::ChaCha8Rng;
use rand_distr::StandardNormal;

const STARTS: [(f64, f64); 4] = [(-3.54, -5.35), (-3.60, 3.28), (1.50, 3.65), (3.78, -5.83)];

#[derive(Clone, Copy)]
pub struct Position {
    pub x: f64,
    pub y: f64,
}

pub struct Simulation {
    rng: ChaCha8Rng,
    positions: Vec<Position>,
    steps_per_publish: usize,
    dt: f64,
}

impl Simulation {
    pub fn new(robots: usize, seed: u64, sim_hz: f64, publish_rate_hz: f64) -> Self {
        let mut rng = ChaCha8Rng::seed_from_u64(seed);
        let positions = (0..robots)
            .map(|robot| {
                let (x, y) = STARTS.get(robot).copied().unwrap_or_else(|| {
                    (
                        rng.random_range(-8.88..8.38),
                        rng.random_range(-10.88..7.88),
                    )
                });
                Position { x, y }
            })
            .collect();
        Self {
            rng,
            positions,
            steps_per_publish: (sim_hz / publish_rate_hz).round().max(1.0) as usize,
            dt: 1.0 / sim_hz,
        }
    }

    pub fn next_sample(&mut self) -> &[Position] {
        for _ in 0..self.steps_per_publish {
            self.advance();
        }
        &self.positions
    }

    fn advance(&mut self) {
        let sigma = 1.25 * self.dt.sqrt();
        for position in &mut self.positions {
            let dx: f64 = self.rng.sample(StandardNormal);
            let dy: f64 = self.rng.sample(StandardNormal);
            let drift_x = wall_drift(position.x, -8.88, 8.38) * self.dt;
            let drift_y = wall_drift(position.y, -10.88, 7.88) * self.dt;
            position.x = (position.x + dx * sigma + drift_x).clamp(-8.88, 8.38);
            position.y = (position.y + dy * sigma + drift_y).clamp(-10.88, 7.88);
        }
    }
}

fn wall_drift(value: f64, min: f64, max: f64) -> f64 {
    let from_min = value - min;
    let from_max = max - value;
    if from_min < 1.5 {
        2.5 * (1.0 - from_min / 1.5).clamp(0.0, 1.0)
    } else if from_max < 1.5 {
        -2.5 * (1.0 - from_max / 1.5).clamp(0.0, 1.0)
    } else {
        0.0
    }
}
