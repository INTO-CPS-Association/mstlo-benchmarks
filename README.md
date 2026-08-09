# MSTLO reference benchmark

This repository compares MSTLO latency through an in-process direct input path and a ROS 2 input path. Both paths use the same Brownian robot source, properties, algorithm, semantics, and publication schedule. The reported metric is latency overhead:

```text
first valid verdict arrival - earliest time the semantics permits a verdict
```

## Docker-first run

The only host requirements for benchmark execution are **Docker and the Docker Compose plugin**. The image contains ROS 2 Jazzy, the vendored ROS interfaces, the Rust checker and runner, and the Python reporting environment. No Rust, Python, `uv`, ROS, or `colcon` installation is needed on the host.

The shortest working command is:

```bash
docker compose run --rm benchmark quick
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

## Local development

The Docker workflow is the supported reproducible path. Local development remains available when Rust, `uv`, ROS 2, and `colcon` are installed:

```bash
uv sync --extra dev
uv run mstlo-bench benchmark --config configs/benchmark.toml --output-dir results/local-run
uv run mstlo-bench report --output-dir results/local-run
```

Local invocations preserve the incremental ROS-interface and Rust compilation behavior. The `--resume`/`--append` rule also applies locally.

The reported metric is latency overhead. Later RoSI refinements at the same property/timestamp are ignored, so all semantics have the same weighting. Delayed semantics exclude their required waiting period; eager and robustness-interval semantics have no fixed wait. A run fails if a verdict has the wrong payload type. The report contains one CSV, one Markdown report, and one fan plot per configured MSTLO semantic.
