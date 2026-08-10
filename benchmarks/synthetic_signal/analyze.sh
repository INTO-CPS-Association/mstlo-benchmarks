#!/usr/bin/env sh
#
# Turn whatever measurements are in $RESULTS_DIR into the tables and figures.
#
# This image ships no RTAMT, so the comparisons against it -- the combined
# performance_comparison_w_rtamt plot, two of the three Mann-Whitney tests, and
# all 11 rtamt_plots -- have no data and are not produced.  Everything measuring
# mstlo and mstlo-python is here in full.

set -e

ANALYSIS="$MSTLO_SRC/synthetic_signal/data_analysis"
RESULTS_DIR="${RESULTS_DIR:?set RESULTS_DIR}"

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

NATIVE_RESULTS_RAW=$(raw_for "$RESULTS_DIR/mstlo/performance_results_M=*_raw.csv" "native results")
PY_RESULTS_RAW=$(raw_for "$RESULTS_DIR/mstlo/python_performance_results_M=*_raw.csv" "mstlo-python results")
NATIVE_RESULTS="${NATIVE_RESULTS_RAW%_raw.csv}.csv"
PY_RESULTS="${PY_RESULTS_RAW%_raw.csv}.csv"

OUT="$RESULTS_DIR/data_analysis"
REGRESSION="$OUT/regression_fit/regression_fit_results.csv"
MSTLO_PLOTS="$OUT/mstlo_plots"

for f in "$NATIVE_RESULTS" "$PY_RESULTS"; do
	[ -f "$f" ] || { echo "missing $f -- run first" >&2; exit 1; }
done

echo "analysing $(basename "$NATIVE_RESULTS")"

echo "=== 1/3  regression fits ==="
python3 "$ANALYSIS/regression_analysis.py" \
	--native-csv "$NATIVE_RESULTS" \
	--python-csv "$PY_RESULTS" \
	--output "$REGRESSION"

echo
echo "=== 2/3  Mann-Whitney U test ==="
python3 "$ANALYSIS/mann_whitney.py" \
	--csv-a "$NATIVE_RESULTS_RAW" \
	--csv-b "$PY_RESULTS_RAW" \
	--label-a "native" --label-b "python" \
	--group-by "formula_id" \
	--filter-a "formula_id in [1, 2, 3, 4]" \
	--filter-b "formula_id in [1, 2, 3, 4]" \
	--output "$OUT/mwu/native_vs_python_mwu.csv"

echo
echo "=== 3/3  mstlo plots ==="
python3 "$ANALYSIS/performance_comparison.py" \
	--benchmark-csv "$NATIVE_RESULTS" \
	--regression-csv "$REGRESSION" \
	--output "$MSTLO_PLOTS/performance_comparison_all.pdf"

python3 "$ANALYSIS/performance_comparison.py" \
	--benchmark-csv "$NATIVE_RESULTS" \
	--regression-csv "$REGRESSION" \
	--output "$MSTLO_PLOTS/performance_comparison_FG_nonrosi.pdf" \
	--plot-operators F G \
	--plot-semantics delquant delqual eagerqual \
	--fg-mode "both" \
	--plot-std \
	--no-log-scale

python3 "$ANALYSIS/performance_comparison.py" \
	--benchmark-csv "$NATIVE_RESULTS" \
	--regression-csv "$REGRESSION" \
	--output "$MSTLO_PLOTS/performance_comparison_U_nonrosi.pdf" \
	--plot-operators U \
	--plot-semantics delquant delqual eagerqual \
	--fg-mode "both" \
	--plot-std \
	--no-log-scale

python3 "$ANALYSIS/performance_comparison.py" \
	--benchmark-csv "$NATIVE_RESULTS" \
	--regression-csv "$REGRESSION" \
	--output "$MSTLO_PLOTS/performance_comparison_FG_rosi.pdf" \
	--plot-operators F G \
	--plot-semantics "rosi" \
	--fg-mode "both" \
	--plot-std \
	--no-log-scale

python3 "$ANALYSIS/performance_comparison.py" \
	--benchmark-csv "$NATIVE_RESULTS" \
	--regression-csv "$REGRESSION" \
	--output "$MSTLO_PLOTS/performance_comparison_U_rosi.pdf" \
	--plot-operators U \
	--plot-semantics "rosi" \
	--fg-mode "both" \
	--plot-std \
	--no-log-scale

echo
echo "done. tables and figures in $OUT"
