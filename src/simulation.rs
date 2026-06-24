use bevy::prelude::*;
use rand::{RngExt, SeedableRng};
use rand_chacha::ChaCha8Rng;
use rand_distr::StandardNormal;

use crate::{
    config::Args,
    robot::{Robot, RobotLabel, RobotPose},
};

#[derive(Clone, Debug, Resource)]
pub struct SimulationConfig {
    pub robots: usize,
    pub seed: u64,
    pub arena_width: f32,
    pub arena_height: f32,
    pub brownian_scale: f32,
    pub sim_hz: f32,
    pub publish_rate_hz: f32,
    pub robot_radius: f32,
    pub robot_labels: bool,
    pub wall_avoidance_margin: f32,
    pub wall_avoidance_strength: f32,
    pub render_scale: f32,
}

impl From<Args> for SimulationConfig {
    fn from(args: Args) -> Self {
        Self {
            robots: args.robots,
            seed: args.seed,
            arena_width: args.arena_width,
            arena_height: args.arena_height,
            brownian_scale: args.brownian_scale,
            sim_hz: args.sim_hz,
            publish_rate_hz: args.publish_rate_hz,
            robot_radius: args.robot_radius,
            robot_labels: args.robot_labels,
            wall_avoidance_margin: args.wall_avoidance_margin,
            wall_avoidance_strength: args.wall_avoidance_strength,
            render_scale: 60.0,
        }
    }
}

impl SimulationConfig {
    pub fn render_position(&self, x: f32, y: f32) -> Vec2 {
        Vec2::new(x * self.render_scale, y * self.render_scale)
    }

    pub fn render_radius(&self) -> f32 {
        self.robot_radius * self.render_scale
    }
}

#[derive(Resource)]
pub struct SimulationRng {
    rng: ChaCha8Rng,
}

impl SimulationRng {
    pub fn new(seed: u64) -> Self {
        Self {
            rng: ChaCha8Rng::seed_from_u64(seed),
        }
    }
}

pub fn spawn_robots(
    mut commands: Commands,
    config: Res<SimulationConfig>,
    mut rng: ResMut<SimulationRng>,
) {
    let half_width = config.arena_width * 0.5 - config.robot_radius;
    let half_height = config.arena_height * 0.5 - config.robot_radius;

    for id in 0..config.robots {
        let x = rng.rng.random_range(-half_width..half_width);
        let y = rng.rng.random_range(-half_height..half_height);
        let hue = (id as f32 * 0.618_034).fract() * 360.0;

        commands.spawn((
            Robot { id },
            RobotPose { x, y, theta: 0.0 },
            Sprite {
                color: Color::hsl(hue, 0.76, 0.55),
                custom_size: Some(Vec2::splat(config.render_radius() * 2.0)),
                ..default()
            },
            Transform::from_xyz(
                config.render_position(x, y).x,
                config.render_position(x, y).y,
                1.0,
            ),
        ));

        if config.robot_labels {
            commands.spawn((
                RobotLabel { robot_id: id },
                Text2d::new(id.to_string()),
                TextFont {
                    font_size: FontSize::Px(13.0),
                    ..default()
                },
                TextColor(Color::WHITE),
                Transform::from_xyz(
                    config.render_position(x, y).x + config.render_radius() + 4.0,
                    config.render_position(x, y).y + config.render_radius() + 4.0,
                    2.0,
                ),
            ));
        }
    }

    eprintln!("INFO spawned {} robot sprites", config.robots);
}

pub fn move_robots(
    config: Res<SimulationConfig>,
    mut rng: ResMut<SimulationRng>,
    mut robots: Query<(&Robot, &mut RobotPose, &mut Transform)>,
) {
    let dt = 1.0 / config.sim_hz;
    let step_sigma = config.brownian_scale * dt.sqrt();
    let half_width = config.arena_width * 0.5 - config.robot_radius;
    let half_height = config.arena_height * 0.5 - config.robot_radius;

    let mut ordered = robots.iter_mut().collect::<Vec<_>>();
    ordered.sort_by_key(|(robot, _, _)| robot.id);

    for (_, mut pose, mut transform) in ordered {
        let dx: f32 = rng.rng.sample(StandardNormal);
        let dy: f32 = rng.rng.sample(StandardNormal);
        let old_x = pose.x;
        let old_y = pose.y;
        let wall_drift = wall_avoidance_drift(
            Vec2::new(pose.x, pose.y),
            Vec2::new(half_width, half_height),
            config.wall_avoidance_margin,
            config.wall_avoidance_strength,
        ) * dt;

        pose.x = (pose.x + dx * step_sigma + wall_drift.x).clamp(-half_width, half_width);
        pose.y = (pose.y + dy * step_sigma + wall_drift.y).clamp(-half_height, half_height);
        pose.theta = (pose.y - old_y).atan2(pose.x - old_x);

        let rendered = config.render_position(pose.x, pose.y);
        transform.translation.x = rendered.x;
        transform.translation.y = rendered.y;
    }
}

