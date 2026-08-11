# MSTLO benchmarks

Three benchmarks for [MSTLO](https://github.com/INTO-CPS-Association/mstlo), each reproducible with a single `docker compose` command. **Docker and the Docker Compose plugin are the only host requirements** — no Rust, Python, `uv`, ROS, `colcon`, or broker installation is needed.

| benchmark | what it measures | run it |
| --- | --- | --- |
| [**multi-robot**](benchmarks/multi_robot/README.md) | MSTLO latency overhead, in-process vs. ROS 2 | `docker compose run --rm benchmark run multi_robot` |
| [**synthetic signal**](benchmarks/synthetic_signal/README.md) | how monitoring cost scales with the temporal depth of a formula, across four semantics | `docker compose run --rm bench run synthetic_signal` |
| [**incubator**](benchmarks/incubator/README.md) | monitoring a recorded digital-twin temperature trace, plus the monitor's memory footprint | `docker compose run --rm bench run incubator` |

Each one is a directory under `benchmarks/` with its own README, configs and stage scripts.

## Getting started

```bash
docker compose build            # build everything, once
```

Measuring and analysing are separate stages, so figures can be redrawn without re-measuring:

```bash
docker compose run --rm bench run     synthetic_signal
docker compose run --rm bench analyze synthetic_signal
```

Run either service with no arguments to list the benchmarks it has, their stages and their configs.

Two images back the three benchmarks: multi-robot needs ROS 2 and has its own (`docker/Dockerfile`, compose service `benchmark`), while the other two are pure Rust and Python (`docker/Dockerfile.mstlo`, compose service `bench`, plus `gather` for re-recording the incubator session).

## Layout

```text
benchmarks/
├── multi_robot/        stage scripts, configs, the Rust runner and its driver
├── synthetic_signal/   stage scripts, configs, the signal and formula builders
├── incubator/          stage scripts, configs, course services
├── entrypoint.sh       the procedure all three share: what a stage is, which
├── config.py           directory it gets, and what is recorded about it
├── metadata.py
├── results.py
└── tests/              tests for that procedure, run inside both images

docker/                 the two Dockerfiles and the cargo patch they apply
results/                everything any benchmark writes, bind-mounted
```

Everything else at the top level is a vendored upstream checkout — see [where the code comes from](#where-the-code-comes-from).

## What the three share

**Configs.** Every knob lives in `benchmarks/<benchmark>/configs/*.toml`. Pass the name as the last argument; the default is `default`, and every benchmark also has a `quick` that proves the pipeline works and says nothing about performance:

```bash
docker compose run --rm bench run incubator quick
```

The `configs/` directories are bind-mounted from the working tree, so editing a config — or adding one — takes effect on the next stage. Everything else in the image is code and still needs `docker compose build`.

Anything set in the environment wins over the file:

```bash
docker compose run --rm -e M_RUNS=7 bench run incubator quick
```

**Results.** Everything is written under `results/`, bind-mounted from the host, and every benchmark uses it the same way:

```text
results/
└── <benchmark>/
    ├── <config>-<UTC timestamp>-<id>/   one measuring stage, everything it produced
    └── latest -> the newest of them
```

A measuring stage — `run`, or the incubator's `gather` — always gets a fresh directory, so re-running never overwrites measurements you still have and never mixes two runs into one set of numbers. An analysing stage — `analyze` — writes its figures back into the run it drew them from, so a run and everything derived from it stay together. It takes the newest run unless told otherwise, and the last argument is how you tell it — a config, or the run itself:

```bash
docker compose run --rm bench analyze incubator                        # the newest run
docker compose run --rm bench analyze incubator quick                  # the newest quick run
docker compose run --rm bench analyze incubator default-20260809T1200Z-a1b2c3d4
docker compose run --rm bench analyze incubator /results/incubator/somewhere-else
```

A run is named in the header its stage prints, which is the name to type to come back to it; `latest` is a name too, and so is any path. `RESULTS_DIR` still overrides everything, for stages that take no such argument:

```bash
docker compose run --rm -e RESULTS_DIR=/results/incubator/keep-this bench run incubator
```

**Metadata.** Every stage appends to the `metadata.json` in the directory it wrote to: the config and its SHA-256, the effective settings, what it read from elsewhere, start and finish times, and how it ended, alongside one record of the machine — toolchain, architecture, CPU, memory limit, kernel, and the ROS distribution where there is one. The config file itself is copied in beside it.

## Where the code comes from

Every benchmarked component is vendored as a `git subtree`:

| subtree | upstream | link |
| --- | --- | --- |
| `mstlo/` | [`INTO-CPS-Association/mstlo`](https://github.com/INTO-CPS-Association/mstlo) — the crate, the Python bindings, and the synthetic-signal and incubator benchmark scripts | [GitHub](https://github.com/INTO-CPS-Association/mstlo) |
| `robosapiens-trustworthiness-checker/` | the checker binary and crate used by the multi-robot benchmark | [GitHub](https://github.com/INTO-CPS-Association/robosapiens-trustworthiness-checker) |
| `multi-robot-runtime-verification/` | the Brownian multi-robot simulator | [GitHub](https://github.com/INTO-CPS-Association/multi-robot-runtime-verification) |
| `incubator-dt-course/` | the incubator digital-twin course | [GitHub](https://github.com/clagms/IncubatorDTCourse) |
| `example-digital-twin-incubator/` | the course's `incubator_dt` submodule, vendored separately because a subtree does not carry submodules |[GitHub](https://github.com/INTO-CPS-Association/example_digital-twin_incubator/tree/master)|


<!-- ## About the numbers

RTAMT is deliberately **not** installed. The version the paper compares against is not on PyPI, needs a separate cmake/Boost.Python build for its C++ backend, and needs a fix that is not upstream — three failure modes that would make this repository worse at its one job. The comparison plots against RTAMT therefore do not appear here; the full recipe for reproducing them is in the [mstlo repository](https://github.com/INTO-CPS-Association/mstlo/blob/main/benchmarks/synthetic_signal/README.md#installing-rtamt). -->
