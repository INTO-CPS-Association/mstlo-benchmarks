use bevy::prelude::*;

#[derive(Component, Clone, Copy, Debug, PartialEq, Eq)]
pub struct Robot {
    pub id: usize,
}

#[derive(Component, Clone, Copy, Debug, PartialEq)]
pub struct RobotPose {
    pub x: f32,
    pub y: f32,
    pub theta: f32,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct RobotPosition {
    pub id: usize,
    pub x: f32,
    pub y: f32,
    pub theta: f32,
}

impl From<(Robot, RobotPose)> for RobotPosition {
    fn from((robot, pose): (Robot, RobotPose)) -> Self {
        Self {
            id: robot.id,
            x: pose.x,
            y: pose.y,
            theta: pose.theta,
        }
    }
}

#[derive(Component)]
pub struct RobotLabel {
    pub robot_id: usize,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum HighlightQuadrant {
    Ne,
    Nw,
    Sw,
    Se,
}

#[derive(Component, Clone, Copy, Debug, PartialEq, Eq)]
pub enum MonitorHighlightLayer {
    Glow,
    Ring,
}

#[derive(Component)]
pub struct RobotMonitorCircle {
    pub robot_id: usize,
    pub quadrant: HighlightQuadrant,
    pub layer: MonitorHighlightLayer,
}
