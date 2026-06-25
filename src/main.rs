mod config;
mod rendering;
mod robot;
mod ros;
mod simulation;
mod trustworthiness_checker;

use bevy::prelude::*;
use clap::Parser;
use config::Args;
use robot::RobotPosition;
use ros::{RosBridge, RosBridgeHandle, TrustMonitorState, start_trust_monitor_reconfig_listener};
use simulation::{SimulationConfig, SimulationRng, initial_robot_positions};
use std::{thread, time::Duration};
use tokio::sync::mpsc;
use trustworthiness_checker::TrustworthinessCheckerProcesses;

fn main() {
    let args = Args::parse();
    let sim_config = SimulationConfig::from(args.clone());
    eprintln!(
        "INFO simulation config: robots={}, robot_labels={}, arena={}x{}",
        sim_config.robots, sim_config.robot_labels, sim_config.arena_width, sim_config.arena_height
    );
    let (position_sender, position_receiver) = mpsc::channel::<Vec<RobotPosition>>(4);

    let ros_handle = if args.no_ros {
        None
    } else {
        match RosBridge::start(sim_config.clone(), position_receiver) {
            Ok(handle) => Some(handle),
            Err(err) => {
                eprintln!("ROS publishing disabled: {err}");
                None
            }
        }
    };
    let trust_monitor_listener = if args.no_ros {
        None
    } else {
        match start_trust_monitor_reconfig_listener(sim_config.clone()) {
            Ok(listener) => Some(listener),
            Err(err) => {
                eprintln!("trust monitor reconfig listener disabled: {err}");
                None
            }
        }
    };
    let (trust_monitor_updates, trust_monitor_worker) = trust_monitor_listener
        .map(|(receiver, worker)| (Some(receiver), Some(worker)))
        .unwrap_or((None, None));

    if !args.no_ros && args.trustworthiness_checker {
        publish_initial_positions_for_scheduler(sim_config.clone(), position_sender.clone());
    }
    let trustworthiness_checker_processes =
        match TrustworthinessCheckerProcesses::start(&args, &sim_config) {
            Ok(processes) => processes,
            Err(err) => {
                eprintln!("trustworthiness checker launch disabled: {err}");
                TrustworthinessCheckerProcesses::none()
            }
        };

    let mut app = App::new();
    app.insert_resource(sim_config.clone())
        .insert_resource(SimulationRng::new(sim_config.seed))
        .insert_resource(RosBridgeHandle {
            sender: position_sender,
            _worker: ros_handle,
            trust_monitor_updates,
            _trust_monitor_worker: trust_monitor_worker,
        })
        .insert_resource(TrustMonitorState::new(sim_config.robots))
        .insert_resource(trustworthiness_checker_processes)
        .insert_resource(Time::<Fixed>::from_hz(sim_config.sim_hz as f64))
        .add_plugins(DefaultPlugins.set(WindowPlugin {
            primary_window: Some(Window {
                title: "Robot Brownian Simulation".to_string(),
                resolution: (1100, 800).into(),
                ..default()
            }),
            ..default()
        }))
        .add_systems(Startup, (rendering::setup_camera, simulation::spawn_robots))
        .add_systems(
            FixedUpdate,
            (
                simulation::move_robots,
                ros::queue_positions.after(simulation::move_robots),
            ),
        )
        .add_systems(
            Update,
            (
                rendering::sync_robot_labels,
                rendering::sync_robot_monitor_circles,
            ),
        );

    app.run();
}

fn publish_initial_positions_for_scheduler(
    config: SimulationConfig,
    sender: tokio::sync::mpsc::Sender<Vec<RobotPosition>>,
) {
    let positions = initial_robot_positions(&config);
    let interval = Duration::from_secs_f32(1.0 / config.publish_rate_hz.max(1.0));
    thread::Builder::new()
        .name("ros-initial-position-bootstrap".to_string())
        .spawn(move || {
            for _ in 0..120 {
                let _ = sender.try_send(positions.clone());
                thread::sleep(interval);
            }
        })
        .expect("failed to spawn initial ROS position bootstrap");
}
