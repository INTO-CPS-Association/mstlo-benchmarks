use bevy::prelude::*;

use crate::{
    robot::{
        HighlightQuadrant, MonitorHighlightLayer, Robot, RobotLabel, RobotMonitorCircle, RobotPose,
    },
    ros::{RosBridgeHandle, TrustMonitorState},
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

    spawn_quadrant_backgrounds(&mut commands, &config);
}

fn spawn_quadrant_backgrounds(commands: &mut Commands, config: &SimulationConfig) {
    let quadrant_width = config.arena_width * config.render_scale * 0.5;
    let quadrant_height = config.arena_height * config.render_scale * 0.5;
    let x_offset = quadrant_width * 0.5;
    let y_offset = quadrant_height * 0.5;

    for (quadrant, x, y) in [
        (HighlightQuadrant::Ne, x_offset, y_offset),
        (HighlightQuadrant::Nw, -x_offset, y_offset),
        (HighlightQuadrant::Sw, -x_offset, -y_offset),
        (HighlightQuadrant::Se, x_offset, -y_offset),
    ] {
        commands.spawn((
            Sprite {
                color: quadrant_color(quadrant, 0.16),
                custom_size: Some(Vec2::new(quadrant_width, quadrant_height)),
                ..default()
            },
            Transform::from_xyz(x, y, -0.8),
        ));
    }
}

pub fn sync_robot_monitor_circles(
    config: Res<SimulationConfig>,
    ros: Res<RosBridgeHandle>,
    mut monitor_state: ResMut<TrustMonitorState>,
    robots: Query<(&Robot, &RobotPose)>,
    mut circles: Query<(
        &RobotMonitorCircle,
        &mut Sprite,
        &mut Transform,
        &mut Visibility,
    )>,
) {
    monitor_state.drain_updates(&ros);

    for (circle, mut sprite, mut transform, mut visibility) in &mut circles {
        if let Some((_, pose)) = robots.iter().find(|(robot, _)| robot.id == circle.robot_id) {
            let rendered = config.render_position(pose.x, pose.y);
            transform.translation.x = rendered.x;
            transform.translation.y = rendered.y;
        }

        let Some(quadrant) = monitor_state.monitored_quadrant(circle.robot_id) else {
            *visibility = Visibility::Hidden;
            continue;
        };

        sprite.color = monitor_highlight_color(quadrant, circle.layer);
        *visibility = Visibility::Visible;
    }
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

pub fn quadrant_color(quadrant: HighlightQuadrant, alpha: f32) -> Color {
    match quadrant {
        HighlightQuadrant::Ne => Color::srgba(0.8, 0.0, 0.0, alpha),
        HighlightQuadrant::Nw => Color::srgba(0.8, 0.8, 0.0, alpha),
        HighlightQuadrant::Sw => Color::srgba(0.0, 0.4, 0.8, alpha),
        HighlightQuadrant::Se => Color::srgba(0.0, 0.8, 0.0, alpha),
    }
}

fn monitor_highlight_color(quadrant: HighlightQuadrant, layer: MonitorHighlightLayer) -> Color {
    match layer {
        MonitorHighlightLayer::Glow => quadrant_color(quadrant, 0.36),
        MonitorHighlightLayer::Ring => quadrant_color(quadrant, 0.96),
        MonitorHighlightLayer::Cutout => Color::srgba(0.08, 0.09, 0.10, 1.0),
    }
}
