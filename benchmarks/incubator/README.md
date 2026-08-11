# Incubator

Monitoring a real digital twin's temperature trace. A recorded session from the [incubator digital-twin course](https://github.com/clagms/IncubatorDTCourse) is replayed through two STL specifications; the monitors are timed on it, and the native monitor's memory footprint is recorded after every update.

```bash
docker compose run --rm incubator run
docker compose run --rm incubator analyze
```

This works out of the box: the recording used in the paper is committed in the `mstlo/` subtree, and `run` copies it in when there has been no `gather` — it says which one it used, in the log and in the metadata. `analyze` draws the figures from the newest `run`, or from whichever one it is named:

```bash
docker compose run --rm incubator analyze quick-20260809T120000Z-a1b2c3d4
```

## Configuration

`configs/default.toml` reproduces the measurements committed under the mstlo checkout; `configs/quick.toml` proves the pipeline works and says nothing about performance; `configs/smoke.toml` is the shortest useful `gather` (see below). Anything set in the environment overrides the file.

| setting | default | quick | meaning |
| --- | --- | --- | --- |
| `PHASES` | `normal,lid_open` | same | which phases of the recording every stage sees; empty is the whole session (preheat, warmup, normal, lid_open) |
| `M_RUNS` | 50 | 2 | timed repetitions per point |
| `WARMUP_RUNS` | 1 | 0 | untimed repetitions before each point |
| `MEMORY_RUNS` | 50 | 3 | untimed passes the memory median is taken over |

## Output

Every `run` gets a fresh directory under `results/incubator/`, named after its config, with `latest` pointing at the newest — the layout is the same for all three benchmarks and is described in the [repository README](../../README.md#what-the-three-share). Inside one:

```text
signal.csv                          the recording being replayed, copied in
config.toml, metadata.json          what produced everything here
dataset.csv, verdicts.csv, latency.csv   replay output and derived dataset
benchmark.csv                       mstlo-python timings
benchmark_rust.csv                  native Rust timings and memory summary
benchmark_rust_memory.csv           native footprint after every update
benchmark_rust_cache_size_M=1.csv   native cached steps (M = 1)
figures/                            written by analyze, into the run it drew from
```

The cache-size pass reads a counter after every update, inside the timed loop, so its timings are not the ones in `benchmark_rust.csv` and go to their own file. One pass is enough: the sizes are deterministic.

## Recording a fresh session

The `gather` stage drives the course's real emulator and controller over RabbitMQ and records a new session. The broker is a compose service this one depends on, the course and its submodule are vendored as subtrees, and the two notebook-generated service scripts are committed under `course-services/` — so there is nothing to clone, extract or step through:

```bash
docker compose run --rm incubator gather
```

**This takes about 70 minutes.** The emulator runs in real time at one sample every 3 s, and the box starts at 30 °C, so roughly the first 15 minutes go into pre-heating up to the control band before any useful sample appears. A shorter session that still exercises every phase — pre-heat, warm-up, normal, lid-open — takes about 20 minutes:

```bash
docker compose run --rm incubator gather smoke
```

A `gather` gets a fresh directory of its own, exactly as a `run` does, and afterwards every `run` copies its `signal.csv` in instead of the committed one — the newest recording wins, and the run's metadata names the one it used. To replay an older recording, copy its `signal.csv` into a result directory and point `run` at it with `RESULTS_DIR`.

`gather` has its own knobs: `WARMUP_CYCLES` (1), `NORMAL_CYCLES` (3) and `LID_DURATION` (1200 s) — `smoke` sets 0, 1 and 60.

Because `gather` is a stage of this service rather than a service of its own, the image carries the course and its interpreter, and compose starts the broker for every incubator command. `run` and `analyze` ignore both.
