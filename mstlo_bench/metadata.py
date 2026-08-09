from __future__ import annotations

import hashlib
import json
import os
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

METADATA_FILE = "metadata.json"


def utc_now() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def _environment_value(*names: str) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


def _read_cpu_model() -> str | None:
    fallback: str | None = None
    try:
        for line in (
            Path("/proc/cpuinfo")
            .read_text(encoding="utf-8", errors="replace")
            .splitlines()
        ):
            key, separator, value = line.partition(":")
            if not separator or not value.strip():
                continue
            normalized_key = key.strip().lower()
            if normalized_key in {"model name", "hardware"}:
                return value.strip()
            if normalized_key == "processor" and fallback is None:
                fallback = value.strip()
    except (OSError, UnicodeError):
        pass
    return fallback


def _memory_limit_bytes() -> int | None:
    """Return the container memory limit when the platform exposes one."""
    for path in (
        Path("/sys/fs/cgroup/memory.max"),
        Path("/sys/fs/cgroup/memory/memory.limit_in_bytes"),
    ):
        try:
            value = path.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError):
            continue
        if not value or value == "max":
            continue
        try:
            parsed = int(value)
        except ValueError:
            continue
        # Some cgroup v1 setups use a very large sentinel for "unlimited".
        if parsed >= 1 << 60:
            return None
        return parsed
    return None


def _kernel_info() -> dict[str, str] | None:
    try:
        info = platform.uname()
    except (OSError, RuntimeError):
        return None
    return {
        "system": info.system,
        "release": info.release,
        "version": info.version,
        "machine": info.machine,
    }


def _architecture() -> str | None:
    try:
        return platform.machine() or None
    except (OSError, RuntimeError):
        return None


def _config_sha256(config_path: Path) -> str:
    return hashlib.sha256(config_path.read_bytes()).hexdigest()


def collect_metadata(
    config_path: Path,
    *,
    started_at_utc: str | None = None,
    completed_at_utc: str | None = None,
    status: str = "running",
) -> dict[str, Any]:
    """Collect reproducibility data without depending on the Docker socket."""
    config_path = config_path.resolve()
    config_sha256 = _config_sha256(config_path)
    kernel = _kernel_info()
    return {
        "started_at_utc": started_at_utc or utc_now(),
        "completed_at_utc": completed_at_utc,
        "status": status,
        "config_path": str(config_path),
        "config_sha256": config_sha256,
        "configuration": {"path": str(config_path), "sha256": config_sha256},
        "repository_revision": _environment_value(
            "MSTLO_BENCH_REPOSITORY_REVISION", "MSTLO_REPOSITORY_REVISION"
        ),
        "image_version": _environment_value(
            "MSTLO_BENCH_IMAGE_VERSION", "MSTLO_IMAGE_VERSION"
        ),
        "architecture": _architecture(),
        "cpu_model": _read_cpu_model(),
        "logical_cpu_count": os.cpu_count(),
        "memory_limit_bytes": _memory_limit_bytes(),
        "kernel": kernel,
        "python_version": platform.python_version(),
        "ros_distribution": os.environ.get("ROS_DISTRO"),
        "ros_middleware": os.environ.get("RMW_IMPLEMENTATION"),
    }


def write_metadata(output_dir: Path, metadata: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / METADATA_FILE
    path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path


def update_metadata(
    output_dir: Path,
    *,
    completed_at_utc: str | None = None,
    status: str,
) -> Path:
    path = output_dir / METADATA_FILE
    metadata = json.loads(path.read_text(encoding="utf-8"))
    metadata["completed_at_utc"] = completed_at_utc or utc_now()
    metadata["status"] = status
    return write_metadata(output_dir, metadata)
