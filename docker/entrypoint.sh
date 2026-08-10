#!/usr/bin/env bash
set -eo pipefail

ros_setup="/opt/ros/${ROS_DISTRO:?ROS_DISTRO is not set}/setup.bash"
if [[ ! -f "${ros_setup}" ]]; then
    echo "ROS setup not found: ${ros_setup}" >&2
    exit 1
fi
source "${ros_setup}"

overlay="${MSTLO_ROS_OVERLAY:-/opt/ros_interfaces/install}"
if [[ -d "${overlay}" ]]; then
    overlay="${overlay}/setup.bash"
elif [[ "${overlay}" != *.bash ]]; then
    overlay="${overlay}/setup.bash"
fi
if [[ ! -f "${overlay}" ]]; then
    echo "ROS interface overlay setup not found: ${overlay}" >&2
    exit 1
fi
source "${overlay}"
set -u

export ROS_LOCALHOST_ONLY="${ROS_LOCALHOST_ONLY:-1}"
export RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION:-rmw_fastrtps_cpp}"
export IDL_PACKAGE_FILTER="${IDL_PACKAGE_FILTER:-std_msgs;geometry_msgs;nav_msgs;id_pose_msgs;robo_sapiens_interfaces}"

if (( $# == 0 )); then
    set -- --help
fi

# The two mstlo benchmarks are driven as `<stage> <benchmark> [config]` by the
# other image's entrypoint.  Accept that shape here too, so the README can
# document all three benchmarks with one verb.  Every existing form -- `quick`,
# `report --output-dir ...`, `test` -- is untouched.
if [[ "${1:-}" == "run" && "${2:-}" == "multi_robot" ]]; then
    shift 2
    set -- "${1:-quick}"
fi

exec /opt/venv/bin/mstlo-bench "$@"
