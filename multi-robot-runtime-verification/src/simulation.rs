use bevy::prelude::*;
use rand::{RngExt, SeedableRng};
use rand_chacha::ChaCha8Rng;
use rand_distr::StandardNormal;

use crate::{
    config::Args,
    robot::{
        HighlightQuadrant, MonitorHighlightLayer, Robot, RobotLabel, RobotMonitorCircle, RobotPose,
        RobotPosition,
    },
};

#[derive(Clone, Debug, Resource)]
pub struct SimulationConfig {
    pub robots: usize,
    pub seed: u64,
    pub arena_min_x: f32,
    pub arena_min_y: f32,
    pub arena_width: f32,
    pub arena_height: f32,
    pub brownian_scale: f32,
    pub sim_hz: f32,
    pub publish_rate_hz: f32,
    pub robot_radius: f32,
    pub robot_labels: bool,
    pub screenshot: bool,
    pub wall_avoidance_margin: f32,
    pub wall_avoidance_strength: f32,
    pub render_scale: f32,
    pub trustworthiness_checker_reconf_topic: String,
}

impl From<Args> for SimulationConfig {
    fn from(args: Args) -> Self {
        Self {
            robots: args.robots,
            seed: args.seed,
            arena_min_x: args.arena_min_x,
            arena_min_y: args.arena_min_y,
            arena_width: args.arena_width,
            arena_height: args.arena_height,
            brownian_scale: args.brownian_scale,
            sim_hz: args.sim_hz,
            publish_rate_hz: args.publish_rate_hz,
            robot_radius: args.robot_radius,
            robot_labels: args.robot_labels,
            screenshot: args.screenshot,
            wall_avoidance_margin: args.wall_avoidance_margin,
            wall_avoidance_strength: args.wall_avoidance_strength,
            render_scale: 60.0,
            trustworthiness_checker_reconf_topic: args.trustworthiness_checker_reconf_topic,
        }
    }
}

impl SimulationConfig {
    pub fn render_position(&self, x: f32, y: f32) -> Vec2 {
        Vec2::new(
            (x - self.arena_center_x()) * self.render_scale,
            (y - self.arena_center_y()) * self.render_scale,
        )
    }

    pub fn arena_max_x(&self) -> f32 {
        self.arena_min_x + self.arena_width
    }

    pub fn arena_max_y(&self) -> f32 {
        self.arena_min_y + self.arena_height
    }

    pub fn arena_center_x(&self) -> f32 {
        self.arena_min_x + self.arena_width * 0.5
    }

    pub fn arena_center_y(&self) -> f32 {
        self.arena_min_y + self.arena_height * 0.5
    }

    pub fn robot_min_x(&self) -> f32 {
        self.arena_min_x + self.robot_radius
    }

    pub fn robot_max_x(&self) -> f32 {
        self.arena_max_x() - self.robot_radius
    }

    pub fn robot_min_y(&self) -> f32 {
        self.arena_min_y + self.robot_radius
    }

    pub fn robot_max_y(&self) -> f32 {
        self.arena_max_y() - self.robot_radius
    }

    pub fn render_radius(&self) -> f32 {
        let multiplier = if self.screenshot { 2.6 } else { 1.0 };
        self.robot_radius * self.render_scale * multiplier
    }

    pub fn robot_label_font_size(&self) -> f32 {
        if self.screenshot { 28.0 } else { 13.0 }
    }

    pub fn robot_label_offset(&self) -> f32 {
        if self.screenshot { 10.0 } else { 4.0 }
    }

    pub fn machine_label_font_size(&self) -> f32 {
        if self.screenshot { 34.0 } else { 20.0 }
    }

    pub fn machine_label_y_offset(&self) -> f32 {
        let multiplier = if self.screenshot { 1.15 } else { 0.68 };
        self.render_scale * multiplier
    }

    pub fn machine_marker_scale(&self) -> f32 {
        if self.screenshot { 1.8 } else { 1.0 }
    }

