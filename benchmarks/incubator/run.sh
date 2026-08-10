#!/usr/bin/env sh
#
# Everything downstream of the recording:
#
#   1. replay the signal through the monitors and derive the dataset
#   2. time mstlo-python on that signal
#   3. time the native Rust monitor, record its memory footprint, and take a
#      separate single pass for the cache sizes
#
# The signal comes from the newest gather, or from the recording committed in
# the mstlo checkout when there has not been one.

set -e

SRC="$MSTLO_SRC/incubator"              # the mstlo repo's scripts
MSTLO_DIR="${MSTLO_DIR:?set MSTLO_DIR}" # the Rust crate
RESULTS_DIR="${RESULTS_DIR:?set RESULTS_DIR}"

M_RUNS="${M_RUNS:-50}"
WARMUP_RUNS="${WARMUP_RUNS:-1}"

# Which phases of the recording every stage sees, comma-separated.  Empty is the
# whole session: the monitors then get one uninterrupted signal, and the replay,
# the datasets, the benchmarks and the figures all cover the same samples.
PHASES="${PHASES-normal,lid_open}"

SIGNAL="$RESULTS_DIR/signal.csv"

# The recording comes from the newest gather, and the committed one only when
# there has been no gather.  Either way it is copied in and noted in the
# metadata, so the measurements and the samples they came from stay together.
if [ ! -f "$SIGNAL" ]; then
	RECORDING=$(python3 "$BENCH_ROOT/results.py" latest incubator --stage gather 2>/dev/null || true)
	if [ -n "$RECORDING" ] && [ -f "$RECORDING/signal.csv" ]; then
		RECORDING="$RECORDING/signal.csv"
		echo "using the recording from $(dirname "$RECORDING")"
	else
		RECORDING="$SRC/data/signal.csv"
		echo "using the committed recording"
	fi
	cp "$RECORDING" "$SIGNAL"
	python3 "$BENCH_ROOT/metadata.py" input recording "$RECORDING"
else
	echo "using the recording already in $RESULTS_DIR"
fi

if [ ! -f "$MSTLO_DIR/Cargo.toml" ]; then
	echo "no crate at $MSTLO_DIR -- set MSTLO_DIR" >&2
	exit 1
fi

# The Python stages take the phases as separate words, the Rust one as the
# comma-separated string it already parses.  A typo would otherwise leave every
# stage with an empty signal, so each name is checked against the recording.
PHASE_ARGS=""
if [ -n "$PHASES" ]; then
	for phase in $(echo "$PHASES" | tr ',' ' '); do
		if ! awk -F, -v want="$phase" '
			NR == 1 { for (i = 1; i <= NF; i++) if ($i == "phase") col = i; next }
			col && $col == want { found = 1; exit }
			END { exit !found }
		' "$SIGNAL"; then
			echo "no samples labelled '$phase' in $SIGNAL" >&2
			exit 1
		fi
	done
	PHASE_ARGS="--phases $(echo "$PHASES" | tr ',' ' ')"
	SCOPE="$PHASES"
else
	SCOPE="all phases"
fi

echo "=== 1/3  monitors and datasets ($SCOPE) ==="

python3 "$SRC/replay.py" --datadir "$RESULTS_DIR" --outdir "$RESULTS_DIR" $PHASE_ARGS

python3 "$SRC/process_results.py" --datadir "$RESULTS_DIR" $PHASE_ARGS

echo
echo "=== 2/3  mstlo-python, M = $M_RUNS ==="

python3 "$SRC/benchmark.py" --datadir "$RESULTS_DIR" --outdir "$RESULTS_DIR" \
	--m-runs "$M_RUNS" --warmup-runs "$WARMUP_RUNS" \
	$PHASE_ARGS --no-rtamt

echo
echo "=== 3/3  native Rust, timings (M = $M_RUNS), memory and cache sizes ==="
(
	cd "$MSTLO_DIR"
	M_RUNS="$M_RUNS" WARMUP_RUNS="$WARMUP_RUNS" \
		SIGNAL_PATH="$SIGNAL" \
		PHASES="$PHASES" \
		OUTPUT_CSV="$RESULTS_DIR/benchmark_rust.csv" \
		OUTPUT_RAW_CSV="$RESULTS_DIR/benchmark_rust_runs.csv" \
		OUTPUT_MEMORY_CSV="$RESULTS_DIR/benchmark_rust_memory.csv" \
		cargo bench --offline --bench incubator_benchmark

	# The cache counter is read after every update, inside the timed loop, so
	# these timings are not the ones above and go to their own file.  One pass
	# is enough -- the sizes are deterministic -- and the memory profiling is
	# off here because the run above already did it.
	M_RUNS=1 WARMUP_RUNS=0 MEMORY_RUNS=0 \
		SIGNAL_PATH="$SIGNAL" \
		PHASES="$PHASES" \
		OUTPUT_CSV="$RESULTS_DIR/benchmark_rust_cache_size_M=1.csv" \
		OUTPUT_RAW_CSV="$RESULTS_DIR/benchmark_rust_cache_size_M=1_raw.csv" \
		cargo bench --offline --bench incubator_benchmark --features track-cache-size
)

echo
echo "done. measurements in $RESULTS_DIR:"
echo "  benchmark.csv                       mstlo-python"
echo "  benchmark_rust.csv                  native Rust timings and memory summary"
echo "  benchmark_rust_memory.csv           native Rust footprint after every update"
echo "  benchmark_rust_cache_size_M=1.csv   native Rust cached steps (M = 1)"
