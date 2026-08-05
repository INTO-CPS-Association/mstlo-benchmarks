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

const TC_LISTENER_READY_TIMEOUT: Duration = Duration::from_secs(3);
const TC_DISCOVERY_SPINS: usize = 10;
const TC_DISCOVERY_SPIN_INTERVAL: Duration = Duration::from_millis(100);

type TcAssignments = Vec<Vec<HighlightQuadrant>>;
type TcUpdateReceiver = Arc<Mutex<mpsc::Receiver<TcAssignments>>>;

#[derive(Resource)]
pub struct RosBridgeHandle {
    pub sender: Sender<Vec<RobotPosition>>,
    pub _worker: Option<thread::JoinHandle<()>>,
    pub tc_updates: Option<TcUpdateReceiver>,
    pub _tc_worker: Option<thread::JoinHandle<()>>,
}

#[derive(Resource)]
pub struct TcAssignmentState {
    assignments: TcAssignments,
}

impl TcAssignmentState {
    pub fn new(robots: usize) -> Self {
        Self {
            assignments: vec![Vec::new(); robots],
        }
    }

    pub fn drain_updates(&mut self, ros: &RosBridgeHandle) -> usize {
        let Some(receiver) = &ros.tc_updates else {
            return 0;
        };
        let Ok(receiver) = receiver.lock() else {
            return 0;
        };

        let mut updates = 0;
        while let Ok(assignments) = receiver.try_recv() {
            self.assignments = assignments;
            updates += 1;
        }
        updates
    }

    pub fn assigned_quadrants(&self, robot_id: usize) -> &[HighlightQuadrant] {
        self.assignments
            .get(robot_id)
            .map(Vec::as_slice)
            .unwrap_or(&[])
    }

