#!/usr/bin/env sh
#
# The latency sweep: every configured point, direct and over ROS 2, into
# $RESULTS_DIR.  The measuring is done by the mstlo-bench CLI installed in this
# image, which is the only thing about this benchmark the other two do not
# share; the stage itself is driven exactly like theirs, by ../entrypoint.sh.
#
# analyze.sh turns what this leaves behind into the report.

set -e

RESULTS_DIR="${RESULTS_DIR:?set RESULTS_DIR}"
CONFIG_FILE="${CONFIG_FILE:?set CONFIG_FILE}"
MSTLO_BENCH="${MSTLO_BENCH:-mstlo-bench}"

# Appending to a directory that already holds results would duplicate rows and
# silently reweight the report, so it has to be asked for:
#
#     RESULTS_DIR=/results/multi_robot/quick-... RESUME=1 run multi_robot quick
set -- benchmark --config "$CONFIG_FILE" --output-dir "$RESULTS_DIR"
if [ -n "$RESUME" ]; then
	set -- "$@" --resume
fi

"$MSTLO_BENCH" "$@" && status=0 || status=$?

echo
echo "done. measurements in $RESULTS_DIR:"
echo "  results.jsonl   one row per benchmark point"
echo "  work/           the raw runner output each row came from"
echo "analyze next, for the report."
exit "$status"
