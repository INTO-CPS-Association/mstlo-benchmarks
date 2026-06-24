use std::{thread, time::Duration};

use bevy::prelude::*;
use r2r::{Context, Node, Publisher, geometry_msgs::msg::Pose2D, qos::QosProfile};
use tokio::sync::mpsc::{Receiver, Sender};

use crate::{
    robot::{Robot, RobotPose, RobotPosition},
    simulation::SimulationConfig,
};

#[derive(Resource)]
pub struct RosBridgeHandle {
    pub sender: Sender<Vec<RobotPosition>>,
    pub _worker: Option<thread::JoinHandle<()>>,
}

pub struct RosBridge;

impl RosBridge {
    pub fn start(
        config: SimulationConfig,
        receiver: Receiver<Vec<RobotPosition>>,
    ) -> Result<thread::JoinHandle<()>, String> {
        let ctx =
            Context::create().map_err(|err| format!("failed to create ROS context: {err}"))?;
        let mut publishers = Vec::with_capacity(config.robots);
        let mut nodes = Vec::with_capacity(config.robots);

        for id in 0..config.robots {
            let node_name = format!("robot_{id}_position_publisher");
            let mut node = Node::create(ctx.clone(), &node_name, "")
                .map_err(|err| format!("failed to create ROS node {node_name}: {err}"))?;
            let topic = format!("/robot_{id}/pose2d");
            let publisher = node
                .create_publisher::<Pose2D>(&topic, QosProfile::default())
                .map_err(|err| format!("failed to create publisher {topic}: {err}"))?;
            publishers.push(publisher);
            nodes.push(node);
        }

        let publish_interval = Duration::from_secs_f32(1.0 / config.publish_rate_hz);
        let handle = thread::Builder::new()
            .name("ros-position-publisher".to_string())
            .spawn(move || run_ros_worker(receiver, publishers, nodes, publish_interval))
            .map_err(|err| format!("failed to spawn ROS worker: {err}"))?;

        Ok(handle)
    }
}

pub fn queue_positions(ros: Res<RosBridgeHandle>, robots: Query<(&Robot, &RobotPose)>) {
    let mut positions = robots
        .iter()
        .map(|(robot, pose)| RobotPosition::from((*robot, *pose)))
        .collect::<Vec<_>>();
    positions.sort_by_key(|position| position.id);

    let _ = ros.sender.try_send(positions);
}

fn run_ros_worker(
    mut receiver: Receiver<Vec<RobotPosition>>,
    publishers: Vec<Publisher<Pose2D>>,
    mut nodes: Vec<Node>,
    publish_interval: Duration,
) {
    while let Some(positions) = receiver.blocking_recv() {
        let mut latest = positions;

        while let Ok(positions) = receiver.try_recv() {
            latest = positions;
        }

        publish_positions(&latest, &publishers);
        for node in &mut nodes {
            node.spin_once(Duration::from_millis(0));
        }

        thread::sleep(publish_interval);
    }
}

fn publish_positions(positions: &[RobotPosition], publishers: &[Publisher<Pose2D>]) {
    for position in positions {
        let Some(publisher) = publishers.get(position.id) else {
            continue;
        };
        let msg = Pose2D {
            x: position.x as f64,
            y: position.y as f64,
            theta: position.theta as f64,
        };
        if let Err(err) = publisher.publish(&msg) {
            eprintln!("failed to publish /robot_{}/pose2d: {err}", position.id);
        }
    }
}
