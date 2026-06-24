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
use ros::{RosBridge, RosBridgeHandle};
use simulation::{SimulationConfig, SimulationRng};
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
        })
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
        .add_systems(Update, rendering::sync_robot_labels);

    app.run();
}