    pub fn region_border_thickness(&self) -> f32 {
        if self.screenshot { 8.0 } else { 4.0 }
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
    for id in 0..config.robots {
        let position = initial_position_for_robot(&config, &mut rng.rng, id);
        let x = position.x;
        let y = position.y;
        let robot_color = robot_color(id);

        commands.spawn((
            Robot { id },
            RobotPose { x, y, theta: 0.0 },
            Sprite {
                color: robot_color,
                custom_size: Some(Vec2::splat(config.render_radius() * 2.0)),
                ..default()
            },
            Transform::from_xyz(
                config.render_position(x, y).x,
                config.render_position(x, y).y,
                1.0,
            ),
        ));

        spawn_monitor_highlight(&mut commands, &config, id, x, y);

        if config.robot_labels {
            commands.spawn((
                RobotLabel { robot_id: id },
                Text2d::new(id.to_string()),
                TextFont {
                    font_size: FontSize::Px(config.robot_label_font_size()),
                    ..default()
                },
                TextColor(Color::WHITE),
                Transform::from_xyz(
                    config.render_position(x, y).x
                        + config.render_radius()
                        + config.robot_label_offset(),
                    config.render_position(x, y).y
                        + config.render_radius()
                        + config.robot_label_offset(),
                    2.0,
                ),
            ));
        }
    }

    eprintln!("INFO spawned {} robot sprites", config.robots);
}

pub fn initial_robot_positions(config: &SimulationConfig) -> Vec<RobotPosition> {
    let mut rng = ChaCha8Rng::seed_from_u64(config.seed);

    (0..config.robots)
        .map(|id| initial_position_for_robot(config, &mut rng, id))
        .collect()
}

pub fn advance_robot_positions(
    config: &SimulationConfig,
    rng: &mut SimulationRng,
    positions: &mut [RobotPosition],
) {
    let dt = 1.0 / config.sim_hz;
    let step_sigma = config.brownian_scale * dt.sqrt();
    let min = Vec2::new(config.robot_min_x(), config.robot_min_y());
    let max = Vec2::new(config.robot_max_x(), config.robot_max_y());

    positions.sort_by_key(|position| position.id);
    for position in positions {
        let dx: f32 = rng.rng.sample(StandardNormal);
        let dy: f32 = rng.rng.sample(StandardNormal);
        let old_x = position.x;
        let old_y = position.y;
        let wall_drift = wall_avoidance_drift(
            Vec2::new(position.x, position.y),
            min,
            max,
            config.wall_avoidance_margin,
            config.wall_avoidance_strength,
        ) * dt;

        position.x = (position.x + dx * step_sigma + wall_drift.x).clamp(min.x, max.x);
        position.y = (position.y + dy * step_sigma + wall_drift.y).clamp(min.y, max.y);
        position.theta = (position.y - old_y).atan2(position.x - old_x);
    }
}

fn robot_color(id: usize) -> Color {
    const ROBOT_COLORS: [Color; 8] = [
        Color::srgb(0.55, 0.20, 0.75), // purple
        Color::srgb(0.95, 0.45, 0.10), // orange
        Color::srgb(0.00, 0.65, 0.75), // teal
        Color::srgb(0.90, 0.15, 0.55), // magenta
        Color::srgb(0.35, 0.35, 0.35), // dark gray
        Color::srgb(0.45, 0.25, 0.05), // brown
        Color::srgb(0.00, 0.35, 0.35), // dark cyan
        Color::srgb(0.55, 0.45, 0.80), // lavender
    ];
    ROBOT_COLORS[id % ROBOT_COLORS.len()]
}

fn initial_position_for_robot(
    config: &SimulationConfig,
    rng: &mut ChaCha8Rng,
    id: usize,
) -> RobotPosition {
    const DISTRIBUTED_MONITOR_STARTS: [(f32, f32); 4] =
        [(-3.54, -5.35), (-3.60, 3.28), (1.50, 3.65), (3.78, -5.83)];

    let (x, y) = DISTRIBUTED_MONITOR_STARTS
        .get(id)
        .copied()
        .unwrap_or_else(|| {
            (
                rng.random_range(config.robot_min_x()..config.robot_max_x()),
                rng.random_range(config.robot_min_y()..config.robot_max_y()),
            )
        });

    RobotPosition {
        id,
        x: x.clamp(config.robot_min_x(), config.robot_max_x()),
        y: y.clamp(config.robot_min_y(), config.robot_max_y()),
        theta: 0.0,
    }
}

fn spawn_monitor_highlight(
    commands: &mut Commands,
    config: &SimulationConfig,
    robot_id: usize,
    x: f32,
    y: f32,
) {
    let rendered = config.render_position(x, y);
    for (quadrant_index, quadrant) in [
        HighlightQuadrant::Ne,
        HighlightQuadrant::Se,
        HighlightQuadrant::Sw,
        HighlightQuadrant::Nw,
    ]
    .into_iter()
    .enumerate()
    {
        let layers = [
            (
                MonitorHighlightLayer::Glow,
                config.render_radius() * 5.0,
                Color::srgba(0.8, 0.0, 0.0, 0.36),
                0.35 + quadrant_index as f32 * 0.03,
            ),
            (
                MonitorHighlightLayer::Ring,
                config.render_radius() * 4.0,
                Color::srgba(0.8, 0.0, 0.0, 0.96),
                0.45 + quadrant_index as f32 * 0.03,
            ),
        ];

        for (layer, diameter, color, z) in layers {
            commands.spawn((
                RobotMonitorCircle {
                    robot_id,
                    quadrant,
                    layer,
                },
                Sprite {
                    color,
                    custom_size: Some(Vec2::splat(diameter)),
                    ..default()
                },
                Transform::from_xyz(rendered.x, rendered.y, z),
                Visibility::Hidden,
            ));
        }
    }
}

pub fn move_robots(
    config: Res<SimulationConfig>,
    mut rng: ResMut<SimulationRng>,
    mut robots: Query<(&Robot, &mut RobotPose, &mut Transform)>,
) {
    let mut ordered = robots.iter_mut().collect::<Vec<_>>();
    ordered.sort_by_key(|(robot, _, _)| robot.id);
    let mut positions = ordered
        .iter()
        .map(|(robot, pose, _)| RobotPosition::from((**robot, **pose)))
        .collect::<Vec<_>>();
    advance_robot_positions(&config, &mut rng, &mut positions);

    for ((_, mut pose, mut transform), position) in ordered.into_iter().zip(positions) {
        pose.x = position.x;
        pose.y = position.y;
        pose.theta = position.theta;

        let rendered = config.render_position(pose.x, pose.y);
        transform.translation.x = rendered.x;
        transform.translation.y = rendered.y;
    }
}

fn wall_avoidance_drift(position: Vec2, min: Vec2, max: Vec2, margin: f32, strength: f32) -> Vec2 {
    Vec2::new(
        axis_wall_drift(position.x, min.x, max.x, margin, strength),
        axis_wall_drift(position.y, min.y, max.y, margin, strength),
    )
}

fn axis_wall_drift(position: f32, min: f32, max: f32, margin: f32, strength: f32) -> f32 {
    let distance_to_min = position - min;
    let distance_to_max = max - position;

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
            arena_min_x: -7.0,
            arena_min_y: -10.5,
            arena_width: 100.0,
            arena_height: 80.0,
            brownian_scale: 3.0,
            sim_hz: 20.0,
            publish_rate_hz: 5.0,
            robot_radius: 4.0,
            robot_labels: false,
            screenshot: false,
            wall_avoidance_margin: 12.0,
            wall_avoidance_strength: 40.0,
            render_scale: 60.0,
            trustworthiness_checker_reconf_topic: "reconfig".to_string(),
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
            arena_min_x: -50.0,
            arena_min_y: -40.0,
            arena_width: 100.0,
            arena_height: 80.0,
            brownian_scale: 3.0,
            sim_hz: 20.0,
            publish_rate_hz: 5.0,
            robot_radius: 4.0,
            robot_labels: false,
            screenshot: false,
            wall_avoidance_margin: 12.0,
            wall_avoidance_strength: 40.0,
            render_scale: 60.0,
            trustworthiness_checker_reconf_topic: "reconfig".to_string(),
        };
        let a = run_reference_sim(&config, 20);
        config.seed = 8;
        let b = run_reference_sim(&config, 20);

