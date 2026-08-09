from __future__ import annotations

import fcntl
import itertools
import json
import os
import signal
import subprocess
import time
import tomllib
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .collect import append_result
from .metadata import collect_metadata, update_metadata, utc_now, write_metadata
from .progress import (
    expected_progress_seconds,
    format_progress_label,
    run_with_progress,
)
from .properties import semantic_horizon_ms, write_artefacts
from .ros import activate

_SOURCE_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("MSTLO_BENCH_ROOT", _SOURCE_ROOT))
RUNNER_DIR = Path(os.environ.get("MSTLO_RUNNER_DIR", ROOT / "benchmark-runner"))
CHECKER_DIR = Path(
    os.environ.get("MSTLO_CHECKER_DIR", ROOT / "robosapiens-trustworthiness-checker")
)
PROFILE = "bench-fast"
MAX_RETRIES = 5


@dataclass(frozen=True)
class Config:
    robots: list[int]
    seeds: list[int]
    property_sets: list[str]
    transports: list[str]
    semantics: list[str]
    algorithm: str
    duration_s: float
    publish_rate_hz: float
    sim_hz: float
    window_s: float
    dwell_s: float
    discovery_s: float
    checker_settle_s: float
    drain_s: float


@dataclass(frozen=True)
class Point:
    robots: int
    seed: int
    property_set: str
    transport: str
    semantics: str

    def name(self) -> str:
        return (
            f"{self.property_set}-{self.semantics}-{self.transport}"
            f"-r{self.robots}-s{self.seed}"
        )


def load_config(path: Path) -> Config:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    benchmark = data["benchmark"]
    ros = data.get("ros", {})
    config = Config(
        robots=list(benchmark["robots"]),
        seeds=list(benchmark["seeds"]),
        property_sets=list(benchmark["property_sets"]),
        transports=list(benchmark["transports"]),
        semantics=list(benchmark.get("semantics", ["delayed-qualitative"])),
        algorithm=str(benchmark.get("algorithm", "incremental")),
        duration_s=float(benchmark["duration_s"]),
        publish_rate_hz=float(benchmark["publish_rate_hz"]),
        sim_hz=float(benchmark.get("sim_hz", 60.0)),
        window_s=float(benchmark.get("window_s", 10.0)),
        dwell_s=float(benchmark.get("dwell_s", 5.0)),
        discovery_s=float(ros.get("discovery_s", 2.0)),
        checker_settle_s=float(ros.get("checker_settle_s", 2.0)),
        drain_s=float(ros.get("drain_s", 2.0)),
    )
    if set(config.transports) - {"direct", "ros"}:
        raise ValueError("transports must contain only 'direct' and 'ros'")
    supported_semantics = {
        "delayed-qualitative",
        "delayed-quantitative",
        "eager-qualitative",
        "robustness-interval",
    }
    if set(config.semantics) - supported_semantics:
        raise ValueError("unsupported MSTLO semantics")
    if config.algorithm != "incremental":
        raise ValueError("the reference benchmark uses the incremental algorithm")
    if not config.robots or min(config.robots) < 1:
        raise ValueError("robots must contain positive integers")
    return config


def run(
    config_path: Path, output_dir: Path, *, resume: bool = False
) -> list[dict[str, Any]]:
    with _output_lock(output_dir):
        return _run_locked(config_path, output_dir, resume=resume)


def fresh_result_directory(results_root: Path, suite_name: str) -> Path:
    """Create and return a unique directory for a new named suite run."""
    results_root.mkdir(parents=True, exist_ok=True)
    timestamp = utc_now().replace("-", "").replace(":", "").replace("+00:00", "")
    timestamp = timestamp.replace("Z", "Z")
    safe_name = (
        "".join(
            character if character.isalnum() or character in "-_" else "-"
            for character in suite_name
        ).strip("-")
        or "benchmark"
    )
    for _ in range(10):
        candidate = results_root / f"{safe_name}-{timestamp}-{uuid.uuid4().hex[:8]}"
        try:
            candidate.mkdir()
        except FileExistsError:
            continue
        return candidate
    raise RuntimeError(
        f"could not allocate a fresh result directory under {results_root}"
    )


