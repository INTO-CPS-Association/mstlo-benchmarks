use std::{
    sync::{Arc, Mutex, mpsc},
    thread,
    time::Duration,
};

use bevy::prelude::*;
use futures::{executor::LocalPool, future, stream::StreamExt, task::LocalSpawnExt};
use r2r::{Context, Node, Publisher, geometry_msgs::msg::Pose2D, qos::QosProfile};
use tokio::sync::mpsc::{Receiver, Sender};

use crate::{
    robot::{HighlightQuadrant, Robot, RobotPose, RobotPosition},
    simulation::SimulationConfig,
};

#[derive(Resource)]
pub struct RosBridgeHandle {
    pub sender: Sender<Vec<RobotPosition>>,
    pub _worker: Option<thread::JoinHandle<()>>,
    pub trust_monitor_updates: Option<Arc<Mutex<mpsc::Receiver<Vec<Option<HighlightQuadrant>>>>>>,
    pub _trust_monitor_worker: Option<thread::JoinHandle<()>>,
}

#[derive(Resource)]
pub struct TrustMonitorState {
    monitored: Vec<Option<HighlightQuadrant>>,
}

impl TrustMonitorState {
    pub fn new(robots: usize) -> Self {
        Self {
            monitored: vec![None; robots],
        }
    }

    pub fn drain_updates(&mut self, ros: &RosBridgeHandle) {
        let Some(receiver) = &ros.trust_monitor_updates else {
            return;
        };
        let Ok(receiver) = receiver.lock() else {
            return;
        };

        while let Ok(monitored) = receiver.try_recv() {
            self.monitored = monitored;
        }
    }

