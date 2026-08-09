from __future__ import annotations

import os
import shlex
import subprocess
import tempfile
from pathlib import Path

IDL_PACKAGE_FILTER = (
    "std_msgs;geometry_msgs;nav_msgs;id_pose_msgs;robo_sapiens_interfaces"
)


def activate(
    checker_dir: Path,
    require_overlay: bool = True,
    overlay_setup: Path | None = None,
) -> None:
    distro = os.environ.get("ROS_DISTRO", "jazzy")
    setups = [Path("/opt/ros") / distro / "setup.bash"]
    overlay = overlay_setup or Path(
        os.environ.get(
            "MSTLO_ROS_OVERLAY",
            str(checker_dir / "ros_interfaces" / "install" / "setup.bash"),
        )
    )
    if overlay.is_dir():
        overlay /= "setup.bash"
    if require_overlay:
        setups.append(overlay)
    missing = [path for path in setups if not path.is_file()]
    if missing:
        raise RuntimeError(f"ROS setup not found: {missing[0]}")
    script = (
        "; ".join(f"source {shlex.quote(str(path))}" for path in setups) + "; env -0"
    )
    result = subprocess.run(["bash", "-c", script], capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors="replace").strip())
    for entry in result.stdout.split(b"\0"):
        if b"=" in entry:
            key, value = entry.split(b"=", 1)
            os.environ[os.fsdecode(key)] = os.fsdecode(value)
    os.environ["IDL_PACKAGE_FILTER"] = IDL_PACKAGE_FILTER
    os.environ.setdefault(
        "ROS_LOG_DIR", str(Path(tempfile.gettempdir()) / "mstlo-bench-ros")
    )
    Path(os.environ["ROS_LOG_DIR"]).mkdir(parents=True, exist_ok=True)
