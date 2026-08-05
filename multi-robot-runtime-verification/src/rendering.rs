use bevy::prelude::*;

use crate::{
    robot::{
        HighlightQuadrant, MonitorHighlightLayer, Robot, RobotLabel, RobotMonitorCircle, RobotPose,
    },
    ros::{RosBridgeHandle, TcAssignmentState},
    simulation::SimulationConfig,
};

pub fn setup_camera(mut commands: Commands, config: Res<SimulationConfig>) {
    commands.spawn(Camera2d);
    let arena_center = config.render_position(config.arena_center_x(), config.arena_center_y());
    commands.spawn((
        Sprite {
            color: Color::WHITE,
            custom_size: Some(Vec2::new(
                config.arena_width * config.render_scale,
                config.arena_height * config.render_scale,
            )),
            ..default()
        },
        Transform::from_xyz(arena_center.x, arena_center.y, -1.0),
    ));

    spawn_machine_region_overlays(&mut commands, &config);
}

fn spawn_machine_region_overlays(commands: &mut Commands, config: &SimulationConfig) {
    let region_size = Vec2::splat(10.0 * config.render_scale);

    for (quadrant, label, x, y) in [
        (HighlightQuadrant::Ne, "Conveyor System", 3.5, 3.0),
        (HighlightQuadrant::Se, "Stacker Crane", 3.5, -6.0),
        (HighlightQuadrant::Sw, "Vertical Lift", -4.0, -6.0),
        (HighlightQuadrant::Nw, "Horizontal Carousel", -4.0, 3.0),
    ] {
        let rendered = config.render_position(x, y);
        commands.spawn((
            Sprite {
                color: quadrant_color(quadrant, 0.42),
                custom_size: Some(region_size),
                ..default()
            },
            Transform::from_xyz(rendered.x, rendered.y, -0.8),
        ));

        spawn_region_border(commands, config, quadrant, rendered, region_size);
        spawn_machine_marker(commands, quadrant, rendered, config);

        commands.spawn((
            Text2d::new(label),
            TextFont {
                font_size: FontSize::Px(config.machine_label_font_size()),
                ..default()
            },
            TextColor(Color::srgba(0.05, 0.06, 0.07, 1.0)),
            Transform::from_xyz(
                rendered.x,
                rendered.y + config.machine_label_y_offset(),
                0.2,
            ),
        ));
    }
}

fn spawn_machine_marker(
    commands: &mut Commands,
    quadrant: HighlightQuadrant,
    center: Vec2,
    config: &SimulationConfig,
) {
    let marker_scale = config.machine_marker_scale();
    let marker_size = Vec2::new(
        config.render_scale * 1.2 * marker_scale,
        config.render_scale * 0.7 * marker_scale,
    );
    commands.spawn((
        Sprite {
            color: quadrant_color(quadrant, 0.92),
            custom_size: Some(marker_size),
            ..default()
        },
        Transform::from_xyz(center.x, center.y, 0.15),
    ));

    commands.spawn((
        Sprite {
            color: Color::srgba(0.04, 0.05, 0.06, 1.0),
            custom_size: Some(Vec2::new(marker_size.x + 6.0, 3.0)),
            ..default()
        },
        Transform::from_xyz(center.x, center.y + marker_size.y * 0.5, 0.16),
    ));
    commands.spawn((
        Sprite {
            color: Color::srgba(0.04, 0.05, 0.06, 1.0),
            custom_size: Some(Vec2::new(marker_size.x + 6.0, 3.0)),
            ..default()
        },
        Transform::from_xyz(center.x, center.y - marker_size.y * 0.5, 0.16),
    ));
    commands.spawn((
        Sprite {
            color: Color::srgba(0.04, 0.05, 0.06, 1.0),
            custom_size: Some(Vec2::new(3.0, marker_size.y + 6.0)),
            ..default()
        },
        Transform::from_xyz(center.x - marker_size.x * 0.5, center.y, 0.16),
    ));
    commands.spawn((
        Sprite {
            color: Color::srgba(0.04, 0.05, 0.06, 1.0),
            custom_size: Some(Vec2::new(3.0, marker_size.y + 6.0)),
            ..default()
        },
        Transform::from_xyz(center.x + marker_size.x * 0.5, center.y, 0.16),
    ));
}

