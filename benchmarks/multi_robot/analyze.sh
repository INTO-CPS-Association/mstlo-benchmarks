#!/usr/bin/env sh
#
# Turn the measurements in $RESULTS_DIR into the report: one CSV, one Markdown
# report, and one fan plot per MSTLO semantics the run covered.
#
# Incomplete and unrun series are named in the report rather than filled in, so
# this is worth running on a sweep that failed partway through.

set -e

RESULTS_DIR="${RESULTS_DIR:?set RESULTS_DIR}"
MSTLO_BENCH="${MSTLO_BENCH:-mstlo-bench}"

[ -f "$RESULTS_DIR/results.jsonl" ] || {
	echo "missing $RESULTS_DIR/results.jsonl -- run first" >&2
	exit 1
}

set -- report --output-dir "$RESULTS_DIR"
if [ -n "$REPORT_DIR" ]; then
	set -- "$@" --report-dir "$REPORT_DIR"
fi

"$MSTLO_BENCH" "$@"

echo
echo "done. report in ${REPORT_DIR:-$RESULTS_DIR/report}"
