# Synthetic signal

How the cost of monitoring scales with the temporal depth of a formula. A signal is generated, then monitored by the native Rust `mstlo` monitor and by the `mstlo-python` bindings, and the resulting timings are fitted.

By default the sweep is the paper's: four fixed formulas plus three families — *until*, *globally* and *eventually* — whose temporal bound is swept over 51 values, all under four semantics: delayed quantitative, delayed qualitative, eager qualitative, and RoSI. RoSI is capped at bounds of 1000, so it contributes 11 points per family instead of 51. A separate single pass records the number of cached steps each monitor keeps.

Everything in that paragraph is a setting. What is measured — which bounds, which formulas, which signal — is decided by the config and written to `formulas.tsv` in the results, and both monitors are pointed at it; neither carries a catalog of its own any more.

```bash
docker compose run --rm synthetic_signal run
docker compose run --rm synthetic_signal analyze
```

`run` generates the signal and measures; `analyze` produces the regression fits, the Mann-Whitney table and the plots, and finds its own input files. The two are separate so the figures can be redrawn without measuring again. `test` is a third stage, running the shared stage layer's tests and this benchmark's own — the catalog and the signal builders — inside the image.

**The default configuration takes hours.** Check the pipeline first:

```bash
docker compose run --rm synthetic_signal run quick
```

## Configuration

`configs/default.toml` reproduces the measurements the paper reports; `configs/quick.toml` proves the pipeline works and says nothing about performance. Anything set in the environment overrides the file, so a one-off variation needs no new config:

```bash
docker compose run --rm -e SIGNAL_TYPES=chirp,constant -e BOUND_HIGH=2000 \
    synthetic_signal run
```

### The signal

| setting | default | quick | meaning |
| --- | --- | --- | --- |
| `SIGNAL_SIZE` | 20000 | 2000 | samples in the generated signal |
| `SIGNAL_TYPES` | `chirp` | `chirp` | which signals to measure against, comma-separated |
| `SAMPLING_RATE` | 1.0 | | samples per second |
| `FREQUENCY` | 0.01 | | sine frequency, Hz |
| `START_FREQUENCY` | 0.01 | | chirp frequency at the start, Hz |
| `END_FREQUENCY` | 0.0001 | | chirp frequency at the end, Hz |
| `AMPLITUDE` | 1.0 | | what the two ramps run between |
| `CONSTANT_VALUE` | 0.25 | | what the constant holds |

`SIGNAL_TYPES` takes any of `chirp`, `sine`, `linear-increasing`, `linear-decreasing` and `constant`. Naming several measures the whole catalog against each in turn — the run takes correspondingly longer — and each gets its own directory of results, so no CSV ever holds two of them. The ramps run from `-AMPLITUDE` to `+AMPLITUDE` and back the other way, which crosses every threshold the built-in formulas test exactly once; `chirp` and `sine` are the paper's, unchanged.

The default sampling rate of 1.0 Hz makes the timestamps integers, so a bound such as `G[0,1000]` means the same number of steps to every monitor.

### The formulas

| setting | default | quick | meaning |
| --- | --- | --- | --- |
| `BOUND_LOW` | 0 | 0 | first bound of the family sweep |
| `BOUND_HIGH` | 5000 | 500 | last bound of the family sweep |
| `BOUND_STEP` | 100 | 100 | distance between bounds |
| `FIRST_BOUND` | 1 | | what a zero first bound becomes |
| `FORMULA_IDS` | all | all | which built-in formulas to measure |
| `CUSTOM_FORMULAS` | none | none | extra formulas, written out in full |
| `ROSI_MAX_BOUND` | 1000 | | longest interval RoSI is asked to monitor |
| `CACHE_SIZE_FORMULA_IDS` | `1,2,3,4` | | what the cache-size pass covers |

The three families are swept over `BOUND_LOW`, `BOUND_LOW + BOUND_STEP`, … up to `BOUND_HIGH`. A bound of zero is degenerate — `G[0,0] (x > 0.0)` has none of the temporal depth the sweep is measuring — so a sweep starting at zero starts at `FIRST_BOUND` instead. That is the paper's `b[0] += 1`, spelled out.

