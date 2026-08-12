# Multi-robot

MSTLO latency through an in-process direct input path and a ROS 2 input path. Both paths use the same Brownian robot source, properties, algorithm, semantics, and publication schedule. Two metrics are calculated from each first-result sample:

```text
latency overhead     = max(0, time to first result - semantics baseline)
time to first result = first valid result arrival - publication of its evaluation timestamp
```

Delayed and eager semantics use the property horizon as their latency-overhead baseline; RoSI uses zero. The report tables contain both metrics, while plots show latency overhead. Later RoSI refinements at the same property/timestamp are ignored, so every semantics is weighted equally. A run fails if a result has the wrong payload type.

This is the one benchmark that needs ROS 2, so its image is built by `docker/Dockerfile` rather than the one the other two share. Everything else about running it is what they do — the compose service is the benchmark, and a command names the stage:

```bash
docker compose run --rm multi_robot run     quick
docker compose run --rm multi_robot analyze
```

`run` allocates a fresh result directory, measures both the direct and the ROS points, and prints where everything went; `analyze` turns that into the report. A failed benchmark point makes the container exit nonzero, and the measurements it did take are still there to analyse.

## Layout

```text
benchmarks/multi_robot/
├── configs/       the TOML suites: default, quick, small, overnight
├── run.sh         the measuring stage, a thin wrapper over the driver
├── analyze.sh     the analysing stage, the same
├── mstlo_bench/   the Python driver (the mstlo-bench CLI)
├── runner/        the Rust runner: robot simulation, transports, timing
└── tests/         unit tests for the driver
```

The runner links the `robosapiens-trustworthiness-checker` subtree at the repository root, which supplies the checker binary the ROS path drives.

Both binaries monitor with the vendored `mstlo/` subtree, so this benchmark measures the same source as the other two. The runner depends on it by path and carries a `[patch.crates-io]` for the copy the checker crate asks the registry for, so only one `mstlo` is ever linked into the runner binary. The checker binary is built on its own, and is patched the same way by [`docker/cargo-config.toml`](../../docker/cargo-config.toml), which the image installs as `/src/.cargo/config.toml` — patching from inside the subtree, or from the repository root, would mean editing or silently re-locking a subtree. The checker is therefore built without `--locked`: its committed lock still pins the registry copy, and the patch necessarily re-locks that one entry. A checker built outside the image, by the local-development path below, gets the registry copy.

## Build the image

```bash
docker compose build
docker compose run --rm multi_robot run quick
```

The combined form works too:

```bash
docker compose run --rm --build multi_robot run quick
```

The build is deliberately multi-stage. Compilation happens only during `docker compose build`; benchmark commands use the prebuilt binaries and never download dependencies or compile code.

## Named configurations

```bash
docker compose run --rm multi_robot run small
docker compose run --rm multi_robot run overnight
```

The config names a file under `configs/`. `quick` proves the pipeline works and says nothing about performance; `default` — used when no config is named — runs the sweep the paper reports.

## Results and reports

The repository's `results/` directory is bind-mounted to `/results` in the container, and every run gets a new directory below it — the same layout the other two benchmarks use:

```text
results/multi_robot/
├── quick-20260809T120000Z-a1b2c3d4/
│   ├── config.toml
│   ├── metadata.json
│   ├── results.jsonl
│   ├── report/
│   │   ├── latency.csv
│   │   ├── latency.md
│   │   └── latency_overhead_fan_<semantics>.png
│   └── work/
└── latest -> quick-20260809T120000Z-a1b2c3d4
```

The directory is printed when the stage starts. The report is one CSV, one Markdown report, and one latency-overhead plot per configured MSTLO semantics. The tables include time to first result for eager-versus-delayed comparison.

`analyze` writes into the newest run, so a report can be redrawn at any time without measuring again. Name a run — or a config, or `latest`, or a path — to report on that one instead, and `REPORT_DIR` puts the files somewhere else:

```bash
docker compose run --rm multi_robot analyze small
docker compose run --rm multi_robot analyze quick-20260809T120000Z-a1b2c3d4
docker compose run --rm -e REPORT_DIR=/results/my-report multi_robot analyze
```

`metadata.json` records what produced the numbers, in the shape all three benchmarks use: see the [repository README](../../README.md#what-the-three-share). ROS distribution and middleware are in there too; fields a platform cannot supply are `null`.

## Failures, retries, and reuse

A point that raises an error or violates the correctness checks is retried up to five times. Only the final row is appended to `results.jsonl`, and its `attempts` field records how many attempts were needed. Direct points still require every expected verdict; ROS points retain the 90% transport completeness threshold. Reports identify incomplete and unrun series rather than inventing values.

A run always gets a fresh directory, so there is normally nothing to append to. Pointed at an existing one, the driver refuses to append to results that are already there, which would otherwise duplicate rows and silently reweight the report. Retrying into a run that stopped partway has to be asked for:

```bash
docker compose run --rm \
  -e RESULTS_DIR=/results/multi_robot/small-20260809T120000Z-a1b2c3d4 -e RESUME=1 \
  multi_robot run small
```

The output lock stays active, so concurrent writers fail immediately.

## Custom configurations

`configs/` is bind-mounted into the image, so a configuration added there — or an edit to one already there — is picked up by the next stage and named like any other, with no rebuild:

```bash
docker compose run --rm multi_robot run custom
```

The unit tests — the driver's, and the shared stage layer's — run inside the image with:

```bash
docker compose run --rm multi_robot test
```

## Linux output ownership

Compose defaults to UID/GID `1000`, which suits the common Linux setup and works through Docker Desktop on macOS and Windows. On a Linux host with another UID/GID, set them for the run so files under `results/` belong to you:

```bash
HOST_UID="$(id -u)" HOST_GID="$(id -g)" \
  docker compose run --rm multi_robot run quick
```

No host networking, host IPC, privileged mode, host devices, Docker socket, GPU, X11, EMQX, or desktop ROS installation is used. ROS/DDS communication stays inside the container with localhost-only discovery and a fixed Fast DDS implementation.

## Local development

The Docker workflow is the supported reproducible path. Local runs remain available when Rust, `uv`, ROS 2, and `colcon` are installed — from the repository root:

```bash
uv sync --extra dev
source /opt/ros/jazzy/setup.bash
BENCH=multi_robot benchmarks/entrypoint.sh run     quick
BENCH=multi_robot benchmarks/entrypoint.sh analyze
```

The same entrypoint, the same layout under `results/`; only the ROS environment has to be arranged by hand, and `RESULTS_ROOT` defaults to the repository's own `results/` rather than `/results`. The driver underneath can also be called directly, which is what the stage scripts do:

```bash
uv run mstlo-bench benchmark --config benchmarks/multi_robot/configs/quick.toml \
  --output-dir results/multi_robot/local-run
uv run mstlo-bench report --output-dir results/multi_robot/local-run
```

Local invocations keep the incremental ROS-interface and Rust compilation behaviour.
