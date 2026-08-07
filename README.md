# MSTLO reference benchmark

This repository compares MSTLO latency with an in-process direct input path and a ROS 2 input path. Both use the same Brownian robot source and the trustworthiness checker runtime.

The reported metric is latency overhead:

```text
first valid verdict arrival - source publication - property semantic horizon
```

There is one sample for each property and logical timestamp. Later RoSI refinements at the same property/timestamp are ignored, so all semantics have the same weighting. The report shows the median, p95, and p99 of these samples; lower is better. A run fails if any expected property/timestamp verdict is missing or has the wrong payload type.

Direct hosts the checker in the runner process. ROS publishes to a standalone checker and collects verdicts in the same Rust source process. ROS uses reliable, volatile, bounded `KEEP_LAST` queues: depth 64 for inputs and 256 for verdicts.

## Run

Requirements: Rust, `uv`, ROS 2, and `colcon`. ROS defaults to `/opt/ros/jazzy`. The launcher builds the local message overlay and both Rust binaries incrementally.

```bash
uv sync --extra dev
uv run mstlo-bench benchmark
uv run mstlo-bench report
```

Use another TOML file or output directory when needed:

```bash
uv run mstlo-bench benchmark --config configs/benchmark.toml --output-dir results/run
uv run mstlo-bench report --output-dir results/run
```

The TOML config defines robot counts, seeds, workloads, transports, semantics, rates, durations, and ROS settling times. `configs/overnight.toml` is a ten-seed direct/ROS sweep through 1,000 robots. Each point uses the fixed-width progress display with settle, warmup, measure, and analysis phases. Results are appended to `results.jsonl`. The report contains only:

- `latency.csv`
- `latency.md`
- one `latency_overhead_fan_<semantics>.png` per MSTLO semantics

The vendored `robosapiens-trustworthiness-checker` and `multi-robot-runtime-verification` directories are Git subtrees. The checker subtree contains the indexed RoSI routing and explicit benchmark QoS settings used here.