    pub fn monitored_quadrant(&self, robot_id: usize) -> Option<HighlightQuadrant> {
        self.monitored.get(robot_id).copied().flatten()
    }
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

pub fn start_trust_monitor_reconfig_listener(
    config: SimulationConfig,
) -> Result<
    (
        Arc<Mutex<mpsc::Receiver<Vec<Option<HighlightQuadrant>>>>>,
        thread::JoinHandle<()>,
    ),
    String,
> {
    let (sender, receiver) = mpsc::channel();
    let receiver = Arc::new(Mutex::new(receiver));
    let handle = thread::Builder::new()
        .name("trust-monitor-reconfig-listener".to_string())
        .spawn(move || run_trust_monitor_reconfig_listener(config, sender))
        .map_err(|err| format!("failed to spawn trust monitor reconfig listener: {err}"))?;

    Ok((receiver, handle))
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

fn run_trust_monitor_reconfig_listener(
    config: SimulationConfig,
    sender: mpsc::Sender<Vec<Option<HighlightQuadrant>>>,
) {
    if config.robots == 0 {
        return;
    }

    let ctx = match Context::create() {
        Ok(ctx) => ctx,
        Err(err) => {
            eprintln!("failed to create ROS context for trust monitor listener: {err}");
            return;
        }
    };
    let mut node = match Node::create(ctx, "trust_monitor_reconfig_listener", "") {
        Ok(node) => node,
        Err(err) => {
            eprintln!("failed to create trust monitor reconfig listener node: {err}");
            return;
        }
    };

    let mut pool = LocalPool::new();
    let spawner = pool.spawner();
    let base_topic = config
        .trustworthiness_checker_reconf_topic
        .trim_start_matches('/')
        .to_string();
    let assignments = Arc::new(Mutex::new(vec![None; config.robots]));

    for worker_id in 0..config.robots {
        let topic = format!("/{base_topic}_R{}", worker_id + 1);
        let Ok(subscriber) =
            node.subscribe::<r2r::std_msgs::msg::String>(&topic, QosProfile::default())
        else {
            eprintln!("failed to subscribe to trust monitor reconfig topic {topic}");
            continue;
        };
        let assignments = Arc::clone(&assignments);
        let sender = sender.clone();
        let robots = config.robots;

        if let Err(err) = spawner.spawn_local(async move {
            subscriber
                .for_each(move |msg| {
                    apply_reconfig_payload(worker_id, robots, &msg.data, &assignments, &sender);
                    future::ready(())
                })
                .await;
        }) {
            eprintln!("failed to spawn trust monitor reconfig task for {topic}: {err}");
        }
    }

    eprintln!("INFO listening for trustworthiness checker reconfig topics on /{base_topic}_R*");

    loop {
        node.spin_once(Duration::from_millis(100));
        pool.run_until_stalled();
    }
}

fn apply_reconfig_payload(
    worker_id: usize,
    robots: usize,
    payload: &str,
    assignments: &Arc<Mutex<Vec<Option<HighlightQuadrant>>>>,
    sender: &mpsc::Sender<Vec<Option<HighlightQuadrant>>>,
) {
    let worker_quadrant = reconfig_payload_quadrant(payload);
    match worker_quadrant {
        Some(quadrant) => eprintln!(
            "INFO trust monitor reconfig: R{} is monitoring {:?}",
            worker_id + 1,
            quadrant
        ),
        None => eprintln!(
            "INFO trust monitor reconfig: R{} received no quadrant property",
            worker_id + 1
        ),
    }

    let Ok(mut assignments) = assignments.lock() else {
        return;
    };
    let Some(assignment) = assignments.get_mut(worker_id) else {
        return;
    };

    *assignment = worker_quadrant;
    let mut monitored = assignments.clone();
    monitored.resize(robots, None);
    let _ = sender.send(monitored);
}

fn reconfig_payload_quadrant(payload: &str) -> Option<HighlightQuadrant> {
    let Ok(value) = serde_json::from_str::<serde_json::Value>(payload) else {
        return None;
    };
    let Some(spec) = value.get("spec").and_then(|spec| spec.as_str()) else {
        return None;
    };

    for line in spec.lines().map(str::trim) {
        let Some(rest) = line.strip_prefix("out ") else {
            continue;
        };
        let Some((variable, _)) = rest.split_once(':') else {
            continue;
        };
        if let Some(quadrant) = quadrant_trust_var(variable.trim()) {
            return Some(quadrant);
        }
    }

    None
}

fn quadrant_trust_var(variable: &str) -> Option<HighlightQuadrant> {
    match variable {
        "neTrustworthy" => Some(HighlightQuadrant::Ne),
        "nwTrustworthy" => Some(HighlightQuadrant::Nw),
        "swTrustworthy" => Some(HighlightQuadrant::Sw),
        "seTrustworthy" => Some(HighlightQuadrant::Se),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn detects_quadrant_property_reconfig_specs() {
        let payload = serde_json::json!({
            "spec": "in r2Pose: Struct<x: Float, y: Float, theta: Float>\nout neTrustworthy: Bool\nneTrustworthy = true\n",
            "type_info": {}
        })
        .to_string();

        assert_eq!(
            reconfig_payload_quadrant(&payload),
            Some(HighlightQuadrant::Ne)
        );
    }

    #[test]
    fn empty_or_invalid_reconfig_payload_contains_no_quadrant_property() {
        assert_eq!(reconfig_payload_quadrant("{not json"), None);
        assert_eq!(
            reconfig_payload_quadrant(&serde_json::json!({ "spec": "" }).to_string()),
            None
        );
        assert_eq!(
            reconfig_payload_quadrant(
                &serde_json::json!({
                    "spec": "out r2Trustworthy: Bool\nr2Trustworthy = true\n"
                })
                .to_string()
            ),
            None
        );
    }

    #[test]
    fn detects_each_quadrant_property_name() {
        for (name, quadrant) in [
            ("neTrustworthy", HighlightQuadrant::Ne),
            ("nwTrustworthy", HighlightQuadrant::Nw),
            ("swTrustworthy", HighlightQuadrant::Sw),
            ("seTrustworthy", HighlightQuadrant::Se),
        ] {
            assert_eq!(quadrant_trust_var(name), Some(quadrant));
        }
    }
}
