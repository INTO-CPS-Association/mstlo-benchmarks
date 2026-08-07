# MSTLO reference benchmark

This repository compares MSTLO latency with an in-process direct input path and a ROS 2 input path. Both use the same Brownian robot source and the trustworthiness checker runtime.

The reported metric is latency overhead:

```text
first valid verdict arrival - earliest time the semantics permits a verdict
```

There is one sample for each property and logical timestamp. Later RoSI refinements at the same property/timestamp are ignored, so all semantics have the same weighting. Delayed semantics exclude their required waiting period; eager and robustness-interval semantics have no fixed wait. The report shows the median, p95, and p99; lower is better. A run fails if any verdict has the wrong payload type. A direct run also fails if any expected verdict is missing. A ROS run is accepted once 90% of the expected verdicts arrive and is marked incomplete when some are missing.

Direct and ROS use the same simulator, seed, scalar input events, properties, algorithm, semantics, synchronization, and publication schedule. Direct hosts the checker in the runner process. ROS publishes to a standalone checker and collects verdicts in the source process, so its latency additionally includes ROS input and output transport. ROS uses reliable, volatile, bounded `KEEP_LAST` queues: depth 64 for inputs and 256 for verdicts. Each benchmark invocation uses a unique ROS topic namespace, preventing concurrently running sweeps from exchanging inputs or verdicts.

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

The TOML config defines robot counts, seeds, workloads, transports, semantics, rates, durations, and ROS settling times. `configs/overnight.toml` is a ten-seed direct/ROS sweep through 1,000 robots. Each point uses the fixed-width progress display with settle, warmup, measure, and analysis phases. A failed point is retried up to five times before the sweep records it as failed; only the final attempt is appended, with an `attempts` count. Results are appended to `results.jsonl`; a result directory is locked for the duration of a sweep so concurrent writers fail immediately instead of corrupting or cross-contaminating a run. Reports mark unrun, unconfigured, and partial series. A robot count is plotted only after every configured seed succeeds, so missing data remains a gap rather than a misleading line. The report contains only:

- `latency.csv`
- `latency.md`
- one `latency_overhead_fan_<semantics>.png` per MSTLO semantics

The vendored `robosapiens-trustworthiness-checker` and `multi-robot-runtime-verification` directories are Git subtrees. The checker subtree contains the indexed RoSI routing and explicit benchmark QoS settings used here.