fn wall_avoidance_drift(position: Vec2, half_extents: Vec2, margin: f32, strength: f32) -> Vec2 {
    Vec2::new(
        axis_wall_drift(position.x, half_extents.x, margin, strength),
        axis_wall_drift(position.y, half_extents.y, margin, strength),
    )
}

fn axis_wall_drift(position: f32, half_extent: f32, margin: f32, strength: f32) -> f32 {
    let distance_to_min = position + half_extent;
    let distance_to_max = half_extent - position;

    if distance_to_min < margin {
        strength * (1.0 - distance_to_min / margin).clamp(0.0, 1.0)
    } else if distance_to_max < margin {
        -strength * (1.0 - distance_to_max / margin).clamp(0.0, 1.0)
    } else {
        0.0
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn same_seed_replays_same_path() {
        let config = SimulationConfig {
            robots: 4,
            seed: 7,
            arena_width: 100.0,
            arena_height: 80.0,
            brownian_scale: 3.0,
            sim_hz: 20.0,
            publish_rate_hz: 5.0,
            robot_radius: 4.0,
            robot_labels: false,
            wall_avoidance_margin: 12.0,
            wall_avoidance_strength: 40.0,
            render_scale: 60.0,
        };

        let a = run_reference_sim(&config, 20);
        let b = run_reference_sim(&config, 20);

        assert_eq!(a, b);
    }

    #[test]
    fn different_seed_changes_path() {
        let mut config = SimulationConfig {
            robots: 4,
            seed: 7,
            arena_width: 100.0,
            arena_height: 80.0,
            brownian_scale: 3.0,
            sim_hz: 20.0,
            publish_rate_hz: 5.0,
            robot_radius: 4.0,
            robot_labels: false,
            wall_avoidance_margin: 12.0,
            wall_avoidance_strength: 40.0,
            render_scale: 60.0,
        };
        let a = run_reference_sim(&config, 20);
        config.seed = 8;
        let b = run_reference_sim(&config, 20);

        assert_ne!(a, b);
    }

    #[test]
    fn wall_avoidance_pushes_away_from_edges() {
        assert!(axis_wall_drift(-47.0, 50.0, 10.0, 20.0) > 0.0);
        assert!(axis_wall_drift(47.0, 50.0, 10.0, 20.0) < 0.0);
        assert_eq!(axis_wall_drift(0.0, 50.0, 10.0, 20.0), 0.0);
    }

    #[test]
    fn wall_avoidance_keeps_positions_in_arena() {
        let config = SimulationConfig {
            robots: 16,
            seed: 11,
            arena_width: 100.0,
            arena_height: 80.0,
            brownian_scale: 25.0,
            sim_hz: 20.0,
            publish_rate_hz: 5.0,
            robot_radius: 4.0,
            robot_labels: false,
            wall_avoidance_margin: 12.0,
            wall_avoidance_strength: 80.0,
            render_scale: 60.0,
        };

        let poses = run_reference_sim_f32(&config, 200);
        let half_width = config.arena_width * 0.5 - config.robot_radius;
        let half_height = config.arena_height * 0.5 - config.robot_radius;

        assert!(
            poses
                .iter()
                .all(|(x, y)| (-half_width..=half_width).contains(x)
                    && (-half_height..=half_height).contains(y))
        );
    }

    fn run_reference_sim(config: &SimulationConfig, steps: usize) -> Vec<(i32, i32)> {
        run_reference_sim_f32(config, steps)
            .into_iter()
            .map(|(x, y)| ((x * 1000.0) as i32, (y * 1000.0) as i32))
            .collect()
    }

    fn run_reference_sim_f32(config: &SimulationConfig, steps: usize) -> Vec<(f32, f32)> {
        let mut rng = ChaCha8Rng::seed_from_u64(config.seed);
        let half_width = config.arena_width * 0.5 - config.robot_radius;
        let half_height = config.arena_height * 0.5 - config.robot_radius;
        let mut poses = (0..config.robots)
            .map(|_| {
                (
                    rng.random_range(-half_width..half_width),
                    rng.random_range(-half_height..half_height),
                )
            })
            .collect::<Vec<(f32, f32)>>();

        let step_sigma = config.brownian_scale * (1.0 / config.sim_hz).sqrt();
        let dt = 1.0 / config.sim_hz;
        for _ in 0..steps {
            for pose in &mut poses {
                let dx: f32 = rng.sample(StandardNormal);
                let dy: f32 = rng.sample(StandardNormal);
                let drift = wall_avoidance_drift(
                    Vec2::new(pose.0, pose.1),
                    Vec2::new(half_width, half_height),
                    config.wall_avoidance_margin,
                    config.wall_avoidance_strength,
                ) * dt;
                pose.0 = (pose.0 + dx * step_sigma + drift.x).clamp(-half_width, half_width);
                pose.1 = (pose.1 + dy * step_sigma + drift.y).clamp(-half_height, half_height);
            }
        }

        poses
    }
}
