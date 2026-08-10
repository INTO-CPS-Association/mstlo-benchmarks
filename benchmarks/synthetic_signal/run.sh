#!/usr/bin/env sh
#
# Time mstlo (native and Python) over a generated chirp signal.  Measuring only
# -- analyze.sh turns the CSVs into the tables and figures.
#
# The mstlo paper also compares against RTAMT.  This image ships no RTAMT, so
# rtamt_benchmark.py is never invoked here; see ../requirements.txt.

set -e

SRC="$MSTLO_SRC/synthetic_signal"       # the mstlo repo's scripts
MSTLO_DIR="${MSTLO_DIR:?set MSTLO_DIR}" # the Rust crate
RESULTS_DIR="${RESULTS_DIR:?set RESULTS_DIR}"

M_RUNS="${M_RUNS:-50}"
WARMUP_RUNS="${WARMUP_RUNS:-10}"
SIGNAL_SIZE="${SIGNAL_SIZE:-20000}"

SIGNAL="$RESULTS_DIR/signal_${SIGNAL_SIZE}_chirp.csv"
CACHE_SIZE_RESULTS="$RESULTS_DIR/mstlo/cache_size_results_M=1.csv"
CACHE_SIZE_RESULTS_RAW="$RESULTS_DIR/mstlo/cache_size_results_M=1_raw.csv"
NATIVE_RESULTS="$RESULTS_DIR/mstlo/performance_results_M=${M_RUNS}.csv"
NATIVE_RESULTS_RAW="$RESULTS_DIR/mstlo/performance_results_M=${M_RUNS}_raw.csv"
PY_RESULTS="$RESULTS_DIR/mstlo/python_performance_results_M=${M_RUNS}.csv"
PY_RESULTS_RAW="$RESULTS_DIR/mstlo/python_performance_results_M=${M_RUNS}_raw.csv"

mkdir -p "$RESULTS_DIR/mstlo"

echo "=== 1/3  signal (N = $SIGNAL_SIZE) ==="
# The default sampling-rate=1.0 Hz produces integer timesteps 0,1,2,...
# This means formula bounds (e.g. G[0,1000]) are numerically identical
# between mstlo (Duration-based, seconds) and RTAMT (discrete step indices).
python3 "$SRC/signal_generation/signal_generator.py" \
	--num-samples "$SIGNAL_SIZE" --output-path "$SIGNAL" --signal-type chirp

echo
echo "=== 2/3  mstlo-python, M = $M_RUNS ==="
python3 "$SRC/python_benchmark.py" \
	--signal-csv "$SIGNAL" \
	--m-runs "$M_RUNS" \
	--warmup-runs "$WARMUP_RUNS" \
	--output "$PY_RESULTS" \
	--output-raw "$PY_RESULTS_RAW" \
	--overwrite

echo
echo "=== 3/3  native Rust, cache sizes then timings (M = $M_RUNS) ==="
(
	cd "$MSTLO_DIR"

	# The cache counter is read inside the timed loop, so these timings are not
	# the ones below and go to their own file.  One pass is enough: the step
	# counts are deterministic.
	#
	# OUTPUT_RAW_CSV is set even though nothing reads the raw cache-size file:
	# unset, the bench falls back to a default path inside the mstlo checkout,
	# which is deliberately not writable here.
	WARMUP_RUNS=0 M_RUNS=1 FORMULA_IDS="1,2,3,4" \
		SIGNAL_PATH="$SIGNAL" \
		OUTPUT_CSV="$CACHE_SIZE_RESULTS" \
		OUTPUT_RAW_CSV="$CACHE_SIZE_RESULTS_RAW" \
		cargo bench --offline --bench paper_benchmark --features track-cache-size

	WARMUP_RUNS="$WARMUP_RUNS" M_RUNS="$M_RUNS" \
		SIGNAL_PATH="$SIGNAL" \
		OUTPUT_CSV="$NATIVE_RESULTS" \
		OUTPUT_RAW_CSV="$NATIVE_RESULTS_RAW" \
		cargo bench --offline --bench paper_benchmark
)

echo
echo "done. measurements in $RESULTS_DIR"
