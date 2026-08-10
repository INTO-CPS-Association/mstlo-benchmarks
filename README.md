# MSTLO benchmarks

Three benchmarks for [MSTLO](https://github.com/INTO-CPS-Association/mstlo), each reproducible with a single `docker compose` command. **Docker and the Docker Compose plugin are the only host requirements** — no Rust, Python, `uv`, ROS, `colcon`, or broker installation is needed.

| benchmark | what it measures | command |
|---|---|---|
| **multi-robot** | MSTLO latency overhead, in-process vs. ROS 2 | `docker compose run --rm benchmark run multi_robot quick` |
| **synthetic signal** | how monitoring cost scales with the temporal depth of a formula, across four semantics | `docker compose run --rm bench run synthetic_signal` |
| **incubator** | monitoring a recorded digital-twin temperature trace, with the monitor's memory footprint | `docker compose run --rm bench run incubator` |

Two images back these: multi-robot needs ROS 2 and has its own (`docker/Dockerfile`), while the other two are pure Rust and Python (`docker/Dockerfile.mstlo`). That is why the service name differs; the verb does not.

```bash
docker compose build            # build everything, once
```

Measuring and analysing are separate stages, so figures can be redrawn without re-measuring:

```bash
docker compose run --rm bench run     synthetic_signal
docker compose run --rm bench analyze synthetic_signal
```

Run `docker compose run --rm bench` with no arguments to list the available benchmarks, stages and configs.

## Where the code comes from

Nothing here is a copy-paste. Every benchmarked component is vendored as a `git subtree`, so the exact source that produced a number is in this repository's history:

| subtree | upstream |
|---|---|
| `mstlo/` | [`INTO-CPS-Association/mstlo`](https://github.com/INTO-CPS-Association/mstlo) — the crate, the Python bindings, and the synthetic-signal and incubator benchmark scripts |
| `robosapiens-trustworthiness-checker/` | the checker binary and crate used by the multi-robot benchmark |
| `multi-robot-runtime-verification/` | the Brownian multi-robot simulator |
| `incubator-dt-course/` | [`clagms/IncubatorDTCourse`](https://github.com/clagms/IncubatorDTCourse) — the incubator digital-twin course |
| `example-digital-twin-incubator/` | the course's `incubator_dt` submodule, vendored separately because a subtree does not carry submodules |

Only the thin stage layer under `benchmarks/` (shell scripts, TOML configs) and the Docker files are written by this repository. Nothing in it writes back into a subtree, so `git subtree pull` never has to merge a local edit.

## About the numbers

**These are not the numbers in the MSTLO paper, and they are not meant to match.** The paper's measurements were taken natively on macOS/arm64 with a source-built RTAMT; these run in a Linux container on whatever hardware you have. Absolute timings differ, and so do some ratios — the same monitor measured natively and in a container differed by ~16% in our own comparison. What reproduces here is the shape of the result, not the digits.

RTAMT is deliberately **not** installed. The version the paper compares against is not on PyPI, needs a separate cmake/Boost.Python build for its C++ backend, and needs a fix that is not upstream — three failure modes that would make this repository worse at its one job. The comparison plots against RTAMT therefore do not appear here; the full recipe for reproducing them is in the [mstlo repository](https://github.com/INTO-CPS-Association/mstlo/blob/main/benchmarks/synthetic_signal/README.md#installing-rtamt).

## Multi-robot

Compares MSTLO latency through an in-process direct input path and a ROS 2 input path. Both paths use the same Brownian robot source, properties, algorithm, semantics, and publication schedule. The reported metric is latency overhead:

```text
first valid verdict arrival - earliest time the semantics permits a verdict
```

The shortest working command is:

```bash
docker compose run --rm benchmark run multi_robot quick
```

The command builds the benchmark image first when necessary, allocates a fresh result directory, runs both direct and ROS points, writes a report, and prints the result/report locations. A failed final benchmark point makes the container exit nonzero even though the partial report is still written.

### Build the image

```bash
docker compose build
docker compose run --rm benchmark quick
```

The combined form is also supported:

```bash
docker compose run --rm --build benchmark quick
```

The build is intentionally multi-stage. Compilation happens only during `docker compose build`; benchmark commands use the prebuilt binaries and never download dependencies or compile code.

### Named configurations

```bash
docker compose run --rm benchmark small
docker compose run --rm benchmark paper
docker compose run --rm benchmark overnight
```

Each named command runs its corresponding `configs/<name>.toml` and then generates the report. The `paper` command uses `configs/paper.toml`.

### Results and reports

The repository's `results/` directory is bind-mounted to `/results` in the container. Every named run gets a new directory such as:

```text
results/quick-20260809T120000Z-a1b2c3d4/
├── config.toml
├── metadata.json
├── results.jsonl
├── report/
│   ├── latency.csv
│   ├── latency.md
│   └── latency_overhead_fan_<semantics>.png
└── work/
```

The selected directory is printed before execution and again when it completes. `metadata.json` records the configuration SHA-256, UTC start/completion times, image/repository version values supplied to the image, architecture, visible CPU and memory information, kernel, Python, ROS distribution, and ROS middleware. Fields unavailable on a platform are recorded as `null` where appropriate.

Generate a report for an existing result directory without running the benchmark again:

```bash
docker compose run --rm benchmark report \
  --output-dir /results/quick-20260809T120000Z-a1b2c3d4
```

Report files are written below that result directory by default. Pass `--report-dir /results/my-report` to choose another output location.

### Failures, retries, and reuse

A point that raises an error or violates the benchmark correctness checks is retried up to five times. Only the final row is appended to `results.jsonl`, and its `attempts` field records how many attempts were needed. Direct points still require every expected verdict; ROS points retain the existing 90% transport completeness threshold. Reports identify incomplete and unrun series rather than inventing values.

Named runs always use a fresh directory. A lower-level command refuses to append to a directory that already has `results.jsonl`, preventing accidental duplicate rows and changed report weighting. Reuse must be explicit:

```bash
docker compose run --rm benchmark benchmark \
  --config /opt/mstlo-bench/configs/small.toml \
  --output-dir /results/existing-run \
  --resume
```

The alias `--append` is also accepted. The existing output lock remains active, so concurrent writers fail immediately.

### Custom configurations

The lower-level commands remain available for custom TOML files. For a file in the checkout, mount it read-only and choose an explicit result directory:

```bash
docker compose run --rm \
  -v "$PWD/configs/custom.toml:/tmp/custom.toml:ro" \
  benchmark benchmark \
  --config /tmp/custom.toml \
  --output-dir /results/custom-run

docker compose run --rm benchmark report --output-dir /results/custom-run
```

You can also add a configuration under `configs/`, rebuild the image, and refer to it as `/opt/mstlo-bench/configs/<name>.toml`. The `test` command runs the focused Python tests inside the image:

```bash
docker compose run --rm benchmark test
```

### Linux output ownership

Compose defaults to UID/GID `1000`, which is convenient for the common Linux setup and works through Docker Desktop on macOS and Windows. If a Linux host uses another UID/GID, set them for the run so files under `results/` belong to you:

```bash
HOST_UID="$(id -u)" HOST_GID="$(id -g)" \
  docker compose run --rm benchmark quick
```

No host networking, host IPC, privileged mode, host devices, Docker socket, GPU, X11, EMQX, or desktop ROS installation is used. ROS/DDS communication stays inside the container with localhost-only discovery and a fixed Fast DDS implementation.

## Synthetic signal

Sweeps 51 temporal bounds for each of the until, globally and eventually families across four semantics, timing the native Rust monitor and the Python bindings on a generated chirp signal, then fits the scaling curves.

```bash
docker compose run --rm bench run     synthetic_signal
docker compose run --rm bench analyze synthetic_signal
```

`run` generates the signal and measures; `analyze` produces the regression fits, the Mann-Whitney table and the plots, and finds its input files itself. The default configuration takes **hours**. Check the pipeline first:

```bash
docker compose run --rm bench run synthetic_signal quick
```

## Incubator

Replays a recorded temperature trace from the [incubator digital-twin course](https://github.com/clagms/IncubatorDTCourse) through two STL specifications, times the monitors on it, and records the native monitor's memory footprint after every update.

```bash
docker compose run --rm bench run     incubator
docker compose run --rm bench analyze incubator
```

This works out of the box because the recording used in the paper is committed in the `mstlo/` subtree; `run` copies it in when no fresher one exists.

### Recording a fresh session

The `gather` stage drives the course's real emulator and controller over RabbitMQ and records a new session. The broker is a compose service, the course and its submodule are subtrees, and the two notebook-generated service scripts are committed under `benchmarks/incubator/course-services/` — so there is nothing to clone, extract or step through:

```bash
docker compose run --rm gather gather incubator
```

**This takes about 70 minutes.** The emulator runs in real time at one sample every 3 s, and the box starts at 30 °C, so roughly the first 15 minutes are spent pre-heating into the control band before any useful sample appears. A shorter session that still exercises every phase — pre-heat, warm-up, normal, lid-open — takes about 20 minutes:

```bash
docker compose run --rm gather gather incubator smoke
```

Afterwards `run` picks up the new recording instead of the committed one, and says which it used.

## Configs

Every knob lives in `benchmarks/<benchmark>/configs/*.toml`, one section per stage plus a shared `[common]`. Pass the name as the third argument; the default is `default`:

```bash
docker compose run --rm bench run incubator quick
```

`default` reproduces the measurements the paper reports. `quick` proves the pipeline works and says nothing about performance. Anything set in the environment wins over the file:

```bash
docker compose run --rm -e M_RUNS=7 bench run incubator quick
```

## Results

Everything is written under `results/`, bind-mounted from the host. The two kinds of benchmark use it differently, on purpose:

```text
results/
├── quick-20260809T120000Z-a1b2c3d4/   multi-robot: one fresh directory per run
├── synthetic_signal/                  stage benchmarks: a stable path
└── incubator/
```

A multi-robot run is one self-contained sweep, so each gets its own timestamped directory and `report` is pointed at a specific one. The other two are a *pipeline* — `gather` writes the recording, `run` reads it and writes the measurements, `analyze` reads those and writes the figures — so they need a stable location to hand work between stages. To keep a particular run, name it:

```bash
docker compose run --rm -e RESULTS_DIR=/results/incubator-2026-08-10-A bench run incubator
```

Each `run` and `gather` drops a `metadata.json` next to its output, recording the config and its SHA-256, the effective settings, the toolchain, architecture, CPU and start/finish times. Inside a VM the container only sees the guest's CPU, so pass the real one if it matters:

```bash
MSTLO_BENCH_HOST_CPU="Apple M4 Pro" docker compose run --rm bench run synthetic_signal
```

## Local development

The Docker workflow is the supported reproducible path. Local development remains available when Rust, `uv`, ROS 2, and `colcon` are installed:

```bash
uv sync --extra dev
uv run mstlo-bench benchmark --config configs/benchmark.toml --output-dir results/local-run
uv run mstlo-bench report --output-dir results/local-run
```

Local invocations preserve the incremental ROS-interface and Rust compilation behavior. The `--resume`/`--append` rule also applies locally.

The reported metric is latency overhead. Later RoSI refinements at the same property/timestamp are ignored, so all semantics have the same weighting. Delayed semantics exclude their required waiting period; eager and robustness-interval semantics have no fixed wait. A run fails if a verdict has the wrong payload type. The report contains one CSV, one Markdown report, and one fan plot per configured MSTLO semantic.