fn spawn_region_border(
    commands: &mut Commands,
    config: &SimulationConfig,
    quadrant: HighlightQuadrant,
    center: Vec2,
    size: Vec2,
) {
    let color = quadrant_color(quadrant, 0.90);
    let thickness = config.region_border_thickness();
    for (x, y, w, h) in [
        (center.x, center.y + size.y * 0.5, size.x, thickness),
        (center.x, center.y - size.y * 0.5, size.x, thickness),
        (center.x - size.x * 0.5, center.y, thickness, size.y),
        (center.x + size.x * 0.5, center.y, thickness, size.y),
    ] {
        commands.spawn((
            Sprite {
                color,
                custom_size: Some(Vec2::new(w, h)),
                ..default()
            },
            Transform::from_xyz(x, y, 0.1),
        ));
    }
}

pub fn sync_robot_monitor_circles(
    config: Res<SimulationConfig>,
    ros: Res<RosBridgeHandle>,
    mut tc_assignment_state: ResMut<TcAssignmentState>,
    robots: Query<(&Robot, &RobotPose)>,
    mut circles: Query<(
        &RobotMonitorCircle,
        &mut Sprite,
        &mut Transform,
        &mut Visibility,
    )>,
) {
    tc_assignment_state.drain_updates(&ros);

    for (circle, mut sprite, mut transform, mut visibility) in &mut circles {
        if let Some((_, pose)) = robots.iter().find(|(robot, _)| robot.id == circle.robot_id) {
            let rendered = config.render_position(pose.x, pose.y);
            transform.translation.x = rendered.x;
            transform.translation.y = rendered.y;
        }

        let assigned_quadrants = tc_assignment_state.assigned_quadrants(circle.robot_id);
        if !assigned_quadrants.contains(&circle.quadrant) {
            *visibility = Visibility::Hidden;
            continue;
        }

        let active_index = assigned_quadrants
            .iter()
            .position(|quadrant| *quadrant == circle.quadrant)
            .unwrap_or(0);
        let stack_index = if assigned_quadrants.len() > 1 {
            assigned_quadrants
                .len()
                .saturating_sub(1)
                .saturating_sub(active_index)
        } else {
            0
        };
        let scale_offset = stack_index as f32 * config.render_radius() * 1.25;
        transform.translation.z = match circle.layer {
            MonitorHighlightLayer::Glow => 0.35 + active_index as f32 * 0.08,
            MonitorHighlightLayer::Ring => 0.45 + active_index as f32 * 0.08,
        };
        let diameter = if assigned_quadrants.len() > 1 {
            match circle.layer {
                MonitorHighlightLayer::Glow => config.render_radius() * 5.0 + scale_offset,
                MonitorHighlightLayer::Ring => config.render_radius() * 4.0 + scale_offset,
            }
        } else {
            match circle.layer {
                MonitorHighlightLayer::Glow => config.render_radius() * 5.0,
                MonitorHighlightLayer::Ring => config.render_radius() * 4.0,
            }
        };
        sprite.custom_size = Some(Vec2::splat(diameter));
        sprite.color = monitor_highlight_color(circle.quadrant, circle.layer);
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
            transform.translation.x =
                rendered.x + config.render_radius() + config.robot_label_offset();
            transform.translation.y =
                rendered.y + config.render_radius() + config.robot_label_offset();
        }
    }
}

pub fn quadrant_color(quadrant: HighlightQuadrant, alpha: f32) -> Color {
    match quadrant {
        HighlightQuadrant::Nw => Color::srgba(0.8, 0.0, 0.0, alpha),
        HighlightQuadrant::Ne => Color::srgba(0.0, 0.8, 0.0, alpha),
        HighlightQuadrant::Sw => Color::srgba(0.8, 0.8, 0.0, alpha),
        HighlightQuadrant::Se => Color::srgba(0.0, 0.4, 0.8, alpha),
    }
}

fn monitor_highlight_color(quadrant: HighlightQuadrant, layer: MonitorHighlightLayer) -> Color {
    match layer {
        MonitorHighlightLayer::Glow => quadrant_color(quadrant, 0.22),
        MonitorHighlightLayer::Ring => quadrant_color(quadrant, 0.96),
    }
}