        assert_ne!(a, b);
    }

    #[test]
    fn wall_avoidance_pushes_away_from_edges() {
        assert!(axis_wall_drift(-47.0, -50.0, 50.0, 10.0, 20.0) > 0.0);
        assert!(axis_wall_drift(47.0, -50.0, 50.0, 10.0, 20.0) < 0.0);
        assert_eq!(axis_wall_drift(0.0, -50.0, 50.0, 10.0, 20.0), 0.0);
    }

    #[test]
    fn wall_avoidance_keeps_positions_in_arena() {
        let config = SimulationConfig {
            robots: 16,
            seed: 11,
            arena_min_x: -50.0,
            arena_min_y: -40.0,
            arena_width: 100.0,
            arena_height: 80.0,
            brownian_scale: 25.0,
            sim_hz: 20.0,
            publish_rate_hz: 5.0,
            robot_radius: 4.0,
            robot_labels: false,
            screenshot: false,
            wall_avoidance_margin: 12.0,
            wall_avoidance_strength: 80.0,
            render_scale: 60.0,
            trustworthiness_checker_reconf_topic: "reconfig".to_string(),
        };

        let poses = run_reference_sim_f32(&config, 200);
        let min_x = config.robot_min_x();
        let max_x = config.robot_max_x();
        let min_y = config.robot_min_y();
        let max_y = config.robot_max_y();

        assert!(
            poses
                .iter()
                .all(|(x, y)| (min_x..=max_x).contains(x) && (min_y..=max_y).contains(y))
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
                    Vec2::new(-half_width, -half_height),
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
