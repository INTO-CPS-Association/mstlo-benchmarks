mod benchmark;
mod config;
mod rendering;
mod robot;
mod ros;
mod simulation;
mod telemetry;
mod trustworthiness_checker;

use bevy::prelude::*;
use clap::Parser;
use config::Args;
use robot::RobotPosition;
use ros::{RosBridge, RosBridgeHandle, TcAssignmentState, start_tc_reconfiguration_listener};
use simulation::{SimulationConfig, SimulationRng};
use tokio::sync::mpsc;
use trustworthiness_checker::TrustworthinessCheckerProcesses;

fn main() {
    let args = Args::parse();
    let sim_config = SimulationConfig::from(args.clone());
    if args.benchmark_duration_secs.is_some() {
        if let Err(err) = benchmark::run(args, sim_config) {
            eprintln!("benchmark failed: {err}");
            std::process::exit(1);
        }
        return;
    }

    eprintln!(
        "INFO simulation config: robots={}, robot_labels={}, screenshot={}, arena={}x{}",
        sim_config.robots,
        sim_config.robot_labels,
        sim_config.screenshot,
        sim_config.arena_width,
        sim_config.arena_height
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
    let tc_listener = if args.no_ros {
        None
    } else {
        match start_tc_reconfiguration_listener(sim_config.clone()) {
            Ok(listener) => Some(listener),
            Err(err) => {
                eprintln!("trustworthiness checker reconfiguration listener disabled: {err}");
                None
            }
        }
    };
    let (tc_updates, tc_worker) = tc_listener
        .map(|(receiver, worker)| (Some(receiver), Some(worker)))
        .unwrap_or((None, None));

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
            tc_updates,
            _tc_worker: tc_worker,
        })
        .insert_resource(TcAssignmentState::new(sim_config.robots))
        .insert_resource(trustworthiness_checker_processes)
        .insert_resource(Time::<Fixed>::from_hz(sim_config.sim_hz as f64))
        .add_plugins(DefaultPlugins.set(WindowPlugin {
            primary_window: Some(Window {
                title: "Robot Brownian Simulation".to_string(),
                resolution: if sim_config.screenshot {
                    (1400, 1100).into()
                } else {
                    (1100, 800).into()
                },
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
