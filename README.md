# Robot Brownian Simulation

Bevy visualization of seeded Brownian motion for a configurable number of robots.
Each robot also publishes its pose through a separate ROS 2 node using `r2r`.

## Run

Source ROS 2 Jazzy before building or running. The `r2r` crate needs the ROS
environment at compile time, even when the application is run with `--no-ros`.

```bash
source /opt/ros/jazzy/setup.bash
cargo run -- --robots 20 --seed 123 --brownian-scale 35
```

Launch the distributed trustworthiness-checker experiment alongside the
simulation:

```bash
source /opt/ros/jazzy/setup.bash
cargo run -- --robots 4 --trustworthiness-checker
```

The shorter alias is also available:

```bash
source /opt/ros/jazzy/setup.bash
cargo run -- --robots 4 --tc
```

This writes a generated Pose2D-based DSRV bundle and checker logs to a
timestamped directory under `target/trustworthiness-checker/`, starts one
reconfigurable checker worker per robot, and starts one scheduler checker
process that applies quadrant-based distribution constraints. The generated
checker inputs consume the simulation's `/robot_N/pose2d` topics as typed
`Struct<x: Float, y: Float, theta: Float>` values. Each checker log file starts
with the exact launch command for that process. Captured stdout/stderr logs are
written directly under `logs/`; TC tracing logs are written via the checker's
own `--log-file` support under `logs/tracing/`.

For visualization only, keep ROS sourced and disable runtime publishing:

```bash
source /opt/ros/jazzy/setup.bash
cargo run -- --no-ros --robots 20 --seed 123
```

## ROS Topics

Each robot has one node and one `geometry_msgs/msg/Pose2D` topic:

```text
/robot_0/pose2d
/robot_1/pose2d
...
```

Inspect a topic:

```bash
source /opt/ros/jazzy/setup.bash
ros2 topic echo /robot_0/pose2d
```

## Useful Arguments

```text
--robots <N>
--seed <u64>
--arena-width <f32>
--arena-height <f32>
--brownian-scale <f32>
--sim-hz <f32>
--publish-rate-hz <f32>
--robot-radius <f32>
--robot-labels
--wall-avoidance-margin <f32>
--wall-avoidance-strength <f32>
--no-ros
--trustworthiness-checker
--tc
--trustworthiness-checker-dir <PATH>
--trustworthiness-checker-profile <PROFILE>
--trustworthiness-checker-work-dir <PATH>
--trustworthiness-checker-reconf-topic <TOPIC>
--trustworthiness-checker-dist-graph-topic <TOPIC>
--trustworthiness-checker-ros-setup <PATH>  # default: ../robosapiens-trustworthiness-checker/ros_interfaces/install/local_setup.bash
```

The same seed and simulation configuration produce the same trajectory.
Robots use Brownian motion with an inward drift near arena walls, and are
clamped at the robot radius so the visual marker stays inside the arena.