`FORMULA_IDS` is a comma-separated selection of the built-in seven, empty meaning all of them:

| ID | formula |
| --- | --- |
| 1 | `(x < 0.5) and (x > -0.5)` |
| 2 | `G[0,1000] (x > 0.5 -> F[0,100] (x < 0.0))` |
| 3 | `(x < 0.5) U[0,1000] (x < 0.0)` |
| 4 | `(G[0,100] (x < 0.5)) or (G[100,150] (x > 0.0))` |
| 5 | `(x < 0.0) U[0,b] (x > 0.0)`, one row per bound |
| 6 | `G[0,b] (x > 0.0)`, one row per bound |
| 7 | `F[0,b] (x > 0.0)`, one row per bound |

An ID names a family, not a row: all 51 bounds of the globally sweep are ID 6, and the analysis groups by that.

`CUSTOM_FORMULAS` is a list of specs, in the same syntax, measured alongside the built-ins:

```toml
CUSTOM_FORMULAS = [
    "G[0,50] (x > 0.0)",
    "(x < 0.5) U[0,20] (x > 0.0)",
]
```

They are numbered from 100 upwards and are measured under all four semantics like everything else, so they appear in the result CSVs — but **the figures will not show them**, because the analysis stage plots IDs 5, 6 and 7 and fits nothing else. A spec that does not parse is rejected before the run starts rather than hours into it.

`ROSI_MAX_BOUND` exists because RoSI on a long interval costs far more than the other three semantics; `none` lifts the cap and makes the run very much longer. `CACHE_SIZE_FORMULA_IDS` is the catalog for the separate single cache-size pass, which the families would tell nothing the fixed formulas do not; empty gives it the same catalog as the timings.

### The measurement

| setting | default | quick | meaning |
| --- | --- | --- | --- |
| `M_RUNS` | 50 | 2 | timed repetitions per point |
| `WARMUP_RUNS` | 10 | 0 | untimed repetitions before each point |
| `MWU_FORMULA_IDS` | `1,2,3,4` | | which formulas native and Python are compared on |

`MWU_FORMULA_IDS` belongs to `analyze` rather than `run`. The four fixed formulas are single rows, so one test each says something; a family would mix every bound into one distribution. Empty tests everything measured.

## Output

Every `run` gets a fresh directory under `results/synthetic_signal/`, named after its config, with `latest` pointing at the newest — the layout is the same for all three benchmarks and is described in the [repository README](../../README.md#what-the-three-share). Inside one:

```text
config.toml, metadata.json                    what produced everything here
formulas.tsv                                  what was measured
formulas_cache_size.tsv                       what the cache-size pass covered
signals/signal_20000_chirp.csv                the generated signal
mstlo/chirp/
├── performance_results_M=50.csv              native Rust, summary and _raw
├── python_performance_results_M=50.csv       mstlo-python, summary and _raw
└── cache_size_results_M=1.csv                cached steps per monitor
data_analysis/chirp/
├── regression_fit/regression_fit_results.csv the fitted scaling curves
├── mwu/native_vs_python_mwu.csv              Mann-Whitney U, native vs. Python
└── mstlo_plots/*.pdf                         performance comparison figures
```

A run measuring several signal types has one `mstlo/<type>/` and one `data_analysis/<type>/` per type, and `analyze` repeats itself over each.

`analyze` writes `data_analysis/` into the run it drew from, so the figures always sit beside the measurements they came from.

The cache-size pass reads a counter inside the timed loop, so its timings are not comparable with the ones above and go to their own file. One pass is enough: the step counts are deterministic.

## Layout

```text
benchmarks/synthetic_signal/
├── configs/       the TOML settings below: default, quick
├── run.sh         the measuring stage
├── analyze.sh     the analysing stage
├── formulas.py    the catalog the config builds
├── signals.py     the signal the config builds
└── tests/         what the two above are pinned to
```
