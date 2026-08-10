#!/usr/bin/env sh
#
# Usage: <stage> <benchmark> [config]
#
# A stage is a script: benchmarks/<benchmark>/<stage>.sh.  A benchmark supports
# whichever of gather/run/analyze it has a script for.  The config names a file
# under benchmarks/<benchmark>/configs/, applied as environment variables that
# anything already in the environment overrides.
#
# Everything is written to $RESULTS_DIR, which defaults to a per-benchmark
# directory under $RESULTS_ROOT.
#
# The benchmark code itself lives in the vendored mstlo checkout ($MSTLO_ROOT);
# only the stage scripts and their configs live here, so that a `git subtree
# pull` never has to merge anything this repository wrote.

set -e

BENCH_ROOT="$(cd "$(dirname "$0")" && pwd)"

STAGE="$1"
BENCH="$2"
CONFIG="${3:-default}"

usage() {
	echo "usage: <stage> <benchmark> [config]" >&2
	echo >&2
	for dir in "$BENCH_ROOT"/*/; do
		[ -d "$dir/configs" ] || continue
		stages=$(cd "$dir" && ls ./*.sh 2>/dev/null | sed 's|\./||;s|\.sh$||' | tr '\n' ' ')
		configs=$(cd "$dir/configs" && ls ./*.toml 2>/dev/null | sed 's|\./||;s|\.toml$||' | tr '\n' ' ')
		printf '  %-18s stages: %-24s configs: %s\n' "$(basename "$dir")" "$stages" "$configs" >&2
	done
	printf '  %-18s stages: %-24s configs: %s\n' \
		"multi_robot" "run" "quick small paper overnight" >&2
	echo >&2
	echo "multi_robot needs ROS 2 and runs in its own image:" >&2
	echo "    docker compose run --rm benchmark run multi_robot <config>" >&2
	exit 1
}

[ -n "$STAGE" ] && [ -n "$BENCH" ] || usage

# Sent here by muscle memory more often than not, and "no such benchmark" would
# be a confusing way to find out it lives in the other image.
if [ "$BENCH" = "multi_robot" ]; then
	echo "multi_robot needs ROS 2 and runs in its own image:" >&2
	echo "    docker compose run --rm benchmark run multi_robot ${CONFIG}" >&2
	exit 2
fi

# Where the vendored mstlo checkout is.  The Python benchmark scripts and the
# Rust benches live there; the stage scripts live here.
MSTLO_ROOT="${MSTLO_ROOT:?set MSTLO_ROOT -- use the bench or gather image}"
MSTLO_SRC="$MSTLO_ROOT/benchmarks"             # the mstlo repo's benchmark scripts
MSTLO_DIR="${MSTLO_DIR:-$MSTLO_ROOT/mstlo}"    # the Rust crate
export MSTLO_ROOT MSTLO_SRC MSTLO_DIR

SCRIPT="$BENCH_ROOT/$BENCH/$STAGE.sh"
CONFIG_FILE="$BENCH_ROOT/$BENCH/configs/$CONFIG.toml"

[ -f "$SCRIPT" ] || { echo "no such stage: $BENCH/$STAGE" >&2; usage; }
[ -f "$CONFIG_FILE" ] || { echo "no such config: $BENCH/$CONFIG" >&2; usage; }

eval "$(python3 "$BENCH_ROOT/config.py" "$CONFIG_FILE" "$STAGE")"

RESULTS_DIR="${RESULTS_DIR:-${RESULTS_ROOT:-/results}/$BENCH}"
export RESULTS_DIR STAGE BENCH CONFIG CONFIG_FILE
mkdir -p "$RESULTS_DIR"

echo "=== $BENCH/$STAGE [$CONFIG] -> $RESULTS_DIR ==="

# What produced the numbers, next to the numbers.  Not written for analyze:
# that stage may be pointed at a committed tree, which it must not dirty.
if [ "$STAGE" = "analyze" ]; then
	exec "$SCRIPT"
fi

python3 "$BENCH_ROOT/metadata.py" start
"$SCRIPT" && status=0 || status=$?
python3 "$BENCH_ROOT/metadata.py" finish "$status"
exit "$status"
