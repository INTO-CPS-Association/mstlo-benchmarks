#!/usr/bin/env sh
#
# Record a fresh incubator session by driving the course's emulator and
# controller over RabbitMQ.  The emulator runs in real time at one sample every
# 3 s, so even the shortest session spends ~15 minutes pre-heating the box from
# 30 C into the control band before the first useful sample.
#
# Only works in the `gather` image, which has the course at $COURSE_ROOT.
# run.sh picks up the signal.csv this writes.

set -e

SRC="$MSTLO_SRC/incubator"
RESULTS_DIR="${RESULTS_DIR:?set RESULTS_DIR}"
COURSE_ROOT="${COURSE_ROOT:?set COURSE_ROOT -- use the gather image}"

# The course pins older versions than the analysis needs, so its services and
# run_experiment.py get their own interpreter.
GATHER_PYTHON="${GATHER_PYTHON:-python3}"

WARMUP_CYCLES="${WARMUP_CYCLES:-1}"
NORMAL_CYCLES="${NORMAL_CYCLES:-3}"
LID_DURATION="${LID_DURATION:-1200}"

# The course's startup.conf points the broker at localhost; in compose it is a
# service of its own.
CONF="$COURSE_ROOT/incubator_dt/software/startup.conf"
RABBITMQ_HOST="${RABBITMQ_HOST:-rabbitmq}"

if [ -f "$CONF" ] && [ -n "$RABBITMQ_HOST" ]; then
	sed -i "s|^\([[:space:]]*ip[[:space:]]*[:=][[:space:]]*\).*|\1\"$RABBITMQ_HOST\"|" "$CONF"
	echo "broker: $RABBITMQ_HOST"
fi

# run_experiment.py resolves the course relative to its own location, so it has
# to be started from where the mstlo checkout put it.
cd "$SRC"
"$GATHER_PYTHON" run_experiment.py \
	--warmup-cycles "$WARMUP_CYCLES" \
	--normal-cycles "$NORMAL_CYCLES" \
	--lid-duration "$LID_DURATION" \
	--outdir "$RESULTS_DIR" \
	--logdir "$RESULTS_DIR/logs"

echo
echo "done. recording in $RESULTS_DIR/signal.csv -- run next"
