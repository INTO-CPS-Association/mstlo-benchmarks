use std::{
    collections::BTreeMap,
    thread,
    time::{Duration, Instant},
};

use serde::Serialize;
use tokio::sync::mpsc;

use crate::{
    config::Args,
    robot::{HighlightQuadrant, RobotPosition},
    ros::{RosBridge, RosBridgeHandle, TcAssignmentState, start_tc_reconfiguration_listener},
    simulation::{
        SimulationConfig, SimulationRng, advance_robot_positions, initial_robot_positions,
    },
    telemetry::TelemetryWriter,
    trustworthiness_checker::{MachineProperty, TrustworthinessCheckerProcesses},
};

#[derive(Debug, Serialize)]
struct BenchmarkRunStarted<'a> {
    robots: usize,
    seed: u64,
    duration_secs: f32,
    warmup_secs: f32,
    sim_hz: f32,
    publish_rate_hz: f32,
    trustworthiness_checker: bool,
    no_ros: bool,
    trustworthiness_checker_run_dir: Option<&'a str>,
    trustworthiness_checker_child_pids: Vec<u32>,
}

#[derive(Debug, Serialize)]
struct TickTelemetry {
    tick: u64,
    pose_publish_attempts: u64,
    pose_publish_successes: u64,
    pose_publish_failures: u64,
    reconfig_messages_received: u64,
}

#[derive(Debug, Serialize)]
pub struct CoverageSample {
    tick: u64,
    possible_property_ticks: u64,
    covered_possible_property_ticks: u64,
    coverage: Option<f64>,
    per_property: BTreeMap<String, PropertyCoverageSample>,
}

#[derive(Clone, Debug, Serialize)]
pub struct PropertyCoverageSample {
    possible: bool,
    covered: bool,
    possible_robots: Vec<usize>,
    assigned_robots: Vec<usize>,
}

