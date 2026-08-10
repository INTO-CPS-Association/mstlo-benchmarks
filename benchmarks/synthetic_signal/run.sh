#!/usr/bin/env sh
#
# Time mstlo (native and Python) over generated signals.  Measuring only --
# analyze.sh turns the CSVs into the tables and figures.
#
# A run measures one catalog of formulas against one or more signals.  Both are
# built here, from the config: formulas.py writes the catalog once, signals.py
# generates each signal, and the two benches are pointed at them.  Neither bench
# decides what to measure any more, which is what keeps the native and the
# Python numbers about the same specs.
#
# Every signal type gets a directory of its own under mstlo/, so no CSV ever
# holds two of them and the analysis never has to tell them apart.

set -e

SRC="$MSTLO_SRC/synthetic_signal"       # the mstlo repo's scripts
MSTLO_DIR="${MSTLO_DIR:?set MSTLO_DIR}" # the Rust crate
RESULTS_DIR="${RESULTS_DIR:?set RESULTS_DIR}"
STAGE_DIR="$(cd "$(dirname "$0")" && pwd)"

M_RUNS="${M_RUNS:-50}"
WARMUP_RUNS="${WARMUP_RUNS:-10}"

# The signal.  SIGNAL_TYPES is a list: every type named is generated and
# measured in turn, and the run takes correspondingly longer.
SIGNAL_SIZE="${SIGNAL_SIZE:-20000}"
SIGNAL_TYPES="${SIGNAL_TYPES:-chirp}"
SAMPLING_RATE="${SAMPLING_RATE:-1.0}"
FREQUENCY="${FREQUENCY:-0.01}"
START_FREQUENCY="${START_FREQUENCY:-0.01}"
END_FREQUENCY="${END_FREQUENCY:-0.0001}"
AMPLITUDE="${AMPLITUDE:-1.0}"
CONSTANT_VALUE="${CONSTANT_VALUE:-0.25}"

# The formulas.  The three families -- until, globally, eventually -- are swept
# over BOUND_LOW, BOUND_LOW + BOUND_STEP, ... up to BOUND_HIGH; FIRST_BOUND is
# what a zero first bound becomes, since G[0,0] has no temporal depth to measure.
BOUND_LOW="${BOUND_LOW:-0}"
BOUND_HIGH="${BOUND_HIGH:-5000}"
BOUND_STEP="${BOUND_STEP:-100}"
FIRST_BOUND="${FIRST_BOUND:-1}"

# Which of the built-in 1-7 to measure, empty being all of them, plus anything
# written out by hand.  Custom formulas are numbered from 100 and are measured
# like the rest, but the analysis stage only fits and plots IDs 5, 6 and 7.
FORMULA_IDS="${FORMULA_IDS:-}"
CUSTOM_FORMULAS="${CUSTOM_FORMULAS:-}"

# RoSI costs far more than the other three semantics on a long interval, so it
# is not asked to monitor one.  `none` lifts the cap.
ROSI_MAX_BOUND="${ROSI_MAX_BOUND:-1000}"

# The cache-size pass is a separate, single pass and does not need the whole
# sweep; empty gives it the same catalog as the timings.
CACHE_SIZE_FORMULA_IDS="${CACHE_SIZE_FORMULA_IDS-1,2,3,4}"

FORMULAS="$RESULTS_DIR/formulas.tsv"
CACHE_SIZE_FORMULAS="$RESULTS_DIR/formulas_cache_size.tsv"

build_formulas() {
	python3 "$STAGE_DIR/formulas.py" \
		--output "$1" \
		--bound-low "$BOUND_LOW" \
		--bound-high "$BOUND_HIGH" \
		--bound-step "$BOUND_STEP" \
		--first-bound "$FIRST_BOUND" \
		--formula-ids "$2" \
		--custom "$CUSTOM_FORMULAS"
}