    pub fn assignments(&self) -> &[Vec<HighlightQuadrant>] {
        &self.assignments
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

pub fn start_tc_reconfiguration_listener(
    config: SimulationConfig,
) -> Result<(TcUpdateReceiver, thread::JoinHandle<()>), String> {
    let (sender, receiver) = mpsc::channel();
    let (ready_sender, ready_receiver) = mpsc::sync_channel(1);
    let receiver = Arc::new(Mutex::new(receiver));
    let handle = thread::Builder::new()
        .name("tc-reconfiguration-listener".to_string())
        .spawn(move || run_tc_reconfiguration_listener(config, sender, ready_sender))
        .map_err(|err| format!("failed to spawn TC reconfiguration listener: {err}"))?;

    match ready_receiver.recv_timeout(TC_LISTENER_READY_TIMEOUT) {
        Ok(Ok(())) => {}
        Ok(Err(err)) => return Err(err),
        Err(mpsc::RecvTimeoutError::Timeout) => {
            eprintln!(
                "WARN TC reconfiguration listener did not report ready within {:?}; continuing",
                TC_LISTENER_READY_TIMEOUT
            );
        }
        Err(mpsc::RecvTimeoutError::Disconnected) => {
            return Err("TC reconfiguration listener exited before becoming ready".to_string());
        }
    }

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

fn run_tc_reconfiguration_listener(
    config: SimulationConfig,
    sender: mpsc::Sender<TcAssignments>,
    ready_sender: mpsc::SyncSender<Result<(), String>>,
) {
    if config.robots == 0 {
        let _ = ready_sender.send(Ok(()));
        return;
    }

    let ctx = match Context::create() {
        Ok(ctx) => ctx,
        Err(err) => {
            let message = format!("failed to create ROS context for TC listener: {err}");
            eprintln!("{message}");
            let _ = ready_sender.send(Err(message));
            return;
        }
    };
    let mut node = match Node::create(ctx, "tc_reconfiguration_listener", "") {
        Ok(node) => node,
        Err(err) => {
            let message = format!("failed to create TC reconfiguration listener node: {err}");
            eprintln!("{message}");
            let _ = ready_sender.send(Err(message));
            return;
        }
    };

    let mut pool = LocalPool::new();
    let spawner = pool.spawner();
    let base_topic = config
        .trustworthiness_checker_reconf_topic
        .trim_start_matches('/')
        .to_string();
    let assignments = Arc::new(Mutex::new(vec![Vec::new(); config.robots]));

    for worker_id in 0..config.robots {
        let topic = format!("/{base_topic}_R{}", worker_id + 1);
        let Ok(subscriber) =
            node.subscribe::<r2r::std_msgs::msg::String>(&topic, QosProfile::default())
        else {
            eprintln!("failed to subscribe to TC reconfiguration topic {topic}");
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
            eprintln!("failed to spawn TC reconfiguration task for {topic}: {err}");
        }
    }

    for _ in 0..TC_DISCOVERY_SPINS {
        node.spin_once(TC_DISCOVERY_SPIN_INTERVAL);
        pool.run_until_stalled();
    }

    eprintln!("INFO listening for trustworthiness checker reconfig topics on /{base_topic}_R*");
    let _ = ready_sender.send(Ok(()));

    loop {
        node.spin_once(Duration::from_millis(100));
        pool.run_until_stalled();
    }
}

fn apply_reconfig_payload(
    worker_id: usize,
    robots: usize,
    payload: &str,
    assignments: &Arc<Mutex<TcAssignments>>,
    sender: &mpsc::Sender<TcAssignments>,
) {
    let worker_quadrants = reconfig_payload_quadrants(payload);
    if worker_quadrants.is_empty() {
        eprintln!(
            "INFO TC reconfiguration: R{} received no machine property",
            worker_id + 1
        );
    } else {
        eprintln!(
            "INFO TC reconfiguration: R{} is monitoring {:?}",
            worker_id + 1,
            worker_quadrants
        );
    }

    let Ok(mut assignments) = assignments.lock() else {
        return;
    };
    let Some(assignment) = assignments.get_mut(worker_id) else {
        return;
    };

    if *assignment == worker_quadrants {
        return;
    }
    *assignment = worker_quadrants;
    let mut updated_assignments = assignments.clone();
    updated_assignments.resize_with(robots, Vec::new);
    let active = updated_assignments
        .iter()
        .filter(|quadrants| !quadrants.is_empty())
        .count();
    eprintln!("INFO TC assignments highlight {active} active workers");
    let _ = sender.send(updated_assignments);
}

fn reconfig_payload_quadrants(payload: &str) -> Vec<HighlightQuadrant> {
    let Ok(value) = serde_json::from_str::<serde_json::Value>(payload) else {
        return Vec::new();
    };
    let Some(spec) = value.get("spec").and_then(|spec| spec.as_str()) else {
        return Vec::new();
    };

    let mut quadrants = Vec::new();
    for line in spec.lines().map(str::trim) {
        let Some(rest) = line.strip_prefix("out ") else {
            continue;
        };
        let Some((variable, _)) = rest.split_once(':') else {
            continue;
        };
        if let Some(quadrant) = monitored_property_quadrant(variable.trim())
            && !quadrants.contains(&quadrant)
        {
            quadrants.push(quadrant);
        }
    }

    quadrants
}

fn monitored_property_quadrant(variable: &str) -> Option<HighlightQuadrant> {
    match variable {
        "CPred" => Some(HighlightQuadrant::Ne),
        "SPred" => Some(HighlightQuadrant::Se),
        "VPred" => Some(HighlightQuadrant::Sw),
        "HPred" => Some(HighlightQuadrant::Nw),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn detects_quadrant_property_reconfig_specs() {
        let payload = serde_json::json!({
            "spec": "in ConveyorSystem: Int\nout CPred: Bool\nCPred = ConveyorSystem > 0\n",
            "type_info": {}
        })
        .to_string();

        assert_eq!(
            reconfig_payload_quadrants(&payload),
            vec![HighlightQuadrant::Ne]
        );
    }

    #[test]
    fn empty_or_invalid_reconfig_payload_contains_no_quadrant_property() {
        assert_eq!(reconfig_payload_quadrants("{not json"), Vec::new());
        assert_eq!(
            reconfig_payload_quadrants(&serde_json::json!({ "spec": "" }).to_string()),
            Vec::new()
        );
        assert_eq!(
            reconfig_payload_quadrants(
                &serde_json::json!({
                    "spec": "out r2Trustworthy: Bool\nr2Trustworthy = true\n"
                })
                .to_string()
            ),
            Vec::new()
        );
    }

    #[test]
    fn detects_multiple_quadrant_property_reconfig_specs() {
        let payload = serde_json::json!({
            "spec": "in VerticalLift: Int\nin StackerCrane: Int\nout SPred: Bool\nout VPred: Bool\nSPred = true\nVPred = true\n",
            "type_info": {}
        })
        .to_string();

        assert_eq!(
            reconfig_payload_quadrants(&payload),
            vec![HighlightQuadrant::Se, HighlightQuadrant::Sw]
        );
    }

    #[test]
    fn detects_each_quadrant_property_name() {
        for (name, quadrant) in [
            ("CPred", HighlightQuadrant::Ne),
            ("SPred", HighlightQuadrant::Se),
            ("VPred", HighlightQuadrant::Sw),
            ("HPred", HighlightQuadrant::Nw),
        ] {
            assert_eq!(monitored_property_quadrant(name), Some(quadrant));
        }
    }
}
