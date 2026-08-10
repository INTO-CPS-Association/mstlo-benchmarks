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

# Everything above is what this image adds: ROS on the path.  What to run is
# then decided exactly as it is for the other two benchmarks, by the shared
# stage layer -- `<stage> <benchmark> [config]`, with no arguments listing what
# there is.
if (( $# == 0 )) || [[ "${1}" == "gather" || "${1}" == "run" || "${1}" == "analyze" ]]; then
    exec /opt/stages/entrypoint.sh "$@"
fi

# The benchmark's own tool, for the things that are not a stage: `test`, and
# `report --output-dir` against a directory of one's choosing.
exec /opt/venv/bin/mstlo-bench "$@"
