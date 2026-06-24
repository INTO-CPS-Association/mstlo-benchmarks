use bevy::prelude::*;

use crate::{
    robot::{Robot, RobotLabel, RobotPose},
    simulation::SimulationConfig,
};

pub fn setup_camera(mut commands: Commands, config: Res<SimulationConfig>) {
    commands.spawn(Camera2d);
    commands.spawn((
        Sprite {
            color: Color::srgba(0.08, 0.09, 0.10, 1.0),
            custom_size: Some(Vec2::new(
                config.arena_width * config.render_scale,
                config.arena_height * config.render_scale,
            )),
            ..default()
        },
        Transform::from_xyz(0.0, 0.0, -1.0),
    ));
}

pub fn sync_robot_labels(
    config: Res<SimulationConfig>,
    robots: Query<(&Robot, &RobotPose)>,
    mut labels: Query<(&RobotLabel, &mut Transform)>,
) {
    for (label, mut transform) in &mut labels {
        if let Some((_, pose)) = robots.iter().find(|(robot, _)| robot.id == label.robot_id) {
            let rendered = config.render_position(pose.x, pose.y);
            transform.translation.x = rendered.x + config.render_radius() + 4.0;
            transform.translation.y = rendered.y + config.render_radius() + 4.0;
        }
    }
}
