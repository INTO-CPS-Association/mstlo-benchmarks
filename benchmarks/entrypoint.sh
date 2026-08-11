#!/usr/bin/env sh
#
# Usage: <stage> [config | results]
#
# The one way to run a benchmark.  Which benchmark is not asked here: one image
# holds one benchmark and names it in $BENCH, so a compose service *is* a
# benchmark and only the stage has to be said.  A stage is a script:
# benchmarks/<benchmark>/<stage>.sh, and a benchmark supports whichever of
# gather/run/analyze it has a script for.  The config names a file under
# benchmarks/<benchmark>/configs/, applied as environment variables that
# anything already in the environment overrides.  An analysing stage takes a
# result directory there instead, when the newest one is not the one wanted.
#
# `test` is the one stage every benchmark has without writing a script for it:
# the shared suite below, plus the benchmark's own if it has one.
#
# Where the results go is decided here, identically for all of them (see
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
CONFIG="${2:-default}"
CONFIG_GIVEN="$2"

# Every benchmark, and the compose service that is it.  Only used to answer a
# command meant for a different one with something more useful than a parse
# error; the list is short and changes about as often as the repository does.
SERVICES="multi_robot synthetic_signal incubator"

usage() {
	echo "usage: docker compose run --rm $BENCH <stage> [config]" >&2
	echo "       docker compose run --rm $BENCH analyze [config | result directory | latest]" >&2
	echo >&2
	stages=$(cd "$BENCH_ROOT/$BENCH" && ls ./*.sh 2>/dev/null | sed 's|\./||;s|\.sh$||' | tr '\n' ' ')
	configs=$(cd "$BENCH_ROOT/$BENCH/configs" && ls ./*.toml 2>/dev/null | sed 's|\./||;s|\.toml$||' | tr '\n' ' ')
	printf '  %-18s stages: %-24s configs: %s\n' "$BENCH" "${stages}test" "$configs" >&2
	echo >&2
	echo "the other benchmarks are other services:" >&2
	for service in $SERVICES; do
		[ "$service" = "$BENCH" ] || echo "    docker compose run --rm $service ..." >&2
	done
	exit 1
}

# The image says which benchmark it is.  Nothing sets this by hand; if it is
# missing the image was built wrong.
if [ -z "$BENCH" ] || [ ! -d "$BENCH_ROOT/$BENCH" ]; then
	echo "this image does not say which benchmark it holds (BENCH=${BENCH:-unset})" >&2
	exit 2
fi

[ -n "$STAGE" ] || usage

# Where the vendored mstlo checkout is.  Its Python scripts and Rust benches
# back two of the three benchmarks; the third has no use for it, so this is only
# passed on when the image has one, and the stage scripts that need it say so.
if [ -n "$MSTLO_ROOT" ]; then
	MSTLO_SRC="$MSTLO_ROOT/benchmarks"           # the mstlo repo's benchmark scripts
	MSTLO_DIR="${MSTLO_DIR:-$MSTLO_ROOT/mstlo}"  # the Rust crate
	export MSTLO_ROOT MSTLO_SRC MSTLO_DIR
fi

# The unit tests, in the image that has to pass them: the shared stage layer's,
# which every benchmark is driven by, and this benchmark's own.  Everything
# after `test` is handed to pytest.
if [ "$STAGE" = "test" ]; then
	shift
	SUITES="$BENCH_ROOT/tests"
	[ -d "$BENCH_ROOT/$BENCH/tests" ] && SUITES="$SUITES $BENCH_ROOT/$BENCH/tests"
	# The suite paths are fixed locations in the image and contain no spaces.
	# shellcheck disable=SC2086
	exec python3 -m pytest $SUITES "$@"
fi

SCRIPT="$BENCH_ROOT/$BENCH/$STAGE.sh"
[ -f "$SCRIPT" ] || { echo "no such stage: $BENCH/$STAGE" >&2; usage; }

# The second argument says which results.  For a measuring stage that can only
# be a config.  For an analysing one it is either a config -- analyse the newest
# run made with it -- or the results to analyse, named directly: a directory
# under results/<benchmark>/, `latest`, or a path.
TARGET=""
if [ -n "$CONFIG_GIVEN" ] && [ ! -f "$BENCH_ROOT/$BENCH/configs/$CONFIG.toml" ]; then
	# A benchmark name here is the old two-argument habit, or a command typed
	# at the wrong service.  Both are worth answering directly.
	if [ "$CONFIG_GIVEN" = "$BENCH" ]; then
		echo "the service already is $BENCH; name only the stage and the config:" >&2
		echo "    docker compose run --rm $BENCH $STAGE" >&2
		exit 2
	fi
	for service in $SERVICES; do
		[ "$service" = "$CONFIG_GIVEN" ] || continue
		echo "$CONFIG_GIVEN is another service:" >&2
		echo "    docker compose run --rm $CONFIG_GIVEN $STAGE" >&2
		exit 2
	done

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

eval "$(python3 "$BENCH_ROOT/config.py" "$CONFIG_FILE" "$STAGE")"

RESULTS_ROOT="${RESULTS_ROOT:-$(cd "$BENCH_ROOT/.." && pwd)/results}"
export RESULTS_ROOT

# A measuring stage never writes into results somebody already has; an analysing
# stage never guesses which results to draw.  It defaults to the newest run,
# which naming a config narrows -- `analyze quick` takes the last quick one --
# and naming a directory replaces outright.
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
