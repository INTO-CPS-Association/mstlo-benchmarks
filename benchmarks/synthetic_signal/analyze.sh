#!/usr/bin/env sh
#
# Turn whatever measurements are in $RESULTS_DIR into the tables and figures.
#
# The run stage puts each signal type it measured in its own directory under
# mstlo/, so this one repeats itself once per directory it finds and writes each
# set of figures to data_analysis/<signal type>/.  A run of one signal type --
# the default -- therefore still produces exactly one of everything.
#
# This image ships no RTAMT, so the comparisons against it -- the combined
# performance_comparison_w_rtamt plot, two of the three Mann-Whitney tests, and
# all 11 rtamt_plots -- have no data and are not produced.  Everything measuring
# mstlo and mstlo-python is here in full.

set -e

ANALYSIS="$MSTLO_SRC/synthetic_signal/data_analysis"
RESULTS_DIR="${RESULTS_DIR:?set RESULTS_DIR}"

# Which formulas the native-versus-Python test covers.  The four fixed ones by
# default: they are single rows, so one test each says something, where a family
# would mix 51 different bounds into one distribution.  Empty tests everything.
MWU_FORMULA_IDS="${MWU_FORMULA_IDS-1,2,3,4}"

# The run stage names its files after the M it used, so they are found rather
# than reconstructed -- analyze does not need to know how the data was made.
# Only the raw files are matched, because their suffix is unambiguous; the
# summary next to each one is the same name without it.
raw_for() {
	# shellcheck disable=SC2086  # deliberate glob expansion
	set -- $1
	if [ "$#" -ne 1 ] || [ ! -f "$1" ]; then
		echo "expected exactly one match for $2 in $RESULTS_DIR, found: $*" >&2
		exit 1
	fi
	echo "$1"
}

analyse_signal() {
	SIGNAL_TYPE="$1"
	MEASUREMENTS="$RESULTS_DIR/mstlo/$SIGNAL_TYPE"

	NATIVE_RESULTS_RAW=$(raw_for "$MEASUREMENTS/performance_results_M=*_raw.csv" "native results")
	PY_RESULTS_RAW=$(raw_for "$MEASUREMENTS/python_performance_results_M=*_raw.csv" "mstlo-python results")
	NATIVE_RESULTS="${NATIVE_RESULTS_RAW%_raw.csv}.csv"
	PY_RESULTS="${PY_RESULTS_RAW%_raw.csv}.csv"

	OUT="$RESULTS_DIR/data_analysis/$SIGNAL_TYPE"
	REGRESSION="$OUT/regression_fit/regression_fit_results.csv"
	MSTLO_PLOTS="$OUT/mstlo_plots"

	for f in "$NATIVE_RESULTS" "$PY_RESULTS"; do
		[ -f "$f" ] || { echo "missing $f -- run first" >&2; exit 1; }
	done

	echo "analysing $SIGNAL_TYPE: $(basename "$NATIVE_RESULTS")"

	echo "--- 1/3  regression fits ---"
	python3 "$ANALYSIS/regression_analysis.py" \
		--native-csv "$NATIVE_RESULTS" \
		--python-csv "$PY_RESULTS" \
		--output "$REGRESSION"

	echo
	echo "--- 2/3  Mann-Whitney U test ---"
	if [ -z "$MWU_FORMULA_IDS" ]; then
		mann_whitney ""
	elif measured "$(echo "$MWU_FORMULA_IDS" | tr ',' '|')"; then
		mann_whitney "$MWU_FORMULA_IDS"
	else
		echo "none of formulas $MWU_FORMULA_IDS were measured -- no test to run"
	fi

	echo
	echo "--- 3/3  mstlo plots ---"
	# Only the three families are plotted, so a run of the fixed formulas alone
	# has nothing to draw.
	if ! measured "5|6|7"; then
		echo "no family was measured -- nothing to plot"
		return
	fi

	python3 "$ANALYSIS/performance_comparison.py" \
		--benchmark-csv "$NATIVE_RESULTS" \
		--regression-csv "$REGRESSION" \
		--output "$MSTLO_PLOTS/performance_comparison_all.pdf"

	# The same four cuts of that plot the paper shows: F/G and U scale
	# differently, and RoSI differently again, so each pair gets its own axes.
	# A cut nothing was measured for is skipped rather than drawn empty --
	# performance_comparison.py has no axes to scale when it is handed nothing.
	if measured "6|7"; then
		plot FG_nonrosi "F G" "delquant delqual eagerqual"
		if measured_rosi; then plot FG_rosi "F G" "rosi"; fi
	fi
	if measured "5"; then
		plot U_nonrosi "U" "delquant delqual eagerqual"
		if measured_rosi; then plot U_rosi "U" "rosi"; fi
	fi
}

# Whether the native results hold any row for these formula IDs, written as an
# alternation.  A run measures whatever its config asked for, so nothing below
# may assume a formula is there.  The ID is the first field of every row, so a
# plain match will do.
measured() {
	grep -qE "^($1)," "$NATIVE_RESULTS"
}

# Whether RoSI ran at all.  ROSI_MAX_BOUND can be set below every bound in the
# sweep, which leaves the two RoSI cuts with nothing.  No spec can contain the
# name of a semantics, so this too is a plain match.
measured_rosi() {
	grep -q ",Rosi," "$NATIVE_RESULTS"
}

# Native against mstlo-python, over the formula IDs given, or over everything
# measured when given none.  The filter is a pandas query, so a list of IDs goes
# in as the literal list it already looks like.
mann_whitney() {
	if [ -n "$1" ]; then
		set -- --filter-a "formula_id in [$1]" --filter-b "formula_id in [$1]"
	else
		set --
	fi

	python3 "$ANALYSIS/mann_whitney.py" \
		--csv-a "$NATIVE_RESULTS_RAW" \
		--csv-b "$PY_RESULTS_RAW" \
		--label-a "native" --label-b "python" \
		--group-by "formula_id" \
		--output "$OUT/mwu/native_vs_python_mwu.csv" \
		"$@"
}

# One cut of the performance comparison: which operators, under which semantics.
plot() {
	# shellcheck disable=SC2086  # both lists are deliberately split into words
	python3 "$ANALYSIS/performance_comparison.py" \
		--benchmark-csv "$NATIVE_RESULTS" \
		--regression-csv "$REGRESSION" \
		--output "$MSTLO_PLOTS/performance_comparison_$1.pdf" \
		--plot-operators $2 \
		--plot-semantics $3 \
		--fg-mode "both" \
		--plot-std \
		--no-log-scale
}

# One directory per signal type the run measured.
SIGNAL_TYPES=""
for dir in "$RESULTS_DIR"/mstlo/*/; do
	[ -d "$dir" ] || continue
	SIGNAL_TYPES="$SIGNAL_TYPES $(basename "$dir")"
done

if [ -z "$SIGNAL_TYPES" ]; then
	echo "no measurements under $RESULTS_DIR/mstlo -- run first" >&2
	exit 1
fi

for signal_type in $SIGNAL_TYPES; do
	echo
	analyse_signal "$signal_type"
done

echo
echo "done. tables and figures in $RESULTS_DIR/data_analysis"