def _run_locked(
    config_path: Path, output_dir: Path, *, resume: bool = False
) -> list[dict[str, Any]]:
    config = load_config(config_path)
    _prepare_output_directory(config_path, output_dir, resume=resume)
    existing_metadata = output_dir / "metadata.json"
    started_at = utc_now()
    if resume and existing_metadata.exists():
        try:
            started_at = json.loads(existing_metadata.read_text(encoding="utf-8"))[
                "started_at_utc"
            ]
        except (KeyError, json.JSONDecodeError):
            raise ValueError(
                f"{existing_metadata} is not valid benchmark metadata; start a fresh run"
            ) from None
    write_metadata(
        output_dir,
        collect_metadata(config_path, started_at_utc=started_at, status="running"),
    )

    rows: list[dict[str, Any]] = []
    try:
        topic_namespace = f"mstlo_bench_{uuid.uuid4().hex}"
        _build("ros" in config.transports)
        points = [
            Point(*values)
            for values in itertools.product(
                config.robots,
                config.seeds,
                config.property_sets,
                config.transports,
                config.semantics,
            )
        ]
        total = len(points)
        label_width = max(
            len(format_progress_label(index, total, point))
            for index, point in enumerate(points, 1)
        )
        maximum_seconds = max(
            expected_progress_seconds(
                point,
                config.duration_s,
                config.checker_settle_s,
                config.discovery_s,
                config.drain_s,
            )
            for point in points
        )
        seconds_width = len(f"{maximum_seconds:.1f}")

        print(f"Running {total} benchmark points into {output_dir}", flush=True)
        for index, point in enumerate(points, 1):

            def attempt(point: Point = point, index: int = index) -> dict[str, Any]:
                try:
                    return run_with_progress(
                        point,
                        index,
                        total,
                        duration_s=config.duration_s,
                        settle_s=config.checker_settle_s,
                        warmup_s=config.discovery_s,
                        drain_s=config.drain_s,
                        label_width=label_width,
                        seconds_width=seconds_width,
                        runner=lambda: _run_point(
                            point, config, output_dir, topic_namespace
                        ),
                    )
                except Exception as error:
                    return _failure_row(point, config, str(error))

            row = run_attempts(attempt)
            append_result(output_dir, row)
            rows.append(row)
            if row["ok"]:
                print(f"  p95 {row['latency_overhead_ms_p95']:.3f} ms")
            else:
                print(f"  failed: {row['error']}")
        return rows
    finally:
        status = "success" if rows and all(row.get("ok") for row in rows) else "failed"
        update_metadata(output_dir, status=status)


def run_attempts(
    attempt: Callable[[], dict[str, Any]], max_retries: int = MAX_RETRIES
) -> dict[str, Any]:
    """Retry a benchmark point until it succeeds, at most `max_retries` times.

    ROS points fail intermittently under load, so a failed attempt is repeated
    instead of leaving a gap in the sweep. Only the final row is kept, and its
    `attempts` field records how many runs it took.
    """
    row: dict[str, Any] = {}
    for number in range(1, max_retries + 2):
        row = attempt()
        row["attempts"] = number
        if row["ok"]:
            break
        if number <= max_retries:
            print(f"  retry {number}/{max_retries} after: {row['error']}")
    return row


def _failure_row(point: Point, config: Config, error: str) -> dict[str, Any]:
    return {
        "robots": point.robots,
        "seed": point.seed,
        "property_set": point.property_set,
        "transport": point.transport,
        "semantics": point.semantics,
        "algorithm": config.algorithm,
        "ok": False,
        "error": error,
    }