pub fn run(args: Args, config: SimulationConfig) -> Result<(), String> {
    let run_id = args.benchmark_run_id.clone().unwrap_or_else(default_run_id);
    let duration_secs = args
        .benchmark_duration_secs
        .ok_or("--benchmark-duration-secs is required for benchmark mode".to_string())?;
    let mut telemetry = TelemetryWriter::create(&args.benchmark_output_dir)?;
    let (position_sender, position_receiver) =
        mpsc::channel::<Vec<RobotPosition>>(position_channel_capacity(&config));

    let ros_handle = if args.no_ros {
        None
    } else {
        match RosBridge::start(config.clone(), position_receiver) {
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
        match start_tc_reconfiguration_listener(config.clone()) {
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
    let ros = RosBridgeHandle {
        sender: position_sender,
        _worker: ros_handle,
        tc_updates,
        _tc_worker: tc_worker,
    };

    let trustworthiness_checker_processes =
        match TrustworthinessCheckerProcesses::start(&args, &config) {
            Ok(processes) => processes,
            Err(err) => {
                eprintln!("trustworthiness checker launch disabled: {err}");
                TrustworthinessCheckerProcesses::none()
            }
        };
    let checker_run_dir = trustworthiness_checker_processes
        .run_dir()
        .map(|path| path.display().to_string());

    telemetry.emit(
        &run_id,
        "simulator",
        "benchmark_run_started",
        0.0,
        BenchmarkRunStarted {
            robots: config.robots,
            seed: config.seed,
            duration_secs,
            warmup_secs: args.benchmark_warmup_secs,
            sim_hz: config.sim_hz,
            publish_rate_hz: config.publish_rate_hz,
            trustworthiness_checker: args.trustworthiness_checker,
            no_ros: args.no_ros,
            trustworthiness_checker_run_dir: checker_run_dir.as_deref(),
            trustworthiness_checker_child_pids: trustworthiness_checker_processes.child_pids(),
        },
    )?;

    let mut rng = SimulationRng::new(config.seed);
    let mut positions = initial_robot_positions(&config);
    let mut tc_assignment_state = TcAssignmentState::new(config.robots);
    let mut tick = 0_u64;
    let mut publish_attempts = 0_u64;
    let mut publish_successes = 0_u64;
    let mut publish_failures = 0_u64;
    let mut reconfig_messages = 0_u64;
    let tick_interval = Duration::from_secs_f32(1.0 / config.sim_hz);
    let started = Instant::now();
    let warmup = Duration::from_secs_f32(args.benchmark_warmup_secs);
    let measurement = Duration::from_secs_f32(duration_secs);
    let stop_at = warmup + measurement;
    let mut next_tick = started;

    while started.elapsed() < stop_at {
        advance_robot_positions(&config, &mut rng, &mut positions);
        publish_attempts += 1;
        match ros.sender.try_send(positions.clone()) {
            Ok(()) => publish_successes += 1,
            Err(_) => publish_failures += 1,
        }
        let updates = tc_assignment_state.drain_updates(&ros) as u64;
        reconfig_messages += updates;

        let elapsed = started.elapsed().as_secs_f64();
        if started.elapsed() >= warmup {
            telemetry.emit(
                &run_id,
                "simulator",
                "sim_tick",
                elapsed,
                TickTelemetry {
                    tick,
                    pose_publish_attempts: publish_attempts,
                    pose_publish_successes: publish_successes,
                    pose_publish_failures: publish_failures,
                    reconfig_messages_received: reconfig_messages,
                },
            )?;
            telemetry.emit(
                &run_id,
                "simulator",
                "coverage_sample",
                elapsed,
                calculate_coverage(tick, &positions, tc_assignment_state.assignments()),
            )?;
        }

        tick += 1;
        next_tick += tick_interval;
        let now = Instant::now();
        if next_tick > now {
            thread::sleep(next_tick - now);
        } else {
            next_tick = now;
        }
    }

    telemetry.emit(
        &run_id,
        "simulator",
        "benchmark_run_finished",
        started.elapsed().as_secs_f64(),
        TickTelemetry {
            tick,
            pose_publish_attempts: publish_attempts,
            pose_publish_successes: publish_successes,
            pose_publish_failures: publish_failures,
            reconfig_messages_received: reconfig_messages,
        },
    )?;
    telemetry.flush()?;
    eprintln!(
        "INFO benchmark telemetry written to {}",
        telemetry.path().display()
    );

    drop(trustworthiness_checker_processes);
    std::process::exit(0);
}

pub fn calculate_coverage(
    tick: u64,
    positions: &[RobotPosition],
    assignments: &[Vec<HighlightQuadrant>],
) -> CoverageSample {
    let mut per_property = BTreeMap::new();
    let mut possible_property_ticks = 0_u64;
    let mut covered_possible_property_ticks = 0_u64;

    for property in MachineProperty::ALL {
        let possible_robots = positions
            .iter()
            .filter(|position| robot_in_property_area(position, property))
            .map(|position| position.id)
            .collect::<Vec<_>>();
        let quadrant = property_quadrant(property);
        let assigned_robots = assignments
            .iter()
            .enumerate()
            .filter(|(_, quadrants)| quadrants.contains(&quadrant))
            .map(|(robot_id, _)| robot_id)
            .collect::<Vec<_>>();
        let possible = !possible_robots.is_empty();
        let covered = possible_robots
            .iter()
            .any(|robot_id| assigned_robots.contains(robot_id));

        if possible {
            possible_property_ticks += 1;
            if covered {
                covered_possible_property_ticks += 1;
            }
        }

        per_property.insert(
            property.predicate_var().to_string(),
            PropertyCoverageSample {
                possible,
                covered,
                possible_robots,
                assigned_robots,
            },
        );
    }

    CoverageSample {
        tick,
        possible_property_ticks,
        covered_possible_property_ticks,
        coverage: if possible_property_ticks == 0 {
            None
        } else {
            Some(covered_possible_property_ticks as f64 / possible_property_ticks as f64)
        },
        per_property,
    }
}

fn robot_in_property_area(position: &RobotPosition, property: MachineProperty) -> bool {
    let (center_x, center_y) = property.center();
    (position.x as f64 - center_x).abs() <= 5.0 && (position.y as f64 - center_y).abs() <= 5.0
}

fn property_quadrant(property: MachineProperty) -> HighlightQuadrant {
    match property {
        MachineProperty::ConveyorSystem => HighlightQuadrant::Ne,
        MachineProperty::StackerCrane => HighlightQuadrant::Se,
        MachineProperty::VerticalLift => HighlightQuadrant::Sw,
        MachineProperty::HorizontalCarousel => HighlightQuadrant::Nw,
    }
}

fn default_run_id() -> String {
    format!("run-{}-{}", std::process::id(), unix_time_secs())
}

fn position_channel_capacity(config: &SimulationConfig) -> usize {
    if config.publish_rate_hz <= 0.0 {
        return 4;
    }
    let ticks_per_publish = (config.sim_hz / config.publish_rate_hz).ceil() as usize;
    ticks_per_publish.saturating_mul(2).max(4)
}

fn unix_time_secs() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|duration| duration.as_secs())
        .unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn coverage_counts_possible_and_assigned_matching_robot() {
        let positions = vec![
            RobotPosition {
                id: 0,
                x: 3.5,
                y: 3.0,
                theta: 0.0,
            },
            RobotPosition {
                id: 1,
                x: -4.0,
                y: -6.0,
                theta: 0.0,
            },
        ];
        let assignments = vec![vec![HighlightQuadrant::Ne], vec![HighlightQuadrant::Nw]];

        let sample = calculate_coverage(7, &positions, &assignments);

        assert_eq!(sample.tick, 7);
        assert_eq!(sample.possible_property_ticks, 2);
        assert_eq!(sample.covered_possible_property_ticks, 1);
        assert_eq!(sample.coverage, Some(0.5));
        assert!(sample.per_property["CPred"].covered);
        assert!(!sample.per_property["VPred"].covered);
    }

    #[test]
    fn coverage_is_none_when_no_property_is_possible() {
        let positions = vec![RobotPosition {
            id: 0,
            x: 100.0,
            y: 100.0,
            theta: 0.0,
        }];
        let sample = calculate_coverage(0, &positions, &[vec![HighlightQuadrant::Ne]]);

        assert_eq!(sample.possible_property_ticks, 0);
        assert_eq!(sample.coverage, None);
    }
}
