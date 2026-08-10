#!/usr/bin/env sh
#
# Usage: <stage> <benchmark> [config | results]
#
# The one way to run any of the three benchmarks.  A stage is a script:
# benchmarks/<benchmark>/<stage>.sh.  A benchmark supports whichever of
# gather/run/analyze it has a script for.  The config names a file under
# benchmarks/<benchmark>/configs/, applied as environment variables that
# anything already in the environment overrides.  An analysing stage takes a
# result directory there instead, when the newest one is not the one wanted.
#
# Where the results go is decided here, identically for all three (see
# results.py): a measuring stage gets a fresh directory of its own, an
# analysing stage is pointed at the newest measurements it can use, and
# $RESULTS_DIR overrides both.
#
# Most benchmark code lives in the vendored checkouts -- the mstlo one at
# $MSTLO_ROOT, the multi-robot runner in this image's mstlo-bench -- so only the
# stage scripts and their configs live here, and a `git subtree pull` never has
# to merge anything this repository wrote.

set -e

BENCH_ROOT="$(cd "$(dirname "$0")" && pwd)"

STAGE="$1"
BENCH="$2"
CONFIG="${3:-default}"
CONFIG_GIVEN="$3"

usage() {
	echo "usage: <stage> <benchmark> [config]" >&2
	echo "       analyze <benchmark> [config | result directory | latest]" >&2
	echo >&2
	for dir in "$BENCH_ROOT"/*/; do
		[ -d "$dir/configs" ] || continue
		stages=$(cd "$dir" && ls ./*.sh 2>/dev/null | sed 's|\./||;s|\.sh$||' | tr '\n' ' ')
		configs=$(cd "$dir/configs" && ls ./*.toml 2>/dev/null | sed 's|\./||;s|\.toml$||' | tr '\n' ' ')
		printf '  %-18s stages: %-24s configs: %s\n' "$(basename "$dir")" "$stages" "$configs" >&2
	done
	echo >&2
	echo "the benchmarks not listed above are in another image; ask for one to be told which" >&2
	exit 1
}

# Which compose service builds the image a benchmark runs in.  Only used to
# answer "no such benchmark" with something more useful than that.
service_for() {
	case "$1" in
	multi_robot) echo benchmark ;;
	synthetic_signal | incubator) echo bench ;;
	*) echo "" ;;
	esac
}

[ -n "$STAGE" ] && [ -n "$BENCH" ] || usage

if [ ! -d "$BENCH_ROOT/$BENCH" ]; then
	service=$(service_for "$BENCH")
	if [ -n "$service" ]; then
		echo "$BENCH is not in this image; it runs in the '$service' one:" >&2
		echo "    docker compose run --rm $service $STAGE $BENCH $CONFIG_GIVEN" >&2
		exit 2
	fi
	echo "no such benchmark: $BENCH" >&2
	usage
fi

SCRIPT="$BENCH_ROOT/$BENCH/$STAGE.sh"
[ -f "$SCRIPT" ] || { echo "no such stage: $BENCH/$STAGE" >&2; usage; }

# The third argument says which.  For a measuring stage that can only be a
# config.  For an analysing one it is either a config -- analyse the newest run
# made with it -- or the results to analyse, named directly: a directory under
# results/<benchmark>/, `latest`, or a path.
TARGET=""
if [ -n "$CONFIG_GIVEN" ] && [ ! -f "$BENCH_ROOT/$BENCH/configs/$CONFIG.toml" ]; then
	case "$STAGE" in
	gather | run)
		echo "no such config: $BENCH/$CONFIG" >&2
		usage
		;;
	*)
		TARGET="$CONFIG"
		CONFIG=default
		CONFIG_GIVEN=""
		;;
	esac
fi

CONFIG_FILE="$BENCH_ROOT/$BENCH/configs/$CONFIG.toml"
[ -f "$CONFIG_FILE" ] || { echo "no such config: $BENCH/$CONFIG" >&2; usage; }

# Where the vendored mstlo checkout is.  Its Python scripts and Rust benches
# back two of the three benchmarks; the third has no use for it, so this is only
# passed on when the image has one, and the stage scripts that need it say so.
if [ -n "$MSTLO_ROOT" ]; then
	MSTLO_SRC="$MSTLO_ROOT/benchmarks"           # the mstlo repo's benchmark scripts
	MSTLO_DIR="${MSTLO_DIR:-$MSTLO_ROOT/mstlo}"  # the Rust crate
	export MSTLO_ROOT MSTLO_SRC MSTLO_DIR
fi

eval "$(python3 "$BENCH_ROOT/config.py" "$CONFIG_FILE" "$STAGE")"

RESULTS_ROOT="${RESULTS_ROOT:-$(cd "$BENCH_ROOT/.." && pwd)/results}"
export RESULTS_ROOT

# A measuring stage never writes into results somebody already has; an analysing
# stage never guesses which results to draw.  It defaults to the newest run,
# which naming a config narrows -- `analyze <bench> quick` takes the last quick
# one -- and naming a directory replaces outright.
if [ -z "$RESULTS_DIR" ]; then
	case "$STAGE" in
	gather | run)
		RESULTS_DIR=$(python3 "$BENCH_ROOT/results.py" new "$BENCH" "$CONFIG")
		;;
	*)
		if [ -n "$TARGET" ]; then
			RESULTS_DIR=$(python3 "$BENCH_ROOT/results.py" resolve "$BENCH" "$TARGET") || {
				echo "'$TARGET' is neither a config of $BENCH nor a result directory" >&2
				usage
			}
		elif [ -n "$CONFIG_GIVEN" ]; then
			RESULTS_DIR=$(python3 "$BENCH_ROOT/results.py" latest "$BENCH" --stage run --config "$CONFIG")
		else
			RESULTS_DIR=$(python3 "$BENCH_ROOT/results.py" latest "$BENCH" --stage run)
		fi
		;;
	esac
fi

export BENCH_ROOT RESULTS_DIR STAGE BENCH CONFIG CONFIG_FILE
mkdir -p "$RESULTS_DIR"

echo "=== $BENCH/$STAGE [$CONFIG] -> $RESULTS_DIR ==="

# What produced the numbers, next to the numbers, for every stage of every
# benchmark.  A measuring stage brings its config along; an analysing one reads
# the one already there.
python3 "$BENCH_ROOT/metadata.py" start
case "$STAGE" in
gather | run) cp "$CONFIG_FILE" "$RESULTS_DIR/config.toml" ;;
esac

"$SCRIPT" && status=0 || status=$?
python3 "$BENCH_ROOT/metadata.py" finish "$status"
exit "$status"