@contextmanager
def _output_lock(output_dir: Path) -> Iterator[None]:
    output_dir.mkdir(parents=True, exist_ok=True)
    lock_path = output_dir / ".benchmark.lock"
    with lock_path.open("a+", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError(
                f"another benchmark is already writing to {output_dir}"
            ) from error
        lock.seek(0)
        lock.truncate()
        lock.write(f"pid={os.getpid()}\n")
        lock.flush()
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _prepare_output_directory(
    config_path: Path, output_dir: Path, *, resume: bool
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    results = output_dir / "results.jsonl"
    if results.exists() and not resume:
        raise ValueError(
            f"{output_dir} already contains results; choose a fresh output directory "
            "or pass --resume explicitly"
        )
    _snapshot_config(config_path, output_dir)


def _snapshot_config(config_path: Path, output_dir: Path) -> None:
    snapshot = output_dir / "config.toml"
    contents = config_path.read_bytes()
    results = output_dir / "results.jsonl"
    if snapshot.exists() and snapshot.read_bytes() != contents and results.exists():
        raise ValueError(f"{output_dir} contains results for a different config")
    output_dir.mkdir(parents=True, exist_ok=True)
    snapshot.write_bytes(contents)


def _build(needs_ros: bool) -> None:
    if _prebuilt_mode():
        _validate_prebuilt(needs_ros)
        if needs_ros:
            activate(
                CHECKER_DIR,
                require_overlay=True,
                overlay_setup=_ros_overlay_setup(),
            )
        return
    features: list[str] = []
    if needs_ros:
        activate(CHECKER_DIR, require_overlay=False)
        _check(
            [
                "colcon",
                "build",
                "--packages-select",
                "robo_sapiens_interfaces",
                "id_pose_msgs",
            ],
            CHECKER_DIR / "ros_interfaces",
        )
        activate(CHECKER_DIR)
        _check(
            [
                "cargo",
                "build",
                "--profile",
                PROFILE,
                "--features",
                "ros",
                "--bin",
                "trustworthiness_checker",
            ],
            CHECKER_DIR,
        )
        features = ["--features", "ros"]
    _check(["cargo", "build", "--profile", PROFILE, *features], RUNNER_DIR)


def _run_point(
    point: Point,
    config: Config,
    output_dir: Path,
    topic_namespace: str,
) -> dict[str, Any]:
    run_dir = output_dir / "work" / point.name()
    properties, input_map, output_map = write_artefacts(
        run_dir,
        point.property_set,
        point.robots,
        config.window_s,
        config.dwell_s,
        topic_namespace,
    )
    horizon_ms = semantic_horizon_ms(
        point.property_set,
        point.semantics,
        config.window_s,
        config.dwell_s,
    )
    common = [
        "--properties",
        str(properties),
        "--robots",
        str(point.robots),
        "--seed",
        str(point.seed),
        "--duration-s",
        str(config.duration_s),
        "--publish-rate-hz",
        str(config.publish_rate_hz),
        "--sim-hz",
        str(config.sim_hz),
        "--horizon-ms",
        str(horizon_ms),
        "--semantics",
        point.semantics,
    ]
    if point.transport == "direct":
        measurement = _run_direct(common, config)
    else:
        measurement = _run_ros(
            common,
            config,
            run_dir,
            properties,
            input_map,
            output_map,
            point.semantics,
            config.algorithm,
            topic_namespace,
        )
    return {
        "robots": point.robots,
        "seed": point.seed,
        "property_set": point.property_set,
        "transport": point.transport,
        "semantics": point.semantics,
        "algorithm": config.algorithm,
        "ok": measurement.get("latency_samples", 0) > 0,
        "error": None
        if measurement.get("latency_samples", 0) > 0
        else "no latency samples",
        **measurement,
    }


def _run_direct(common: list[str], config: Config) -> dict[str, Any]:
    result = subprocess.run(
        [str(_runner_binary()), "direct", *common],
        cwd=RUNNER_DIR if RUNNER_DIR.is_dir() else _runner_binary().parent,
        capture_output=True,
        text=True,
        timeout=config.duration_s + 60,
    )
    if result.returncode:
        raise RuntimeError(
            result.stderr.strip() or f"runner exited {result.returncode}"
        )
    return json.loads(
        next(line for line in reversed(result.stdout.splitlines()) if line)
    )


def _run_ros(
    common: list[str],
    config: Config,
    run_dir: Path,
    properties: Path,
    input_map: Path,
    output_map: Path,
    semantics: str,
    algorithm: str,
    topic_namespace: str,
) -> dict[str, Any]:
    checker_log = (run_dir / "checker.log").open("wb")
    checker = subprocess.Popen(
        [
            str(_checker_binary()),
            str(properties),
            "--input-ros-file",
            str(input_map),
            "--output-ros-file",
            str(output_map),
            "--language",
            "mstlo",
            "--semantics",
            semantics,
            "--mstlo-algorithm",
            algorithm,
            "--mstlo-synchronization",
            "zero-order-hold",
        ],
        cwd=CHECKER_DIR if CHECKER_DIR.is_dir() else run_dir,
        stdout=subprocess.DEVNULL,
        stderr=checker_log,
        start_new_session=True,
    )
    try:
        time.sleep(config.checker_settle_s)
        result = subprocess.run(
            [
                str(_runner_binary()),
                "ros",
                *common,
                "--output-map",
                str(output_map),
                "--topic-namespace",
                topic_namespace,
                "--discovery-s",
                str(config.discovery_s),
                "--drain-s",
                str(config.drain_s),
            ],
            cwd=RUNNER_DIR if RUNNER_DIR.is_dir() else run_dir,
            capture_output=True,
            text=True,
            timeout=config.duration_s + config.discovery_s + config.drain_s + 60,
        )
        if result.returncode:
            raise RuntimeError(
                result.stderr.strip() or f"ROS runner exited {result.returncode}"
            )
        return json.loads(
            next(line for line in reversed(result.stdout.splitlines()) if line)
        )
    finally:
        _stop(checker, signal.SIGTERM)
        checker_log.close()


def _check(command: list[str], cwd: Path) -> None:
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"{' '.join(command)} failed")


def _stop(process: subprocess.Popen[Any], sig: signal.Signals) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, sig)
        process.wait(timeout=10)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        if process.poll() is None:
            process.kill()
            process.wait()