echo "=== formulas ==="
build_formulas "$FORMULAS" "$FORMULA_IDS"
if [ -n "$CACHE_SIZE_FORMULA_IDS" ]; then
	build_formulas "$CACHE_SIZE_FORMULAS" "$CACHE_SIZE_FORMULA_IDS"
else
	CACHE_SIZE_FORMULAS="$FORMULAS"
fi

# One signal type at a time, each one measured the same way.  The heading counts
# them so a sweep of several says where it is.
TOTAL=$(echo "$SIGNAL_TYPES" | tr ',' ' ' | wc -w | tr -d ' ')
INDEX=0

for TYPE in $(echo "$SIGNAL_TYPES" | tr ',' ' '); do
	INDEX=$((INDEX + 1))
	SIGNAL="$RESULTS_DIR/signals/signal_${SIGNAL_SIZE}_${TYPE}.csv"
	OUT="$RESULTS_DIR/mstlo/$TYPE"
	mkdir -p "$OUT"

	echo
	echo "=== signal $INDEX/$TOTAL: $TYPE (N = $SIGNAL_SIZE) ==="
	# The default sampling rate of 1.0 Hz produces integer timesteps 0,1,2,...
	# This means formula bounds (e.g. G[0,1000]) are numerically identical
	# between mstlo (Duration-based, seconds) and RTAMT (discrete step indices).
	python3 "$STAGE_DIR/signals.py" \
		--output "$SIGNAL" \
		--num-samples "$SIGNAL_SIZE" \
		--signal-type "$TYPE" \
		--sampling-rate "$SAMPLING_RATE" \
		--frequency "$FREQUENCY" \
		--start-frequency "$START_FREQUENCY" \
		--end-frequency "$END_FREQUENCY" \
		--amplitude "$AMPLITUDE" \
		--value "$CONSTANT_VALUE"

	echo
	echo "--- mstlo-python, M = $M_RUNS ---"
	python3 "$SRC/python_benchmark.py" \
		--signal-csv "$SIGNAL" \
		--formulas-tsv "$FORMULAS" \
		--rosi-max-bound "$ROSI_MAX_BOUND" \
		--m-runs "$M_RUNS" \
		--warmup-runs "$WARMUP_RUNS" \
		--output "$OUT/python_performance_results_M=${M_RUNS}.csv" \
		--output-raw "$OUT/python_performance_results_M=${M_RUNS}_raw.csv" \
		--overwrite

	echo
	echo "--- native Rust, cache sizes then timings (M = $M_RUNS) ---"
	(
		cd "$MSTLO_DIR"

		# The cache counter is read inside the timed loop, so these timings are
		# not the ones below and go to their own file.  One pass is enough: the
		# step counts are deterministic.
		#
		# OUTPUT_RAW_CSV is set even though nothing reads the raw cache-size
		# file: unset, the bench falls back to a default path inside the mstlo
		# checkout, which is deliberately not writable here.
		WARMUP_RUNS=0 M_RUNS=1 \
			FORMULAS_TSV="$CACHE_SIZE_FORMULAS" \
			ROSI_MAX_BOUND="$ROSI_MAX_BOUND" \
			SIGNAL_PATH="$SIGNAL" \
			OUTPUT_CSV="$OUT/cache_size_results_M=1.csv" \
			OUTPUT_RAW_CSV="$OUT/cache_size_results_M=1_raw.csv" \
			cargo bench --offline --bench paper_benchmark --features track-cache-size

		WARMUP_RUNS="$WARMUP_RUNS" M_RUNS="$M_RUNS" \
			FORMULAS_TSV="$FORMULAS" \
			ROSI_MAX_BOUND="$ROSI_MAX_BOUND" \
			SIGNAL_PATH="$SIGNAL" \
			OUTPUT_CSV="$OUT/performance_results_M=${M_RUNS}.csv" \
			OUTPUT_RAW_CSV="$OUT/performance_results_M=${M_RUNS}_raw.csv" \
			cargo bench --offline --bench paper_benchmark
	)
done

echo
echo "done. measurements in $RESULTS_DIR"
