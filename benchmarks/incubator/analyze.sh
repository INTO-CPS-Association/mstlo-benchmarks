#!/usr/bin/env sh
#
# Draw the figures from whatever the run stage left in $RESULTS_DIR.

set -e

SRC="$MSTLO_SRC/incubator"
RESULTS_DIR="${RESULTS_DIR:?set RESULTS_DIR}"

[ -f "$RESULTS_DIR/dataset.csv" ] || {
	echo "missing $RESULTS_DIR/dataset.csv -- run first" >&2
	exit 1
}

python3 "$SRC/plot_results.py" \
	--datadir "$RESULTS_DIR" \
	--figdir "$RESULTS_DIR/figures"

echo
echo "done. figures in $RESULTS_DIR/figures"