def _prebuilt_mode() -> bool:
    return os.environ.get("MSTLO_BENCH_PREBUILT", "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _ros_overlay_setup() -> Path:
    configured = os.environ.get("MSTLO_ROS_OVERLAY")
    if configured:
        path = Path(configured)
        return path / "setup.bash" if path.is_dir() else path
    return CHECKER_DIR / "ros_interfaces" / "install" / "setup.bash"


def _validate_binary(path: Path, label: str) -> None:
    if not path.is_file():
        raise RuntimeError(
            f"prebuilt {label} binary not found at {path}; set the corresponding "
            "MSTLO_*_BIN environment variable or rebuild the image"
        )
    if not os.access(path, os.X_OK):
        raise RuntimeError(f"prebuilt {label} binary is not executable: {path}")


def _validate_prebuilt(needs_ros: bool) -> None:
    _validate_binary(_runner_binary(), "runner")
    if not needs_ros:
        return
    _validate_binary(_checker_binary(), "checker")
    ros_setup = Path("/opt/ros") / os.environ.get("ROS_DISTRO", "jazzy") / "setup.bash"
    if not ros_setup.is_file():
        raise RuntimeError(f"ROS setup not found in prebuilt mode: {ros_setup}")
    overlay_setup = _ros_overlay_setup()
    if not overlay_setup.is_file():
        raise RuntimeError(
            f"prebuilt ROS setup for the interface overlay not found at {overlay_setup}; "
            "set MSTLO_ROS_OVERLAY to its setup.bash or overlay directory"
        )


def _runner_binary() -> Path:
    configured = os.environ.get("MSTLO_RUNNER_BIN")
    return (
        Path(configured)
        if configured
        else RUNNER_DIR / "target" / PROFILE / "mstlo-benchmark-runner"
    )


def _checker_binary() -> Path:
    configured = os.environ.get("MSTLO_CHECKER_BIN")
    return (
        Path(configured)
        if configured
        else CHECKER_DIR / "target" / PROFILE / "trustworthiness_checker"
    )
