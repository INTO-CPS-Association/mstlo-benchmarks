# Robot Brownian Simulation

A seeded Brownian-motion simulation for multiple robots, visualized with Bevy.
Each robot publishes its pose through a separate ROS 2 node, and the simulator
can launch a distributed trustworthiness checker that reallocates monitoring
responsibilities as robots move.

## Requirements

- Rust and Cargo
- ROS 2 Jazzy
- The `robosapiens-trustworthiness-checker` repository for distributed monitoring
- [`uv`](https://docs.astral.sh/uv/) for scalability benchmark sweeps

The checker is expected at `../robosapiens-trustworthiness-checker` by default.
Use `--trustworthiness-checker-dir` and `--trustworthiness-checker-ros-setup` if
it is installed elsewhere.

ROS 2 must be sourced before compiling because `r2r` reads the ROS environment
at build time, including for runs that use `--no-ros`.

## Run the simulation

```bash
source /opt/ros/jazzy/setup.bash
cargo run -- --robots 20 --seed 123 --brownian-scale 35
```

To run the visualization without publishing poses:

```bash
source /opt/ros/jazzy/setup.bash
cargo run -- --no-ros --robots 20 --seed 123
```

A seed and simulation configuration produce the same trajectory. Robots use
Brownian motion with inward drift near arena walls.

## Run distributed monitoring

```bash
source /opt/ros/jazzy/setup.bash
cargo run -- --robots 4 --trustworthiness-checker
```

`--tc` is an alias for `--trustworthiness-checker`. The simulator generates the
checker configuration, starts one worker per robot and one scheduler, and uses
quadrant-based constraints to assign machine properties to workers. Generated
configuration and logs are written under `target/trustworthiness-checker/`.

Each robot publishes `geometry_msgs/msg/Pose2D` on its own topic:

```text
/robot_0/pose2d
/robot_1/pose2d
...
```

For example:

```bash
ros2 topic echo /robot_0/pose2d
```

## Scalability benchmarks

The headless benchmark mode exercises the same simulation, ROS publishing, and
checker integration while writing JSONL telemetry:

```bash
source /opt/ros/jazzy/setup.bash
cargo run --release -- \
  --robots 10 \
  --trustworthiness-checker \
  --benchmark-duration-secs 120 \
  --benchmark-warmup-secs 20 \
  --benchmark-output-dir target/scalability-benchmarks/manual
```

The Python harness runs multi-size sweeps and produces Parquet summaries and
plots. A short simulator-only smoke run is:

```bash
uv run benchmark-scalability \
  --robots 2,4 \
  --seeds 123 \
  --duration 5 \
  --warmup 1 \
  --no-ros \
  --profile dev
```

Run `cargo run -- --help` and `uv run benchmark-scalability --help` for the full
set of options.

## License

This project is distributed under the INTO-CPS Association Public License
(ICAPL) version 1.0. The selected usage mode is GPL; see `LICENSE.md` and
`ICA-USAGE-MODE.txt`.
