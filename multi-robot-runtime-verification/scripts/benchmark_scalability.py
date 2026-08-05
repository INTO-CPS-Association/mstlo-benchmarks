#!/usr/bin/env python3
"""Run robot_brownian_sim scalability sweeps and collate benchmark artifacts."""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any


IDL_PACKAGE_FILTER = "std_msgs;geometry_msgs;nav_msgs;id_pose_msgs;robo_sapiens_interfaces"
CLK_TCK = os.sysconf(os.sysconf_names["SC_CLK_TCK"])
PAGE_SIZE = os.sysconf("SC_PAGE_SIZE")
PLOT_FONT_SIZE = 7
PLOT_LABEL_SIZE = 8
PLOT_TICK_SIZE = 7
PLOT_LEGEND_SIZE = 6
DYNAMIC_BOXPLOT_COLOR = "#2ca02c"
DYNAMIC_BOXPLOT_EDGE_COLOR = "#1b5e20"
PAPER_TWO_COLUMN_PANEL_FIGSIZE = (6.1, 2.35)
PAPER_SINGLE_COLUMN_SQUARE_FIGSIZE = (3.95, 3.45)
PROCESS_MEASURED_CACHE: dict[tuple[int, int], Any] = {}

RUN_COLUMNS = [
    "run_id",
    "robots",
    "seed",
    "attempt",
    "max_attempts",
    "duration_secs",
    "warmup_secs",
    "status",
    "returncode",
    "started_unix",
    "ended_unix",
    "run_dir",
    "command",
    "error",
]
SHUTDOWN_ERROR_PATTERNS = (
    "terminate called after throwing an instance",
    "std::system_error",
    "Owner died",
    "what():  Invalid argument",
)
RETRYABLE_STATUSES = {"failed", "timeout", "error"}
PROGRESS_PHASE_WIDTH = max(len("Finished early"), len("Shutdown wait"))
TELEMETRY_FINISHED_EXIT_GRACE_SECS = 5.0
PROCESS_SAMPLE_COLUMNS = [
    "run_id",
    "robots",
    "seed",
    "elapsed_secs",
    "role",
    "role_instance",
    "pid",
    "comm",
    "cmdline",
    "cpu_time_secs",
    "user_cpu_time_secs",
    "system_cpu_time_secs",
    "rss_bytes",
    "threads",
    "sample_unix",
]
ROS_SHM_ROLE = "ros_shm"
TELEMETRY_EVENT_COLUMNS = [
    "run_id",
    "ts_unix_ms",
    "elapsed_secs",
    "role",
    "event_type",
    "payload_json",
]
COVERAGE_SAMPLE_COLUMNS = [
    "run_id",
    "elapsed_secs",
    "tick",
    "possible_property_ticks",
    "covered_possible_property_ticks",
    "coverage",
    "CPred_possible",
    "CPred_covered",
    "SPred_possible",
    "SPred_covered",
    "VPred_possible",
    "VPred_covered",
    "HPred_possible",
    "HPred_covered",
]
RUN_SUMMARY_COLUMNS = [
    "run_id",
    "robots",
    "seed",
    "status",
    "checker_cpu_time_secs",
    "checker_cpu_time_per_measured_sec",
    "scheduler_cpu_time_secs",
    "worker_cpu_time_secs",
    "worker_cpu_time_mean_secs",
    "worker_cpu_time_p95_secs",
    "worker_cpu_imbalance_ratio",
    "checker_max_rss_bytes",
    "scheduler_max_rss_bytes",
    "worker_max_rss_bytes",
    "checker_max_threads",
    "reconfig_messages_received",
    "worker_reconfiguration_events",
    "worker_reconfiguration_events_per_sec",
    "mape_phase_events",
    "scheduler_iterations_per_sec",
    "scheduler_plan_attempts_per_sec",
    "scheduler_successful_plans_per_sec",
    "scheduler_execute_events_per_sec",
    "mape_plan_mean_ms",
    "mape_plan_p95_ms",
    "mape_plan_p99_ms",
    "mape_execute_mean_ms",
    "mape_execute_p95_ms",
    "mape_execute_p99_ms",
    "mape_iteration_total_mean_ms",
    "mape_iteration_total_p50_ms",
    "mape_iteration_total_p95_ms",
    "mape_iteration_total_p99_ms",
    "scheduler_cpu_per_iteration",
    "scheduler_cpu_per_plan_attempt",
    "scheduler_cpu_per_successful_plan",
    "worker_monitoring_step_events",
    "worker_monitoring_steps_per_sec",
    "worker_expr_evaluators_per_sec",
    "worker_non_aux_expr_evaluators_per_sec",
    "worker_eval_ms_per_expr",
    "worker_step_count_imbalance_ratio",
    "worker_monitoring_duration_imbalance_ratio",
    "worker_reconfiguration_imbalance_ratio",
    "worker_monitor_eval_mean_ms",
    "worker_monitor_eval_p95_ms",
    "worker_monitor_eval_p99_ms",
    "worker_monitor_step_mean_ms",
    "worker_monitor_step_p95_ms",
    "worker_monitor_step_p99_ms",
    "constraint_monitoring_events",
    "constraint_monitoring_mean_ms",
    "constraint_monitoring_p95_ms",
    "sat_solver_events",
    "sat_solve_events",
    "sat_fast_path_events",
    "sat_solve_mean_ms",
    "sat_solve_p95_ms",
    "sat_solve_max_ms",
    "sat_solver_ms_per_clause",
    "sat_solver_ms_per_var",
    "sat_solver_ms_per_constraint",
    "sat_solver_ms_per_assigned_stream",
    "sat_terminal_mean_ms",
    "sat_terminal_p95_ms",
    "sat_total_mean_ms",
    "sat_cnf_clauses_max",
    "sat_cnf_vars_max",
    "pose_publish_failure_rate",
    "pose_publish_failures_per_sec",
    "reconfiguration_latency_p50_ms",
    "reconfiguration_latency_p95_ms",
    "reconfiguration_latency_p99_ms",
    "coverage_mean",
    "coverage_p05",
    "coverage_p50",
    "coverage_p95",
    "coverage_min",
    "telemetry_events",
    "first_reconfig_elapsed_secs",
]
CHECKER_PROCESS_SUMMARY_COLUMNS = [
    "run_id",
    "robots",
    "seed",
    "role",
    "role_instance",
    "pid",
    "cpu_time_secs",
    "user_cpu_time_secs",
    "system_cpu_time_secs",
    "cpu_time_per_measured_sec",
    "user_cpu_time_per_measured_sec",
    "system_cpu_time_per_measured_sec",
    "rss_bytes",
    "rss_mib",
    "threads",
]
WORKER_RECONFIGURATION_COLUMNS = [
    "run_id",
    "robots",
    "seed",
    "elapsed_secs",
    "worker",
    "input_var_count",
    "output_var_count",
    "active_tasks",
    "global_tasks",
    "sleepers",
    "input_vars_json",
    "output_vars_json",
    "source",
]
SCHEDULER_MAPE_PHASE_COLUMNS = [
    "run_id",
    "robots",
    "seed",
    "elapsed_secs",
    "role",
    "phase",
    "tick",
    "duration_ms",
    "constraints_hold",
    "should_plan",
    "should_execute",
    "plan_succeeded",
    "source",
]
SAT_SOLVER_EVENT_COLUMNS = [
    "run_id",
    "robots",
    "seed",
    "elapsed_secs",
    "role",
    "phase",
    "result",
    "fast_path",
    "forced_sat",
    "duration_ms",
    "total_duration_ms",
    "nodes",
    "edges",
    "constraints",
    "outputs",
    "assigned_streams",
    "clauses",
    "vars",
    "atoms",
    "bound_values",
    "source",
]
WORKER_MONITORING_STEP_COLUMNS = [
    "run_id",
    "robots",
    "seed",
    "elapsed_secs",
    "role",
    "worker",
    "context_id",
    "expr_evaluator_count",
    "non_aux_expr_evaluator_count",
    "aux_var_count",
    "forward_state",
    "eval_state",
    "forward_values_duration_ms",
    "eval_expr_duration_ms",
    "duration_ms",
    "source",
]
CONSTRAINT_MONITORING_COLUMNS = [
    "run_id",
    "robots",
    "seed",
    "elapsed_secs",
    "role",
    "stream_count",
    "values_received",
    "constraints_hold",
    "duration_ms",
    "source",
]


def main() -> int:
    args, sim_extra_args = parse_args()
    require_python_packages()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    if args.analyse_only:
        analyse_existing_outputs(args.output_dir)
        return 0

    robots = parse_int_list(args.robots)
    seeds = parse_int_list(args.seeds)
    args.progress_robot_width = max(len(str(robot_count)) for robot_count in robots)
    args.progress_seed_width = max(len(str(seed)) for seed in seeds)

    simulator_binary = prebuild_simulator(args)
    if not args.no_ros:
        prebuild_trustworthiness_checker(args)

    run_rows: list[dict[str, Any]] = []
    process_rows: list[dict[str, Any]] = []
    telemetry_rows: list[dict[str, Any]] = []
    coverage_rows: list[dict[str, Any]] = []
    benchmarks = [(robot_count, seed) for robot_count in robots for seed in seeds]
    total_benchmarks = len(benchmarks)

    max_attempts = args.retries + 1
    for benchmark_index, (robot_count, seed) in enumerate(benchmarks, start=1):
        benchmark_label = f"[{benchmark_index}/{total_benchmarks}]"
        base_run_id = f"robots-{robot_count}_seed-{seed}_{int(time.time())}"
        for attempt in range(1, max_attempts + 1):
            clean_ros_shared_memory()
            run_id = base_run_id if attempt == 1 else f"{base_run_id}_attempt-{attempt}"
            run_dir = args.output_dir / "raw" / run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            started = time.time()
            command = build_command(
                simulator_binary,
                args,
                sim_extra_args,
                robot_count,
                seed,
                run_id,
                run_dir,
            )
            row = {
                "run_id": run_id,
                "robots": robot_count,
                "seed": seed,
                "attempt": attempt,
                "max_attempts": max_attempts,
                "duration_secs": args.duration,
                "warmup_secs": args.warmup,
                "status": "running",
                "returncode": None,
                "started_unix": started,
                "ended_unix": None,
                "run_dir": str(run_dir),
                "command": " ".join(command),
            }
            run_rows.append(row)
            attempt_label = f"attempt {attempt}/{max_attempts}"
            stdout = None
            stderr = None
            proc = None
            try:
                stdout = open(run_dir / "simulator.stdout.log", "w", encoding="utf-8")
                stderr = open(run_dir / "simulator.stderr.log", "w", encoding="utf-8")
                proc = subprocess.Popen(
                    command,
                    cwd=args.repo_dir,
                    stdout=stdout,
                    stderr=stderr,
                    start_new_session=True,
                )
                timed_out = sample_processes(
                    proc.pid,
                    run_id,
                    robot_count,
                    seed,
                    benchmark_index,
                    total_benchmarks,
                    run_dir,
                    process_rows,
                    proc,
                    args,
                )
                if timed_out:
                    raise subprocess.TimeoutExpired(command, effective_timeout(args))
                returncode = proc.returncode
                completed_by_telemetry = telemetry_has_finished(run_dir, run_id)
                stderr_text = read_text(run_dir / "simulator.stderr.log")
                shutdown_error = stderr_contains_shutdown_error(stderr_text)
                row["returncode"] = returncode
                if completed_by_telemetry:
                    row["status"] = "ok"
                    if returncode != 0:
                        append_run_error(
                            row,
                            "telemetry completed, but simulator exited with "
                            f"return code {returncode}",
                        )
                    if shutdown_error:
                        append_run_error(
                            row,
                            "post-telemetry simulator stderr contains shutdown/system error",
                        )
                else:
                    row["status"] = "failed"
                    if shutdown_error:
                        row["error"] = "simulator stderr contains shutdown/system error"
            except subprocess.TimeoutExpired:
                row["status"] = "timeout"
                if proc is not None:
                    terminate_process_group(proc)
                    row["returncode"] = proc.wait(timeout=10)
            except KeyboardInterrupt:
                row["status"] = "interrupted"
                if proc is not None:
                    terminate_process_group(proc)
                raise
            except Exception as exc:  # noqa: BLE001
                row["status"] = "error"
                row["error"] = str(exc)
            finally:
                row["ended_unix"] = time.time()
                if stdout:
                    stdout.close()
                if stderr:
                    stderr.close()

            malformed_telemetry_lines = ingest_telemetry(
                run_dir / "telemetry_events.jsonl",
                telemetry_rows,
                coverage_rows,
            )
            record_malformed_telemetry(row, malformed_telemetry_lines)
            print(
                f"{benchmark_label} [{run_id}] {row['status']} ({attempt_label})",
                flush=True,
            )
            if row["status"] not in RETRYABLE_STATUSES:
                break
            if attempt < max_attempts:
                print(
                    f"{benchmark_label} [{run_id}] retrying after {row['status']}",
                    flush=True,
                )

    write_outputs(args.output_dir, run_rows, process_rows, telemetry_rows, coverage_rows)
    print(f"wrote benchmark outputs to {args.output_dir}")
    return 0


def parse_args() -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser()
    parser.add_argument("--robots", default="5,10,20,30,40")
    parser.add_argument("--seeds", default="123")
    parser.add_argument("--duration", type=float, default=120.0)
    parser.add_argument("--warmup", type=float, default=20.0)
    parser.add_argument("--output-dir", type=Path, default=Path("target/scalability-benchmarks"))
    parser.add_argument("--repo-dir", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--no-ros", action="store_true", help="smoke-test mode; disables ROS and TC")
    parser.add_argument("--profile", default="release", choices=["dev", "release"])
    parser.add_argument(
        "--trustworthiness-checker-dir",
        type=Path,
        default=Path("../robosapiens-trustworthiness-checker"),
    )
    parser.add_argument("--trustworthiness-checker-profile", default="dev-fast")
    parser.add_argument(
        "--trustworthiness-checker-ros-setup",
        type=Path,
        default=Path(
            "../robosapiens-trustworthiness-checker/ros_interfaces/install/local_setup.bash"
        ),
    )
    parser.add_argument("--sample-interval", type=float, default=1.0)
    parser.add_argument("--timeout", type=float, default=None)
    parser.add_argument(
        "--retries",
        type=non_negative_int,
        default=5,
        help="number of times to retry a failed, timed out, or errored benchmark run",
    )
    parser.add_argument(
        "--analyse-only",
        "--analyze-only",
        action="store_true",
        dest="analyse_only",
        help="regenerate derived Parquet files and plots from existing Parquet inputs",
    )
    return parser.parse_known_args()


def parse_int_list(value: str) -> list[int]:
    items = [int(item.strip()) for item in value.split(",") if item.strip()]
    if not items:
        raise SystemExit("expected at least one integer")
    return items


def non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("expected a non-negative integer")
    return parsed


def require_python_packages() -> None:
    missing = []
    for name in ["pandas", "pyarrow", "matplotlib", "tqdm"]:
        try:
            __import__(name)
        except ImportError:
            missing.append(name)
    if missing:
        raise SystemExit(
            "missing benchmark Python packages: "
            + ", ".join(missing)
            + "; install pandas pyarrow matplotlib"
        )


def build_command(
    simulator_binary: Path,
    args: argparse.Namespace,
    sim_extra_args: list[str],
    robots: int,
    seed: int,
    run_id: str,
    run_dir: Path,
) -> list[str]:
    command = [str(simulator_binary)]
    command.extend(
        [
            "--robots",
            str(robots),
            "--seed",
            str(seed),
            "--benchmark-duration-secs",
            str(args.duration),
            "--benchmark-warmup-secs",
            str(args.warmup),
            "--benchmark-output-dir",
            str(run_dir),
            "--benchmark-run-id",
            run_id,
        ]
    )
    if args.no_ros:
        command.append("--no-ros")
    else:
        command.extend(
            [
                "--trustworthiness-checker",
                "--trustworthiness-checker-dir",
                str(resolve_from_repo(args.repo_dir, args.trustworthiness_checker_dir)),
                "--trustworthiness-checker-profile",
                args.trustworthiness_checker_profile,
                "--trustworthiness-checker-ros-setup",
                str(resolve_from_repo(args.repo_dir, args.trustworthiness_checker_ros_setup)),
            ]
        )
    command.extend(sim_extra_args)
    return command


def prebuild_simulator(args: argparse.Namespace) -> Path:
    command = ["cargo", "build"]
    if args.profile == "release":
        command.append("--release")

    log_dir = args.output_dir / "prebuild"
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = log_dir / "simulator.stdout.log"
    stderr_path = log_dir / "simulator.stderr.log"
    print(f"prebuilding simulator profile={args.profile}", flush=True)
    with open(stdout_path, "w", encoding="utf-8") as stdout, open(
        stderr_path, "w", encoding="utf-8"
    ) as stderr:
        result = subprocess.run(
            command,
            cwd=args.repo_dir,
            stdout=stdout,
            stderr=stderr,
            check=False,
        )
    if result.returncode != 0:
        raise SystemExit(
            f"simulator prebuild failed with exit code {result.returncode}; see {stderr_path}"
        )

    binary = args.repo_dir / "target" / simulator_target_dir(args.profile) / "robot_brownian_sim"
    if not binary.is_file():
        raise SystemExit(f"simulator prebuild completed but binary was not found: {binary}")
    return binary


def prebuild_trustworthiness_checker(args: argparse.Namespace) -> None:
    checker_dir = resolve_from_repo(args.repo_dir, args.trustworthiness_checker_dir)
    if not checker_dir.is_dir():
        raise SystemExit(f"trustworthiness checker directory does not exist: {checker_dir}")

    command = [
        "cargo",
        "build",
        "--profile",
        args.trustworthiness_checker_profile,
        "--features",
        "ros",
        "--bin",
        "trustworthiness_checker",
    ]
    log_dir = args.output_dir / "prebuild"
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = log_dir / "trustworthiness_checker.stdout.log"
    stderr_path = log_dir / "trustworthiness_checker.stderr.log"
    env = trustworthiness_checker_build_env(args)

    print(
        "prebuilding trustworthiness checker "
        f"profile={args.trustworthiness_checker_profile} dir={checker_dir}",
        flush=True,
    )
    with open(stdout_path, "w", encoding="utf-8") as stdout, open(
        stderr_path, "w", encoding="utf-8"
    ) as stderr:
        result = subprocess.run(
            command,
            cwd=checker_dir,
            env=env,
            stdout=stdout,
            stderr=stderr,
            check=False,
        )

    if result.returncode != 0:
        raise SystemExit(
            "trustworthiness checker prebuild failed "
            f"with exit code {result.returncode}; see {stderr_path}"
        )

    binary = (
        checker_dir
        / "target"
        / profile_target_dir(args.trustworthiness_checker_profile)
        / "trustworthiness_checker"
    )
    if not binary.is_file():
        raise SystemExit(
            "trustworthiness checker prebuild completed but binary was not found: "
            f"{binary}"
        )


def trustworthiness_checker_build_env(args: argparse.Namespace) -> dict[str, str]:
    env = os.environ.copy()
    setup = resolve_from_repo(args.repo_dir, args.trustworthiness_checker_ros_setup)
    if setup.is_file():
        env.update(load_shell_env_after_sourcing(setup))
    else:
        print(
            "trustworthiness checker ROS setup not found; using current environment only: "
            f"{setup}",
            flush=True,
        )
    env["IDL_PACKAGE_FILTER"] = IDL_PACKAGE_FILTER
    return env


def load_shell_env_after_sourcing(setup: Path) -> dict[str, str]:
    output = subprocess.run(
        ["bash", "-lc", f"source {sh_single_quote(setup)} && env -0"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if output.returncode != 0:
        raise SystemExit(
            f"failed to source trustworthiness checker ROS setup {setup}: "
            f"{output.stderr.decode(errors='replace')}"
        )
    env: dict[str, str] = {}
    for entry in output.stdout.split(b"\0"):
        if not entry or b"=" not in entry:
            continue
        key, value = entry.split(b"=", 1)
        env[key.decode(errors="surrogateescape")] = value.decode(errors="surrogateescape")
    return env


def profile_target_dir(profile: str) -> str:
    if profile == "dev":
        return "debug"
    if profile == "release":
        return "release"
    return profile


def simulator_target_dir(profile: str) -> str:
    if profile == "release":
        return "release"
    return "debug"


def resolve_from_repo(repo_dir: Path, path: Path) -> Path:
    if path.is_absolute():
        return path
    return (repo_dir / path).resolve()


def sh_single_quote(path: Path) -> str:
    return "'" + str(path).replace("'", "'\\''") + "'"


def sample_processes(
    root_pid: int,
    run_id: str,
    robots: int,
    seed: int,
    benchmark_index: int,
    total_benchmarks: int,
    run_dir: Path,
    rows: list[dict[str, Any]],
    proc: subprocess.Popen[Any],
    args: argparse.Namespace,
) -> bool:
    from tqdm import tqdm

    started = time.time()
    timeout_at = started + effective_timeout(args)
    expected_run_secs = args.duration + args.warmup
    progress_label = format_progress_label(
        benchmark_index,
        total_benchmarks,
        robots,
        seed,
        args,
    )
    progress_seconds_width = len(f"{expected_run_secs:.1f}")
    analysing = False

    class BenchmarkTqdm(tqdm):
        @property
        def format_dict(self) -> dict[str, Any]:
            values = super().format_dict
            values["raw_postfix"] = self.postfix or ""
            return values

    with BenchmarkTqdm(
        total=expected_run_secs,
        desc=progress_label,
        unit="s",
        dynamic_ncols=True,
        leave=True,
        bar_format="{desc}: {bar}| {percentage:3.0f}% [ {raw_postfix} ]",
    ) as progress:
        while proc.poll() is None and time.time() < timeout_at:
            elapsed = time.time() - started
            if elapsed <= expected_run_secs:
                progress.update(max(0.0, elapsed - progress.n))
                set_progress_status(
                    progress,
                    "warmup" if elapsed < args.warmup else "measure",
                    elapsed,
                    expected_run_secs,
                    progress_seconds_width,
                )
            elif not analysing:
                progress.update(max(0.0, expected_run_secs - progress.n))
                set_progress_status(
                    progress,
                    "analysing",
                    expected_run_secs,
                    expected_run_secs,
                    progress_seconds_width,
                )
                progress.clear()
                progress.close()
                analysing = True

            if elapsed >= expected_run_secs and telemetry_has_finished(run_dir, run_id):
                progress.update(max(0.0, expected_run_secs - progress.n))
                set_progress_status(
                    progress,
                    "shutdown wait",
                    expected_run_secs,
                    expected_run_secs,
                    progress_seconds_width,
                )
                if proc.poll() is None:
                    try:
                        proc.wait(timeout=TELEMETRY_FINISHED_EXIT_GRACE_SECS)
                    except subprocess.TimeoutExpired:
                        terminate_process_group(proc)
                set_progress_status(
                    progress,
                    "finished",
                    expected_run_secs,
                    expected_run_secs,
                    progress_seconds_width,
                )
                return False

            for pid in process_tree(root_pid):
                sample = read_proc_sample(pid)
                if sample:
                    sample.update(
                        {
                            "run_id": run_id,
                            "robots": robots,
                            "seed": seed,
                            "elapsed_secs": elapsed,
                            "role": process_role(pid, root_pid),
                            "role_instance": process_role_instance(pid),
                        }
                    )
                    rows.append(sample)
            rows.append(read_ros_shm_sample(run_id, robots, seed, elapsed))
            time.sleep(args.sample_interval)

        elapsed = time.time() - started
        if not analysing:
            progress.update(max(0.0, min(elapsed, expected_run_secs) - progress.n))
            if proc.poll() is None and time.time() >= timeout_at:
                set_progress_status(
                    progress,
                    "timeout",
                    elapsed,
                    expected_run_secs,
                    progress_seconds_width,
                )
            elif elapsed < expected_run_secs:
                set_progress_status(
                    progress,
                    "finished early",
                    elapsed,
                    expected_run_secs,
                    progress_seconds_width,
                )
            else:
                set_progress_status(
                    progress,
                    "finished",
                    expected_run_secs,
                    expected_run_secs,
                    progress_seconds_width,
                )
    return proc.poll() is None and time.time() >= timeout_at


def format_progress_label(
    benchmark_index: int,
    total_benchmarks: int,
    robots: int,
    seed: int,
    args: argparse.Namespace,
) -> str:
    index_width = len(str(total_benchmarks))
    robot_width = getattr(args, "progress_robot_width", len(str(robots)))
    seed_width = getattr(args, "progress_seed_width", len(str(seed)))
    return (
        f"[{benchmark_index:>{index_width}}/{total_benchmarks}] "
        f"robots={robots:>{robot_width}} seed={seed:>{seed_width}}"
    )


def progress_status(phase: str, elapsed: float, total: float, seconds_width: int) -> str:
    label = phase.capitalize()
    return (
        f"{label:<{PROGRESS_PHASE_WIDTH}} "
        f"{min(elapsed, total):>{seconds_width}.1f}/{total:>{seconds_width}.1f}s"
    )


def set_progress_status(
    progress: Any,
    phase: str,
    elapsed: float,
    total: float,
    seconds_width: int,
) -> None:
    progress.postfix = progress_status(phase, elapsed, total, seconds_width)
    progress.refresh()


def telemetry_has_finished(run_dir: Path, run_id: str) -> bool:
    path = run_dir / "telemetry_events.jsonl"
    events, _malformed_lines = read_telemetry_events(path)
    for event in reversed(events):
        return (
            event.get("run_id") == run_id
            and event.get("event_type") == "benchmark_run_finished"
        )
    return False


def effective_timeout(args: argparse.Namespace) -> float:
    if args.timeout is not None:
        return args.timeout
    return args.duration + args.warmup + 180.0


def process_tree(root_pid: int) -> list[int]:
    parents: dict[int, int] = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        stat = read_text(entry / "stat")
        if not stat:
            continue
        try:
            after_comm = stat.rsplit(")", 1)[1].strip().split()
            parents[int(entry.name)] = int(after_comm[1])
        except (IndexError, ValueError):
            continue

    tree = [root_pid]
    changed = True
    while changed:
        changed = False
        known = set(tree)
        for pid, ppid in parents.items():
            if ppid in known and pid not in known:
                tree.append(pid)
                changed = True
    return tree


def read_proc_sample(pid: int) -> dict[str, Any] | None:
    proc_dir = Path("/proc") / str(pid)
    stat = read_text(proc_dir / "stat")
    status = read_text(proc_dir / "status")
    if not stat or not status:
        return None
    try:
        fields = stat.rsplit(")", 1)[1].strip().split()
        utime = int(fields[11]) / CLK_TCK
        stime = int(fields[12]) / CLK_TCK
        rss_bytes = int(fields[21]) * PAGE_SIZE
    except (IndexError, ValueError):
        return None
    thread_count = None
    for line in status.splitlines():
        if line.startswith("Threads:"):
            thread_count = int(line.split()[1])
            break
    return {
        "pid": pid,
        "comm": read_text(proc_dir / "comm").strip(),
        "cmdline": read_text(proc_dir / "cmdline").replace("\x00", " ").strip(),
        "cpu_time_secs": utime + stime,
        "user_cpu_time_secs": utime,
        "system_cpu_time_secs": stime,
        "rss_bytes": rss_bytes,
        "threads": thread_count,
        "sample_unix": time.time(),
    }


def read_ros_shm_sample(
    run_id: str,
    robots: int,
    seed: int,
    elapsed: float,
) -> dict[str, Any]:
    shm_bytes, shm_files = ros_shared_memory_usage()
    return {
        "run_id": run_id,
        "robots": robots,
        "seed": seed,
        "elapsed_secs": elapsed,
        "role": ROS_SHM_ROLE,
        "role_instance": "fastrtps",
        "pid": None,
        "comm": "fastdds_shm",
        "cmdline": f"{shm_files} fastrtps shared-memory file(s)",
        "cpu_time_secs": None,
        "user_cpu_time_secs": None,
        "system_cpu_time_secs": None,
        "rss_bytes": shm_bytes,
        "threads": None,
        "sample_unix": time.time(),
    }


def ros_shared_memory_usage() -> tuple[int, int]:
    total = 0
    count = 0
    for path in Path("/dev/shm").glob("fastrtps*"):
        try:
            total += path.stat().st_size
            count += 1
        except OSError:
            continue
    return total, count


def clean_ros_shared_memory() -> None:
    try:
        result = subprocess.run(
            ["fastdds", "shm", "clean"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError:
        return
    if result.returncode != 0 and result.stderr.strip():
        print(f"warning: fastdds shm clean failed: {result.stderr.strip()}", flush=True)


def process_role(pid: int, root_pid: int) -> str:
    cmdline = read_text(Path("/proc") / str(pid) / "cmdline").replace("\x00", " ")
    if "properties_pub.py" in cmdline:
        return "property_emulator"
    if "reconf-semi-sync" in cmdline or "--local-node" in cmdline:
        return "worker"
    if "--scheduling-mode" in cmdline or "tc_scheduler_main" in cmdline:
        return "scheduler"
    if "trustworthiness_checker" in cmdline:
        return "trustworthiness_checker"
    if "robot_brownian_sim" in cmdline:
        return "simulator"
    if pid == root_pid:
        return "simulator"
    return "child"


def process_role_instance(pid: int) -> str | None:
    cmdline = read_text(Path("/proc") / str(pid) / "cmdline").replace("\x00", " ")
    local_node = re.search(r"--local-node\s+(R\d+)", cmdline)
    if local_node:
        return local_node.group(1)
    scheduler_node = re.search(r"--scheduler-ros-node-name\s+(\S+)", cmdline)
    if scheduler_node:
        return scheduler_node.group(1)
    if "properties_pub.py" in cmdline:
        return "property_emulator"
    program = cmdline.split(" ", 1)[0]
    if program.endswith("robot_brownian_sim"):
        return "simulator"
    return None


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def read_telemetry_events(path: Path) -> tuple[list[dict[str, Any]], int]:
    if not path.is_file():
        return [], 0
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return [], 0

    events = []
    malformed_lines = 0
    for line in lines:
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            malformed_lines += 1
            continue
        if isinstance(event, dict):
            events.append(event)
        else:
            malformed_lines += 1
    return events, malformed_lines


def record_malformed_telemetry(row: dict[str, Any], malformed_lines: int) -> None:
    if malformed_lines <= 0:
        return
    if row.get("status") == "ok":
        row["status"] = "failed"
    append_run_error(row, f"skipped {malformed_lines} malformed telemetry line(s)")


def append_run_error(row: dict[str, Any], message: str) -> None:
    existing = row.get("error")
    if existing:
        row["error"] = f"{existing}; {message}"
    else:
        row["error"] = message


def stderr_contains_shutdown_error(stderr_text: str) -> bool:
    return any(pattern in stderr_text for pattern in SHUTDOWN_ERROR_PATTERNS)


def terminate_process_group(proc: subprocess.Popen[Any]) -> None:
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=10)
    except Exception:  # noqa: BLE001
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except Exception:  # noqa: BLE001
            pass


def ingest_telemetry(
    path: Path,
    telemetry_rows: list[dict[str, Any]],
    coverage_rows: list[dict[str, Any]],
) -> int:
    events, malformed_lines = read_telemetry_events(path)
    for event in events:
        payload = event.get("payload") or {}
        telemetry_rows.append(
            {
                "run_id": event.get("run_id"),
                "ts_unix_ms": event.get("ts_unix_ms"),
                "elapsed_secs": event.get("elapsed_secs"),
                "role": event.get("role"),
                "event_type": event.get("event_type"),
                "payload_json": json.dumps(payload, sort_keys=True),
            }
        )
        if event.get("event_type") == "coverage_sample":
            row = {
                "run_id": event.get("run_id"),
                "elapsed_secs": event.get("elapsed_secs"),
                "tick": payload.get("tick"),
                "possible_property_ticks": payload.get("possible_property_ticks"),
                "covered_possible_property_ticks": payload.get("covered_possible_property_ticks"),
                "coverage": payload.get("coverage"),
            }
            per_property = payload.get("per_property") or {}
            for name, sample in per_property.items():
                row[f"{name}_possible"] = sample.get("possible")
                row[f"{name}_covered"] = sample.get("covered")
            coverage_rows.append(row)
        if event.get("event_type") == "benchmark_run_started":
            checker_dir = payload.get("trustworthiness_checker_run_dir")
            if checker_dir:
                ingest_checker_logs(
                    Path(checker_dir),
                    event.get("run_id"),
                    telemetry_rows,
                    event.get("ts_unix_ms"),
                )
    return malformed_lines


def ingest_checker_logs(
    checker_run_dir: Path,
    run_id: str,
    telemetry_rows: list[dict[str, Any]],
    run_start_ts_unix_ms: int | None = None,
) -> None:
    tracing_dir = checker_run_dir / "logs" / "tracing"
    if not tracing_dir.is_dir():
        return
    for path in tracing_dir.glob("*.log"):
        role = "scheduler" if "scheduler" in path.name else "worker"
        worker = worker_name_from_trace_path(path)
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            elapsed_secs = trace_elapsed_secs(line, run_start_ts_unix_ms)
            mape_phase = mape_phase_from_line(line)
            if mape_phase:
                telemetry_rows.append(
                    {
                        "run_id": run_id,
                        "ts_unix_ms": None,
                        "elapsed_secs": elapsed_secs,
                        "role": role,
                        "event_type": "scheduler_mape_phase",
                        "payload_json": json.dumps(mape_phase | {"source": str(path)}, sort_keys=True),
                    }
                )
            constraint_monitoring = constraint_monitoring_from_line(line)
            if constraint_monitoring:
                telemetry_rows.append(
                    {
                        "run_id": run_id,
                        "ts_unix_ms": None,
                        "elapsed_secs": elapsed_secs,
                        "role": role,
                        "event_type": "constraint_monitoring",
                        "payload_json": json.dumps(
                            constraint_monitoring | {"source": str(path)},
                            sort_keys=True,
                        ),
                    }
                )
            sat_event = sat_solver_event_from_line(line)
            if sat_event:
                telemetry_rows.append(
                    {
                        "run_id": run_id,
                        "ts_unix_ms": None,
                        "elapsed_secs": elapsed_secs,
                        "role": role,
                        "event_type": "sat_solver",
                        "payload_json": json.dumps(sat_event | {"source": str(path)}, sort_keys=True),
                    }
                )
            monitoring_step = monitoring_step_from_line(line)
            if monitoring_step:
                telemetry_rows.append(
                    {
                        "run_id": run_id,
                        "ts_unix_ms": None,
                        "elapsed_secs": elapsed_secs,
                        "role": role,
                        "event_type": "worker_monitoring_step",
                        "payload_json": json.dumps(
                            monitoring_step | {"source": str(path), "worker": worker},
                            sort_keys=True,
                        ),
                    }
                )
            reconfig = worker_reconfiguration_from_line(line)
            if reconfig:
                reconfig.update({"source": str(path), "worker": worker, "line": strip_ansi(line)[:500]})
                telemetry_rows.append(
                    {
                        "run_id": run_id,
                        "ts_unix_ms": None,
                        "elapsed_secs": elapsed_secs,
                        "role": role,
                        "event_type": "worker_reconfiguration",
                        "payload_json": json.dumps(reconfig, sort_keys=True),
                    }
                )


def mape_phase_from_line(line: str) -> dict[str, Any] | None:
    clean = strip_ansi(line)
    if "benchmark_mape_phase" not in clean:
        return legacy_scheduler_phase_from_line(clean)
    fields = tracing_fields(clean)
    if fields.get("event") != "benchmark_mape_phase":
        return None
    return {
        "phase": normalize_mape_phase(fields.get("phase")),
        "duration_ms": float_or_none(fields.get("duration_ms")),
        "tick": int_or_none(fields.get("tick")),
        "constraints_hold": bool_or_none(fields.get("constraints_hold")),
        "should_plan": bool_or_none(fields.get("should_plan")),
        "should_execute": bool_or_none(fields.get("should_execute")),
        "plan_succeeded": bool_or_none(fields.get("plan_succeeded")),
    }


def sat_solver_event_from_line(line: str) -> dict[str, Any] | None:
    clean = strip_ansi(line)
    if "benchmark_sat_solver" not in clean:
        return None
    fields = tracing_fields(clean)
    if fields.get("event") != "benchmark_sat_solver":
        return None
    return {
        "phase": fields.get("phase"),
        "result": fields.get("result"),
        "fast_path": bool_or_none(fields.get("fast_path")),
        "forced_sat": bool_or_none(fields.get("forced_sat")),
        "duration_ms": float_or_none(fields.get("duration_ms")),
        "total_duration_ms": float_or_none(fields.get("total_duration_ms")),
        "nodes": int_or_none(fields.get("nodes")),
        "edges": int_or_none(fields.get("edges")),
        "constraints": int_or_none(fields.get("constraints")),
        "outputs": int_or_none(fields.get("outputs")),
        "assigned_streams": int_or_none(fields.get("assigned_streams")),
        "clauses": int_or_none(fields.get("clauses")),
        "vars": int_or_none(fields.get("vars")),
        "atoms": int_or_none(fields.get("atoms")),
        "bound_values": int_or_none(fields.get("bound_values")),
    }


def monitoring_step_from_line(line: str) -> dict[str, Any] | None:
    clean = strip_ansi(line)
    if "benchmark_monitoring_step" not in clean:
        return None
    fields = tracing_fields(clean)
    if fields.get("event") != "benchmark_monitoring_step":
        return None
    return {
        "context_id": int_or_none(fields.get("context_id")),
        "expr_evaluator_count": int_or_none(fields.get("expr_evaluator_count")),
        "non_aux_expr_evaluator_count": int_or_none(fields.get("non_aux_expr_evaluator_count")),
        "aux_var_count": int_or_none(fields.get("aux_var_count")),
        "forward_state": fields.get("forward_state"),
        "eval_state": fields.get("eval_state"),
        "forward_values_duration_ms": float_or_none(fields.get("forward_values_duration_ms")),
        "eval_expr_duration_ms": float_or_none(fields.get("eval_expr_duration_ms")),
        "duration_ms": float_or_none(fields.get("duration_ms")),
    }


def constraint_monitoring_from_line(line: str) -> dict[str, Any] | None:
    clean = strip_ansi(line)
    if "benchmark_constraint_monitoring" not in clean:
        return None
    fields = tracing_fields(clean)
    if fields.get("event") != "benchmark_constraint_monitoring":
        return None
    return {
        "stream_count": int_or_none(fields.get("stream_count")),
        "values_received": int_or_none(fields.get("values_received")),
        "constraints_hold": bool_or_none(fields.get("constraints_hold")),
        "duration_ms": float_or_none(fields.get("duration_ms")),
    }


def legacy_scheduler_phase_from_line(line: str) -> dict[str, Any] | None:
    lower = line.lower()
    phase = None
    for candidate in ["monitor", "analyse", "analyze", "plan", "execute"]:
        if candidate in lower:
            phase = "analyse" if candidate == "analyze" else candidate
            break
    if not phase:
        return None
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(ms|millis|s|sec|secs|seconds|us|µs)", lower)
    if not match:
        return None
    value = float(match.group(1))
    unit = match.group(2)
    if unit in {"s", "sec", "secs", "seconds"}:
        value *= 1000.0
    elif unit in {"us", "µs"}:
        value /= 1000.0
    return {"phase": phase, "duration_ms": value}


def normalize_mape_phase(phase: str | None) -> str | None:
    if phase == "monitor_analyse":
        return "monitor"
    return phase


def tracing_fields(line: str) -> dict[str, str]:
    fields = {}
    for key, value in re.findall(r"(\w+)=((?:\"[^\"]*\")|(?:\S+))", line):
        fields[key] = value.strip('"').rstrip(",")
    return fields


def float_or_none(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def int_or_none(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def bool_or_none(value: str | None) -> bool | None:
    if value is None:
        return None
    if value == "true":
        return True
    if value == "false":
        return False
    return None


def worker_name_from_trace_path(path: Path) -> str | None:
    match = re.search(r"worker_(\d+)\.tracing\.log", path.name)
    if not match:
        return None
    return f"R{int(match.group(1)) + 1}"


def trace_elapsed_secs(line: str, run_start_ts_unix_ms: int | None) -> float | None:
    if run_start_ts_unix_ms is None:
        return None
    clean = strip_ansi(line)
    match = re.match(r"(\d{4}-\d{2}-\d{2}T[0-9:.]+Z)", clean)
    if not match:
        return None
    try:
        timestamp = datetime.fromisoformat(match.group(1).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None
    return timestamp - (run_start_ts_unix_ms / 1000.0)


def worker_reconfiguration_from_line(line: str) -> dict[str, Any] | None:
    clean = strip_ansi(line)
    if "Reconfiguring ReconfSemiSyncMonitor" not in clean:
        return None
    input_vars = sorted(set(re.findall(r'input_vars: \{([^}]*)\}', clean)))
    output_vars = sorted(set(re.findall(r'output_vars: \{([^}]*)\}', clean)))
    input_names = var_names_from_groups(input_vars)
    output_names = var_names_from_groups(output_vars)
    active = int_match(r"active: (\d+)", clean)
    global_tasks = int_match(r"global_tasks: (\d+)", clean)
    sleepers = int_match(r"sleepers: (\d+)", clean)
    return {
        "input_vars": input_names,
        "output_vars": output_names,
        "input_var_count": len(input_names),
        "output_var_count": len(output_names),
        "active_tasks": active,
        "global_tasks": global_tasks,
        "sleepers": sleepers,
    }


def var_names_from_groups(groups: list[str]) -> list[str]:
    names: set[str] = set()
    for group in groups:
        names.update(re.findall(r'VarName::new\("([^"]+)"\)', group))
    return sorted(names)


def int_match(pattern: str, text: str) -> int | None:
    match = re.search(pattern, text)
    return int(match.group(1)) if match else None


def strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def write_outputs(
    output_dir: Path,
    run_rows: list[dict[str, Any]],
    process_rows: list[dict[str, Any]],
    telemetry_rows: list[dict[str, Any]],
    coverage_rows: list[dict[str, Any]],
) -> None:
    import pandas as pd

    runs = dataframe_with_columns(pd, run_rows, RUN_COLUMNS)
    process = dataframe_with_columns(pd, process_rows, PROCESS_SAMPLE_COLUMNS)
    telemetry = dataframe_with_columns(pd, telemetry_rows, TELEMETRY_EVENT_COLUMNS)
    coverage = dataframe_with_columns(pd, coverage_rows, COVERAGE_SAMPLE_COLUMNS)
    write_output_frames(output_dir, runs, process, telemetry, coverage)


def analyse_existing_outputs(output_dir: Path) -> None:
    import pandas as pd
    import polars as pl

    required = [
        "runs.parquet",
        "process_samples.parquet",
        "telemetry_events.parquet",
        "coverage_samples.parquet",
    ]
    missing = [name for name in required if not (output_dir / name).is_file()]
    if missing:
        raise SystemExit(
            f"cannot analyse {output_dir}; missing required Parquet files: "
            + ", ".join(missing)
        )

    run_rows = pl.read_parquet(output_dir / "runs.parquet").to_dicts()
    reclassify_runs_from_raw_stderr(output_dir, run_rows)
    runs = dataframe_with_columns(pd, run_rows, RUN_COLUMNS)
    process = dataframe_with_columns(
        pd,
        pl.read_parquet(output_dir / "process_samples.parquet").to_dicts(),
        PROCESS_SAMPLE_COLUMNS,
    )
    telemetry_rows = pl.read_parquet(output_dir / "telemetry_events.parquet").to_dicts()
    reingest_checker_logs_from_raw(output_dir, runs, telemetry_rows)
    telemetry = dataframe_with_columns(
        pd,
        telemetry_rows,
        TELEMETRY_EVENT_COLUMNS,
    )
    coverage = dataframe_with_columns(
        pd,
        pl.read_parquet(output_dir / "coverage_samples.parquet").to_dicts(),
        COVERAGE_SAMPLE_COLUMNS,
    )
    write_output_frames(output_dir, runs, process, telemetry, coverage)
    robots = sorted(runs["robots"].dropna().unique().tolist()) if not runs.empty else []
    print(
        f"reanalysed {len(runs)} runs for robots={','.join(map(str, robots))}; "
        f"wrote benchmark outputs to {output_dir}",
        flush=True,
    )


def reclassify_runs_from_raw_stderr(output_dir: Path, run_rows: list[dict[str, Any]]) -> None:
    for row in run_rows:
        run_dir = Path(row.get("run_dir") or "")
        if not run_dir.is_absolute() and not run_dir.exists():
            run_dir = output_dir.parent / run_dir

        _events, malformed_telemetry_lines = read_telemetry_events(
            run_dir / "telemetry_events.jsonl"
        )
        record_malformed_telemetry(row, malformed_telemetry_lines)

        completed_by_telemetry = telemetry_has_finished(run_dir, row.get("run_id") or "")
        if completed_by_telemetry and row.get("status") in {"failed", "timeout", "error"}:
            row["status"] = "ok"
            append_run_error(row, "reclassified ok because telemetry completed")

        if row.get("status") not in {"ok", "failed"}:
            continue
        if stderr_contains_shutdown_error(read_text(run_dir / "simulator.stderr.log")):
            if completed_by_telemetry:
                append_run_error(
                    row,
                    "post-telemetry simulator stderr contains shutdown/system error",
                )
                continue
            row["status"] = "failed"
            append_run_error(row, "simulator stderr contains shutdown/system error")


def reingest_checker_logs_from_raw(
    output_dir: Path,
    runs: Any,
    telemetry_rows: list[dict[str, Any]],
) -> None:
    existing = {
        (row.get("run_id"), row.get("event_type"), row.get("payload_json"))
        for row in telemetry_rows
        if row.get("event_type")
        in {
            "scheduler_mape_phase",
            "constraint_monitoring",
            "sat_solver",
            "worker_monitoring_step",
            "worker_reconfiguration",
        }
    }
    for run in runs.to_dict("records"):
        run_id = run["run_id"]
        run_dir = Path(run["run_dir"])
        if not run_dir.is_absolute() and not run_dir.exists():
            run_dir = output_dir.parent / run_dir
        raw_telemetry = run_dir / "telemetry_events.jsonl"
        if not raw_telemetry.is_file():
            continue
        events, _malformed_lines = read_telemetry_events(raw_telemetry)
        for event in events:
            if event.get("event_type") != "benchmark_run_started":
                continue
            checker_dir = (event.get("payload") or {}).get("trustworthiness_checker_run_dir")
            if not checker_dir:
                continue
            before = len(telemetry_rows)
            ingest_checker_logs(
                Path(checker_dir),
                run_id,
                telemetry_rows,
                event.get("ts_unix_ms"),
            )
            if len(telemetry_rows) == before:
                continue
            deduped = []
            for row in telemetry_rows[before:]:
                key = (row.get("run_id"), row.get("event_type"), row.get("payload_json"))
                if key in existing:
                    continue
                existing.add(key)
                deduped.append(row)
            telemetry_rows[before:] = deduped


def write_output_frames(
    output_dir: Path,
    runs: Any,
    process: Any,
    telemetry: Any,
    coverage: Any,
) -> None:
    import matplotlib.pyplot as plt
    import pandas as pd

    configure_matplotlib()
    PROCESS_MEASURED_CACHE.clear()
    summaries = summarize_runs(runs, process, telemetry, coverage)
    checker_process_summaries = summarize_checker_processes(pd, runs, process)
    worker_reconfigurations = extract_worker_reconfigurations(pd, runs, telemetry)
    scheduler_mape_phases = extract_scheduler_mape_phases(pd, runs, telemetry)
    sat_solver_events = extract_sat_solver_events(pd, runs, telemetry)
    worker_monitoring_steps = extract_worker_monitoring_steps(pd, runs, telemetry)
    constraint_monitoring = extract_constraint_monitoring(pd, runs, telemetry)

    write_parquet_polars(runs, output_dir / "runs.parquet")
    write_parquet_polars(process, output_dir / "process_samples.parquet")
    write_parquet_polars(telemetry, output_dir / "telemetry_events.parquet")
    write_parquet_polars(coverage, output_dir / "coverage_samples.parquet")
    write_parquet_polars(summaries, output_dir / "run_summaries.parquet")
    write_parquet_polars(
        checker_process_summaries,
        output_dir / "checker_process_summaries.parquet",
    )
    write_parquet_polars(
        worker_reconfigurations,
        output_dir / "worker_reconfigurations.parquet",
    )
    write_parquet_polars(
        scheduler_mape_phases,
        output_dir / "scheduler_mape_phases.parquet",
    )
    write_parquet_polars(
        sat_solver_events,
        output_dir / "sat_solver_events.parquet",
    )
    write_parquet_polars(
        worker_monitoring_steps,
        output_dir / "worker_monitoring_steps.parquet",
    )
    write_parquet_polars(
        constraint_monitoring,
        output_dir / "constraint_monitoring.parquet",
    )

    plot_dir = output_dir / "plots"
    plot_dir.mkdir(exist_ok=True)
    for pattern in ["*.png", "*.pdf"]:
        for stale_plot in plot_dir.glob(pattern):
            stale_plot.unlink()
    if not process.empty:
        plot_checker_cpu_by_role(process, runs, plot_dir / "total_checker_cpu_by_role_by_robot_count.png")
        plot_total_checker_cpu_by_run(
            process,
            runs,
            plot_dir / "total_checker_cpu_by_robot_count.png",
        )
        plot_total_checker_cpu_per_second_by_run(
            process,
            runs,
            plot_dir / "total_checker_cpu_per_second_by_robot_count.png",
        )
        plot_scheduler_cpu_per_second(
            process,
            runs,
            plot_dir / "per_node_scheduler_cpu_per_second_by_robot_count.png",
        )
        plot_scheduler_cpu_user_system_per_second(
            process,
            runs,
            plot_dir / "per_node_scheduler_cpu_user_system_per_second_by_robot_count.png",
        )
        plot_checker_cpu_rate_timeseries(
            process,
            runs,
            "scheduler",
            plot_dir / "scheduler_cpu_rate_over_time.png",
        )
        plot_checker_cpu_rate_timeseries(
            process,
            runs,
            "worker",
            plot_dir / "worker_cpu_rate_over_time.png",
        )
        plot_per_node_checker_cpu(process, runs, plot_dir / "per_node_checker_cpu_by_robot_count.png")
        plot_per_node_checker_cpu_without_outliers(
            process,
            runs,
            plot_dir / "per_node_checker_cpu_without_outliers_by_robot_count.png",
        )
        plot_worker_cpu(process, runs, plot_dir / "per_node_worker_cpu_by_robot_count.png")
        plot_checker_memory_by_role(process, runs, plot_dir / "total_checker_memory_by_role_by_robot_count.png")
        plot_total_checker_memory_by_run(
            process,
            runs,
            plot_dir / "total_checker_memory_by_robot_count.png",
        )
        plot_per_node_checker_memory(process, runs, plot_dir / "per_node_checker_memory_by_robot_count.png")
        plot_worker_memory(process, runs, plot_dir / "per_node_worker_memory_by_robot_count.png")
        plot_ros_shared_memory(process, runs, plot_dir / "ros_shm_usage_by_robot_count.png")
    if not telemetry.empty:
        plot_scheduler_mape(telemetry, runs, plot_dir / "per_event_scheduler_mape_by_robot_count.png")
        plot_scheduler_mape_total(
            telemetry,
            runs,
            plot_dir / "scheduler_mape_total_by_robot_count.png",
        )
        plot_scheduler_mape_tail_latency(
            telemetry,
            runs,
            plot_dir / "scheduler_mape_phase_p95_by_robot_count.png",
        )
        plot_scheduler_iteration_tail_latency(
            telemetry,
            runs,
            plot_dir / "scheduler_iteration_latency_percentiles_by_robot_count.png",
        )
        plot_scheduler_phase_latency_timeseries(
            telemetry,
            runs,
            plot_dir / "scheduler_phase_latency_over_time.png",
        )
        plot_sat_solver_time_boxplot(
            telemetry,
            runs,
            plot_dir / "per_solve_sat_solver_time_by_robot_count.png",
        )
        plot_sat_solver_time_scatter(
            telemetry,
            runs,
            plot_dir / "per_solve_sat_solver_time_scatter_by_robot_count.png",
        )
        plot_sat_solver_total(
            telemetry,
            runs,
            plot_dir / "total_sat_solver_time_by_robot_count.png",
        )
        plot_sat_solver_normalized_cost(
            summaries,
            plot_dir / "sat_solver_normalized_cost_by_robot_count.png",
        )
        plot_reconfiguration_activity(
            telemetry,
            runs,
            plot_dir / "reconfiguration_activity_by_robot_count.png",
        )
        plot_reconfiguration_activity_timeseries(
            telemetry,
            runs,
            plot_dir / "reconfiguration_activity_over_time.png",
        )
        plot_time_to_reconfig(telemetry, runs, plot_dir / "time_to_first_reconfiguration.png")
        plot_reconfiguration_latency(
            summaries,
            plot_dir / "reconfiguration_latency_by_robot_count.png",
        )
        plot_worker_monitoring_cost(
            telemetry,
            runs,
            plot_dir / "per_node_worker_monitoring_cost_by_robot_count.png",
        )
        plot_worker_monitoring_total(
            telemetry,
            runs,
            plot_dir / "total_worker_monitoring_cost_by_robot_count.png",
        )
        plot_worker_monitoring_throughput(
            summaries,
            plot_dir / "worker_monitoring_throughput_by_robot_count.png",
        )
        plot_worker_monitoring_load_balance(
            summaries,
            plot_dir / "worker_monitoring_load_balance_by_robot_count.png",
        )
        plot_worker_reconfiguration_load_balance(
            summaries,
            plot_dir / "worker_reconfiguration_load_balance_by_robot_count.png",
        )
        plot_constraint_monitoring_cost(
            telemetry,
            runs,
            plot_dir / "per_event_constraint_monitoring_cost_by_robot_count.png",
        )
        plot_constraint_monitoring_total(
            telemetry,
            runs,
            plot_dir / "total_constraint_monitoring_cost_by_robot_count.png",
        )
    if not coverage.empty:
        plot_coverage(coverage, runs, plot_dir / "total_coverage_by_robot_count.png")
        plot_coverage(
            coverage,
            runs,
            plot_dir / "total_coverage_by_robot_count_ymin_0_8.png",
            y_min=0.8,
            title="Monitoring coverage by robot count (zoomed)",
        )
        plot_coverage_scatter_mean(
            coverage,
            runs,
            plot_dir / "total_coverage_by_robot_count_scatter.png",
        )
        plot_coverage_scatter_mean(
            coverage,
            runs,
            plot_dir / "total_coverage_by_robot_count_scatter_ymin_0_8.png",
            y_min=0.8,
            title="Monitoring coverage by robot count (scatter, zoomed)",
        )
        plot_coverage_trend_zoom(
            coverage,
            runs,
            plot_dir / "coverage_trend_zoom_by_robot_count.png",
        )
        plot_coverage_change_from_baseline(
            coverage,
            runs,
            plot_dir / "coverage_change_from_min_robot_by_robot_count.png",
        )
        plot_coverage_distribution(
            coverage,
            runs,
            plot_dir / "coverage_distribution_by_robot_count.png",
        )
        plot_coverage_distribution(
            coverage,
            runs,
            plot_dir / "coverage_distribution_by_robot_count_ymin_0_8.png",
            y_min=0.8,
            title="Coverage distribution across seeds (zoomed)",
        )
        plot_coverage_violin(
            coverage,
            runs,
            plot_dir / "coverage_violin_by_robot_count.png",
        )
        plot_coverage_violin(
            coverage,
            runs,
            plot_dir / "coverage_violin_by_robot_count_ymin_0_8.png",
            y_min=0.8,
            title="Coverage distribution across seeds (violin, zoomed)",
        )
        plot_coverage_run_scatter(
            coverage,
            runs,
            plot_dir / "coverage_runs_by_robot_count.png",
        )
        plot_property_coverage(
            coverage,
            runs,
            plot_dir / "per_property_coverage_by_robot_count.png",
        )
        plot_possible_property_ticks(
            coverage,
            runs,
            plot_dir / "possible_property_ticks_by_robot_count.png",
        )
        plot_coverage_vs_checker_cpu(
            coverage,
            runs,
            summaries,
            plot_dir / "total_coverage_vs_total_checker_cpu.png",
        )
    if not summaries.empty:
        plot_checker_cpu_per_second(summaries, plot_dir / "checker_cpu_per_second_by_robot_count.png")
        plot_scheduler_throughput(
            summaries,
            plot_dir / "scheduler_throughput_by_robot_count.png",
        )
        plot_scheduler_normalized_cost(
            summaries,
            plot_dir / "scheduler_normalized_cpu_cost_by_robot_count.png",
        )
        plot_pose_publish_backlog(
            summaries,
            plot_dir / "pose_publish_backlog_by_robot_count.png",
        )
    plot_failure_rate(runs, plot_dir / "checker_failure_timeout_rate.png")
    plt.close("all")


def dataframe_with_columns(pd: Any, rows: list[dict[str, Any]], columns: list[str]) -> Any:
    frame = pd.DataFrame(rows)
    for column in columns:
        if column not in frame.columns:
            frame[column] = None
    return frame[columns]


def write_parquet_polars(frame: Any, path: Path) -> None:
    import polars as pl

    pl.from_pandas(frame.reset_index(drop=True)).write_parquet(path)


def pandas_from_polars(frame: Any) -> Any:
    return frame.to_pandas() if hasattr(frame, "to_pandas") else frame


def run_window_maps(runs: Any) -> tuple[dict[str, float], dict[str, float]]:
    warmups = {}
    ends = {}
    if runs.empty:
        return warmups, ends
    for _, run in runs.iterrows():
        run_id = run["run_id"]
        warmup = float(run["warmup_secs"] or 0.0)
        duration = float(run["duration_secs"] or 0.0)
        warmups[run_id] = warmup
        ends[run_id] = warmup + duration
    return warmups, ends


def measured_rows(frame: Any, runs: Any, keep_unknown_elapsed: bool = False) -> Any:
    if frame.empty or "elapsed_secs" not in frame:
        return frame
    import polars as pl

    run_windows = runs[["run_id", "warmup_secs", "duration_secs"]].copy()
    if run_windows.empty:
        return frame
    run_windows["warmup_secs"] = run_windows["warmup_secs"].fillna(0.0).astype(float)
    run_windows["end_secs"] = run_windows["warmup_secs"] + run_windows["duration_secs"].fillna(0.0).astype(float)
    pl_frame = pl.from_pandas(frame.reset_index(drop=True))
    pl_windows = pl.from_pandas(run_windows[["run_id", "warmup_secs", "end_secs"]].reset_index(drop=True))
    filtered = pl_frame.join(pl_windows, on="run_id", how="left")
    in_window = (
        pl.col("elapsed_secs").is_not_null()
        & (pl.col("elapsed_secs") >= pl.col("warmup_secs").fill_null(0.0))
        & (pl.col("elapsed_secs") <= pl.col("end_secs").fill_null(float("inf")))
    )
    if keep_unknown_elapsed:
        in_window = in_window | pl.col("elapsed_secs").is_null()
    filtered = filtered.filter(in_window).drop(["warmup_secs", "end_secs"])
    return filtered.to_pandas()


def measured_process_samples(process: Any, runs: Any) -> Any:
    if process.empty:
        return process
    import polars as pl

    cache_key = (id(process), id(runs))
    cached = PROCESS_MEASURED_CACHE.get(cache_key)
    if cached is not None:
        return cached.copy()

    run_windows = runs[["run_id", "warmup_secs", "duration_secs"]].copy()
    run_windows["warmup_secs"] = run_windows["warmup_secs"].fillna(0.0).astype(float)
    run_windows["end_secs"] = run_windows["warmup_secs"] + run_windows["duration_secs"].fillna(0.0).astype(float)
    pl_process = pl.from_pandas(process.reset_index(drop=True))
    pl_windows = pl.from_pandas(run_windows[["run_id", "warmup_secs", "end_secs"]].reset_index(drop=True))
    measured = (
        pl_process.join(pl_windows, on="run_id", how="left")
        .filter(
            pl.col("elapsed_secs").is_not_null()
            & (pl.col("elapsed_secs") >= pl.col("warmup_secs").fill_null(0.0))
            & (pl.col("elapsed_secs") <= pl.col("end_secs").fill_null(float("inf")))
        )
        .sort(["run_id", "pid", "elapsed_secs"])
    )
    if measured.is_empty():
        result = process.iloc[0:0].copy()
        PROCESS_MEASURED_CACHE[cache_key] = result
        return result.copy()
    last_value_columns = [
        column
        for column in PROCESS_SAMPLE_COLUMNS
        if column in measured.columns and column not in {"run_id", "pid"}
    ]
    grouped = measured.group_by(["run_id", "pid"], maintain_order=True).agg(
        [
            *[pl.col(column).last().alias(column) for column in last_value_columns],
            pl.col("cpu_time_secs").first().alias("baseline_cpu_time_secs"),
            pl.col("user_cpu_time_secs").first().alias("baseline_user_cpu_time_secs"),
            pl.col("system_cpu_time_secs").first().alias("baseline_system_cpu_time_secs"),
            pl.col("rss_bytes").max().alias("max_rss_bytes"),
            pl.col("threads").max().alias("max_threads"),
        ]
    )
    result = grouped.with_columns(
        [
            (pl.col("cpu_time_secs") - pl.col("baseline_cpu_time_secs")).clip(0.0, None).alias("cpu_time_secs"),
            (pl.col("user_cpu_time_secs") - pl.col("baseline_user_cpu_time_secs")).clip(0.0, None).alias("user_cpu_time_secs"),
            (pl.col("system_cpu_time_secs") - pl.col("baseline_system_cpu_time_secs")).clip(0.0, None).alias("system_cpu_time_secs"),
            pl.col("max_rss_bytes").alias("rss_bytes"),
            pl.col("max_threads").alias("threads"),
        ]
    ).drop(
        [
            "baseline_cpu_time_secs",
            "baseline_user_cpu_time_secs",
            "baseline_system_cpu_time_secs",
            "max_rss_bytes",
            "max_threads",
        ]
    )
    result = result.select([column for column in PROCESS_SAMPLE_COLUMNS if column in result.columns]).to_pandas()
    PROCESS_MEASURED_CACHE[cache_key] = result
    return result.copy()


def summarize_checker_processes(pd: Any, runs: Any, process: Any) -> Any:
    if process.empty:
        return dataframe_with_columns(pd, [], CHECKER_PROCESS_SUMMARY_COLUMNS)
    final = checker_processes(measured_process_samples(process, runs))
    if final.empty:
        return dataframe_with_columns(pd, [], CHECKER_PROCESS_SUMMARY_COLUMNS)
    run_info = runs[["run_id", "robots", "seed", "duration_secs"]]
    final = final.merge(run_info, on=["run_id", "robots", "seed"], how="left")
    final = final.copy()
    final["cpu_time_per_measured_sec"] = final["cpu_time_secs"] / final["duration_secs"]
    final["user_cpu_time_per_measured_sec"] = (
        final["user_cpu_time_secs"] / final["duration_secs"]
    )
    final["system_cpu_time_per_measured_sec"] = (
        final["system_cpu_time_secs"] / final["duration_secs"]
    )
    final["rss_mib"] = final["rss_bytes"] / (1024 * 1024)
    return dataframe_with_columns(
        pd,
        final.to_dict("records"),
        CHECKER_PROCESS_SUMMARY_COLUMNS,
    )


def extract_worker_reconfigurations(pd: Any, runs: Any, telemetry: Any) -> Any:
    if telemetry.empty:
        return dataframe_with_columns(pd, [], WORKER_RECONFIGURATION_COLUMNS)
    telemetry = measured_rows(telemetry, runs, keep_unknown_elapsed=False)
    run_info = runs.set_index("run_id")[["robots", "seed"]].to_dict("index")
    rows = []
    for _, event in telemetry[telemetry["event_type"] == "worker_reconfiguration"].iterrows():
        payload = json.loads(event["payload_json"])
        run_id = event["run_id"]
        rows.append(
            {
                "run_id": run_id,
                "robots": run_info.get(run_id, {}).get("robots"),
                "seed": run_info.get(run_id, {}).get("seed"),
                "elapsed_secs": event.get("elapsed_secs"),
                "worker": payload.get("worker"),
                "input_var_count": payload.get("input_var_count"),
                "output_var_count": payload.get("output_var_count"),
                "active_tasks": payload.get("active_tasks"),
                "global_tasks": payload.get("global_tasks"),
                "sleepers": payload.get("sleepers"),
                "input_vars_json": json.dumps(payload.get("input_vars", []), sort_keys=True),
                "output_vars_json": json.dumps(payload.get("output_vars", []), sort_keys=True),
                "source": payload.get("source"),
            }
        )
    return dataframe_with_columns(pd, rows, WORKER_RECONFIGURATION_COLUMNS)


def extract_scheduler_mape_phases(pd: Any, runs: Any, telemetry: Any) -> Any:
    if telemetry.empty:
        return dataframe_with_columns(pd, [], SCHEDULER_MAPE_PHASE_COLUMNS)
    telemetry = measured_rows(telemetry, runs, keep_unknown_elapsed=False)
    run_info = runs.set_index("run_id")[["robots", "seed"]].to_dict("index")
    rows = []
    for _, event in telemetry[telemetry["event_type"] == "scheduler_mape_phase"].iterrows():
        payload = json.loads(event["payload_json"])
        run_id = event["run_id"]
        rows.append(
            {
                "run_id": run_id,
                "robots": run_info.get(run_id, {}).get("robots"),
                "seed": run_info.get(run_id, {}).get("seed"),
                "elapsed_secs": event.get("elapsed_secs"),
                "role": event["role"],
                "phase": normalize_mape_phase(payload.get("phase")),
                "tick": payload.get("tick"),
                "duration_ms": payload.get("duration_ms"),
                "constraints_hold": payload.get("constraints_hold"),
                "should_plan": payload.get("should_plan"),
                "should_execute": payload.get("should_execute"),
                "plan_succeeded": payload.get("plan_succeeded"),
                "source": payload.get("source"),
            }
        )
    return dataframe_with_columns(pd, rows, SCHEDULER_MAPE_PHASE_COLUMNS)


def extract_sat_solver_events(pd: Any, runs: Any, telemetry: Any) -> Any:
    if telemetry.empty:
        return dataframe_with_columns(pd, [], SAT_SOLVER_EVENT_COLUMNS)
    telemetry = measured_rows(telemetry, runs, keep_unknown_elapsed=False)
    run_info = runs.set_index("run_id")[["robots", "seed"]].to_dict("index")
    rows = []
    for _, event in telemetry[telemetry["event_type"] == "sat_solver"].iterrows():
        payload = json.loads(event["payload_json"])
        run_id = event["run_id"]
        rows.append(
            {
                "run_id": run_id,
                "robots": run_info.get(run_id, {}).get("robots"),
                "seed": run_info.get(run_id, {}).get("seed"),
                "elapsed_secs": event.get("elapsed_secs"),
                "role": event["role"],
                "phase": normalize_mape_phase(payload.get("phase")),
                "result": payload.get("result"),
                "fast_path": payload.get("fast_path"),
                "forced_sat": payload.get("forced_sat"),
                "duration_ms": payload.get("duration_ms"),
                "total_duration_ms": payload.get("total_duration_ms"),
                "nodes": payload.get("nodes"),
                "edges": payload.get("edges"),
                "constraints": payload.get("constraints"),
                "outputs": payload.get("outputs"),
                "assigned_streams": payload.get("assigned_streams"),
                "clauses": payload.get("clauses"),
                "vars": payload.get("vars"),
                "atoms": payload.get("atoms"),
                "bound_values": payload.get("bound_values"),
                "source": payload.get("source"),
            }
        )
    return dataframe_with_columns(pd, rows, SAT_SOLVER_EVENT_COLUMNS)


def extract_worker_monitoring_steps(pd: Any, runs: Any, telemetry: Any) -> Any:
    if telemetry.empty:
        return dataframe_with_columns(pd, [], WORKER_MONITORING_STEP_COLUMNS)
    telemetry = measured_rows(telemetry, runs, keep_unknown_elapsed=False)
    run_info = runs.set_index("run_id")[["robots", "seed"]].to_dict("index")
    rows = []
    for _, event in telemetry[telemetry["event_type"] == "worker_monitoring_step"].iterrows():
        payload = json.loads(event["payload_json"])
        run_id = event["run_id"]
        rows.append(
            {
                "run_id": run_id,
                "robots": run_info.get(run_id, {}).get("robots"),
                "seed": run_info.get(run_id, {}).get("seed"),
                "elapsed_secs": event.get("elapsed_secs"),
                "role": event["role"],
                "worker": payload.get("worker"),
                "context_id": payload.get("context_id"),
                "expr_evaluator_count": payload.get("expr_evaluator_count"),
                "non_aux_expr_evaluator_count": payload.get("non_aux_expr_evaluator_count"),
                "aux_var_count": payload.get("aux_var_count"),
                "forward_state": payload.get("forward_state"),
                "eval_state": payload.get("eval_state"),
                "forward_values_duration_ms": payload.get("forward_values_duration_ms"),
                "eval_expr_duration_ms": payload.get("eval_expr_duration_ms"),
                "duration_ms": payload.get("duration_ms"),
                "source": payload.get("source"),
            }
        )
    return dataframe_with_columns(pd, rows, WORKER_MONITORING_STEP_COLUMNS)


def extract_constraint_monitoring(pd: Any, runs: Any, telemetry: Any) -> Any:
    if telemetry.empty:
        return dataframe_with_columns(pd, [], CONSTRAINT_MONITORING_COLUMNS)
    telemetry = measured_rows(telemetry, runs, keep_unknown_elapsed=False)
    run_info = runs.set_index("run_id")[["robots", "seed"]].to_dict("index")
    rows = []
    for _, event in telemetry[telemetry["event_type"] == "constraint_monitoring"].iterrows():
        payload = json.loads(event["payload_json"])
        run_id = event["run_id"]
        rows.append(
            {
                "run_id": run_id,
                "robots": run_info.get(run_id, {}).get("robots"),
                "seed": run_info.get(run_id, {}).get("seed"),
                "elapsed_secs": event.get("elapsed_secs"),
                "role": event["role"],
                "stream_count": payload.get("stream_count"),
                "values_received": payload.get("values_received"),
                "constraints_hold": payload.get("constraints_hold"),
                "duration_ms": payload.get("duration_ms"),
                "source": payload.get("source"),
            }
        )
    return dataframe_with_columns(pd, rows, CONSTRAINT_MONITORING_COLUMNS)


def summarize_runs(runs: Any, process: Any, telemetry: Any, coverage: Any) -> Any:
    import pandas as pd

    rows = []
    for _, run in runs.iterrows():
        run_id = run["run_id"]
        proc = process[process["run_id"] == run_id] if not process.empty else pd.DataFrame()
        tel = telemetry[telemetry["run_id"] == run_id] if not telemetry.empty else pd.DataFrame()
        cov = coverage[coverage["run_id"] == run_id] if not coverage.empty else pd.DataFrame()
        tel = measured_rows(tel, runs, keep_unknown_elapsed=False)
        cov = measured_rows(cov, runs, keep_unknown_elapsed=False)
        coverage_values = cov["coverage"].dropna() if not cov.empty else pd.Series(dtype="float64")
        final_proc = measured_process_samples(proc, runs)
        checker_proc = checker_processes(final_proc)
        scheduler_proc = final_proc[final_proc["role"] == "scheduler"] if not final_proc.empty else pd.DataFrame()
        worker_proc = final_proc[final_proc["role"] == "worker"] if not final_proc.empty else pd.DataFrame()
        worker_cpu = worker_proc["cpu_time_secs"] if not worker_proc.empty else pd.Series(dtype="float64")
        checker_cpu = checker_proc["cpu_time_secs"].sum() if not checker_proc.empty else None
        worker_reconfigs = telemetry_payload_count(tel, "worker_reconfiguration")
        reconfig_messages = max_sim_tick_payload_value(tel, "reconfig_messages_received")
        mape = mape_phase_dataframe(pd, tel)
        monitoring = worker_monitoring_step_dataframe(pd, tel)
        monitoring_eval_duration = (
            monitoring["eval_expr_duration_ms"].dropna()
            if not monitoring.empty
            else pd.Series(dtype="float64")
        )
        monitoring_step_duration = (
            monitoring["duration_ms"].dropna()
            if not monitoring.empty
            else pd.Series(dtype="float64")
        )
        constraint_monitoring = constraint_monitoring_dataframe(pd, tel)
        constraint_monitoring_duration = (
            constraint_monitoring["duration_ms"].dropna()
            if not constraint_monitoring.empty
            else pd.Series(dtype="float64")
        )
        sat = sat_solver_payload_dataframe(pd, tel)
        sat_solve = sat[sat["phase"] == "sat_solve"] if not sat.empty else pd.DataFrame()
        sat_fast_path = (
            sat[(sat["phase"] == "guarded_fast_path") & (sat["result"] == "sat")]
            if not sat.empty
            else pd.DataFrame()
        )
        sat_terminal = sat_terminal_solver_dataframe(pd, sat)
        sat_solve_duration = (
            sat_solve["duration_ms"].dropna() if not sat_solve.empty else pd.Series(dtype="float64")
        )
        sat_terminal_duration = (
            sat_terminal["solver_duration_ms"].dropna()
            if not sat_terminal.empty
            else pd.Series(dtype="float64")
        )
        sat_total_duration = (
            sat["total_duration_ms"].dropna() if not sat.empty else pd.Series(dtype="float64")
        )
        duration = float(run["duration_secs"]) if run["duration_secs"] else None
        robot_count = int(run["robots"]) if run["robots"] else 0
        scheduler_cpu = scheduler_proc["cpu_time_secs"].sum() if not scheduler_proc.empty else None
        mape_iterations = len(mape[mape["phase"] == "iteration_total"]) if not mape.empty else 0
        plan_attempts = bool_column_count(mape, "should_plan")
        successful_plans = bool_column_count(mape, "plan_succeeded")
        execute_events = bool_column_count(mape, "should_execute")
        worker_expr_evaluators = numeric_sum(monitoring, "expr_evaluator_count")
        worker_non_aux_expr_evaluators = numeric_sum(monitoring, "non_aux_expr_evaluator_count")
        worker_step_counts = pad_worker_series(
            monitoring.groupby("worker").size()
            if not monitoring.empty and "worker" in monitoring
            else pd.Series(dtype="float64"),
            robot_count,
        )
        worker_duration_by_worker = pad_worker_series(
            monitoring.groupby("worker")["duration_ms"].sum().dropna()
            if not monitoring.empty and "worker" in monitoring and "duration_ms" in monitoring
            else pd.Series(dtype="float64"),
            robot_count,
        )
        worker_reconfigs_by_worker = pad_worker_series(worker_reconfig_counts(pd, tel), robot_count)
        terminal_cost = sat_terminal.copy() if not sat_terminal.empty else pd.DataFrame()
        reconfiguration_latency = reconfiguration_latency_series(pd, tel)
        pose_publish_failures = max_sim_tick_payload_value(tel, "pose_publish_failures")
        pose_publish_attempts = max_sim_tick_payload_value(tel, "pose_publish_attempts")
        rows.append(
            {
                "run_id": run_id,
                "robots": run["robots"],
                "seed": run["seed"],
                "status": run["status"],
                "checker_cpu_time_secs": checker_cpu,
                "checker_cpu_time_per_measured_sec": (
                    checker_cpu / duration if checker_cpu is not None and duration else None
                ),
                "scheduler_cpu_time_secs": (
                    scheduler_proc["cpu_time_secs"].sum() if not scheduler_proc.empty else None
                ),
                "worker_cpu_time_secs": worker_cpu.sum() if not worker_cpu.empty else None,
                "worker_cpu_time_mean_secs": worker_cpu.mean() if not worker_cpu.empty else None,
                "worker_cpu_time_p95_secs": worker_cpu.quantile(0.95) if not worker_cpu.empty else None,
                "worker_cpu_imbalance_ratio": (
                    worker_cpu.max() / worker_cpu.mean()
                    if not worker_cpu.empty and worker_cpu.mean() > 0.0
                    else None
                ),
                "checker_max_rss_bytes": (
                    checker_proc["rss_bytes"].max() if not checker_proc.empty else None
                ),
                "scheduler_max_rss_bytes": (
                    scheduler_proc["rss_bytes"].max() if not scheduler_proc.empty else None
                ),
                "worker_max_rss_bytes": worker_proc["rss_bytes"].max() if not worker_proc.empty else None,
                "checker_max_threads": (
                    checker_proc["threads"].max() if not checker_proc.empty else None
                ),
                "reconfig_messages_received": reconfig_messages,
                "worker_reconfiguration_events": worker_reconfigs,
                "worker_reconfiguration_events_per_sec": (
                    worker_reconfigs / duration if duration else None
                ),
                "mape_phase_events": len(mape),
                "scheduler_iterations_per_sec": safe_div(mape_iterations, duration),
                "scheduler_plan_attempts_per_sec": safe_div(plan_attempts, duration),
                "scheduler_successful_plans_per_sec": safe_div(successful_plans, duration),
                "scheduler_execute_events_per_sec": safe_div(execute_events, duration),
                "mape_plan_mean_ms": mape_phase_mean(mape, "plan"),
                "mape_plan_p95_ms": mape_phase_quantile(mape, "plan", 0.95),
                "mape_plan_p99_ms": mape_phase_quantile(mape, "plan", 0.99),
                "mape_execute_mean_ms": mape_phase_mean(mape, "execute"),
                "mape_execute_p95_ms": mape_phase_quantile(mape, "execute", 0.95),
                "mape_execute_p99_ms": mape_phase_quantile(mape, "execute", 0.99),
                "mape_iteration_total_mean_ms": mape_phase_mean(mape, "iteration_total"),
                "mape_iteration_total_p50_ms": mape_phase_quantile(mape, "iteration_total", 0.50),
                "mape_iteration_total_p95_ms": mape_phase_quantile(mape, "iteration_total", 0.95),
                "mape_iteration_total_p99_ms": mape_phase_quantile(mape, "iteration_total", 0.99),
                "scheduler_cpu_per_iteration": safe_div(scheduler_cpu, mape_iterations),
                "scheduler_cpu_per_plan_attempt": safe_div(scheduler_cpu, plan_attempts),
                "scheduler_cpu_per_successful_plan": safe_div(scheduler_cpu, successful_plans),
                "worker_monitoring_step_events": len(monitoring),
                "worker_monitoring_steps_per_sec": safe_div(len(monitoring), duration),
                "worker_expr_evaluators_per_sec": safe_div(worker_expr_evaluators, duration),
                "worker_non_aux_expr_evaluators_per_sec": safe_div(
                    worker_non_aux_expr_evaluators,
                    duration,
                ),
                "worker_eval_ms_per_expr": safe_div(
                    monitoring_eval_duration.sum() if not monitoring_eval_duration.empty else None,
                    worker_expr_evaluators,
                ),
                "worker_step_count_imbalance_ratio": max_mean_ratio(worker_step_counts),
                "worker_monitoring_duration_imbalance_ratio": max_mean_ratio(worker_duration_by_worker),
                "worker_reconfiguration_imbalance_ratio": max_mean_ratio(worker_reconfigs_by_worker),
                "worker_monitor_eval_mean_ms": (
                    monitoring_eval_duration.mean()
                    if not monitoring_eval_duration.empty
                    else None
                ),
                "worker_monitor_eval_p95_ms": (
                    monitoring_eval_duration.quantile(0.95)
                    if not monitoring_eval_duration.empty
                    else None
                ),
                "worker_monitor_eval_p99_ms": (
                    monitoring_eval_duration.quantile(0.99)
                    if not monitoring_eval_duration.empty
                    else None
                ),
                "worker_monitor_step_mean_ms": (
                    monitoring_step_duration.mean()
                    if not monitoring_step_duration.empty
                    else None
                ),
                "worker_monitor_step_p95_ms": (
                    monitoring_step_duration.quantile(0.95)
                    if not monitoring_step_duration.empty
                    else None
                ),
                "worker_monitor_step_p99_ms": (
                    monitoring_step_duration.quantile(0.99)
                    if not monitoring_step_duration.empty
                    else None
                ),
                "constraint_monitoring_events": len(constraint_monitoring),
                "constraint_monitoring_mean_ms": (
                    constraint_monitoring_duration.mean()
                    if not constraint_monitoring_duration.empty
                    else None
                ),
                "constraint_monitoring_p95_ms": (
                    constraint_monitoring_duration.quantile(0.95)
                    if not constraint_monitoring_duration.empty
                    else None
                ),
                "sat_solver_events": len(sat),
                "sat_solve_events": len(sat_solve),
                "sat_fast_path_events": len(sat_fast_path),
                "sat_solve_mean_ms": (
                    sat_solve_duration.mean() if not sat_solve_duration.empty else None
                ),
                "sat_solve_p95_ms": (
                    sat_solve_duration.quantile(0.95) if not sat_solve_duration.empty else None
                ),
                "sat_solve_max_ms": (
                    sat_solve_duration.max() if not sat_solve_duration.empty else None
                ),
                "sat_solver_ms_per_clause": normalized_solver_cost(terminal_cost, "clauses"),
                "sat_solver_ms_per_var": normalized_solver_cost(terminal_cost, "vars"),
                "sat_solver_ms_per_constraint": normalized_solver_cost(terminal_cost, "constraints"),
                "sat_solver_ms_per_assigned_stream": normalized_solver_cost(
                    terminal_cost,
                    "assigned_streams",
                ),
                "sat_terminal_mean_ms": (
                    sat_terminal_duration.mean() if not sat_terminal_duration.empty else None
                ),
                "sat_terminal_p95_ms": (
                    sat_terminal_duration.quantile(0.95)
                    if not sat_terminal_duration.empty
                    else None
                ),
                "sat_total_mean_ms": (
                    sat_total_duration.mean() if not sat_total_duration.empty else None
                ),
                "sat_cnf_clauses_max": sat["clauses"].max() if not sat.empty else None,
                "sat_cnf_vars_max": sat["vars"].max() if not sat.empty else None,
                "pose_publish_failure_rate": safe_div(pose_publish_failures, pose_publish_attempts),
                "pose_publish_failures_per_sec": safe_div(pose_publish_failures, duration),
                "reconfiguration_latency_p50_ms": series_quantile(reconfiguration_latency, 0.50),
                "reconfiguration_latency_p95_ms": series_quantile(reconfiguration_latency, 0.95),
                "reconfiguration_latency_p99_ms": series_quantile(reconfiguration_latency, 0.99),
                "coverage_mean": coverage_values.mean() if not coverage_values.empty else None,
                "coverage_p05": (
                    coverage_values.quantile(0.05) if not coverage_values.empty else None
                ),
                "coverage_p50": (
                    coverage_values.quantile(0.50) if not coverage_values.empty else None
                ),
                "coverage_p95": (
                    coverage_values.quantile(0.95) if not coverage_values.empty else None
                ),
                "coverage_min": coverage_values.min() if not coverage_values.empty else None,
                "telemetry_events": len(tel),
                "first_reconfig_elapsed_secs": first_reconfig_time(tel),
            }
        )
    return dataframe_with_columns(pd, rows, RUN_SUMMARY_COLUMNS)


def mape_phase_dataframe(pd: Any, telemetry: Any) -> Any:
    rows = []
    if telemetry.empty:
        return pd.DataFrame(rows)
    for _, row in telemetry[telemetry["event_type"] == "scheduler_mape_phase"].iterrows():
        payload = json.loads(row["payload_json"])
        rows.append(
            {
                "run_id": row["run_id"],
                "elapsed_secs": row.get("elapsed_secs"),
                "phase": normalize_mape_phase(payload.get("phase")),
                "duration_ms": payload.get("duration_ms"),
                "tick": payload.get("tick"),
                "constraints_hold": payload.get("constraints_hold"),
                "should_plan": payload.get("should_plan"),
                "should_execute": payload.get("should_execute"),
                "plan_succeeded": payload.get("plan_succeeded"),
            }
        )
    return pd.DataFrame(rows)


def worker_monitoring_step_dataframe(pd: Any, telemetry: Any) -> Any:
    rows = []
    if telemetry.empty:
        return pd.DataFrame(rows)
    for _, row in telemetry[telemetry["event_type"] == "worker_monitoring_step"].iterrows():
        payload = json.loads(row["payload_json"])
        rows.append(
            {
                "run_id": row["run_id"],
                "elapsed_secs": row.get("elapsed_secs"),
                "worker": payload.get("worker"),
                "context_id": payload.get("context_id"),
                "expr_evaluator_count": payload.get("expr_evaluator_count"),
                "non_aux_expr_evaluator_count": payload.get("non_aux_expr_evaluator_count"),
                "aux_var_count": payload.get("aux_var_count"),
                "forward_state": payload.get("forward_state"),
                "eval_state": payload.get("eval_state"),
                "forward_values_duration_ms": payload.get("forward_values_duration_ms"),
                "eval_expr_duration_ms": payload.get("eval_expr_duration_ms"),
                "duration_ms": payload.get("duration_ms"),
            }
        )
    return pd.DataFrame(rows)


def constraint_monitoring_dataframe(pd: Any, telemetry: Any) -> Any:
    rows = []
    if telemetry.empty:
        return pd.DataFrame(rows)
    for _, row in telemetry[telemetry["event_type"] == "constraint_monitoring"].iterrows():
        payload = json.loads(row["payload_json"])
        rows.append(
            {
                "run_id": row["run_id"],
                "elapsed_secs": row.get("elapsed_secs"),
                "stream_count": payload.get("stream_count"),
                "values_received": payload.get("values_received"),
                "constraints_hold": payload.get("constraints_hold"),
                "duration_ms": payload.get("duration_ms"),
            }
        )
    return pd.DataFrame(rows)


def sat_solver_payload_dataframe(pd: Any, telemetry: Any) -> Any:
    rows = []
    if telemetry.empty:
        return pd.DataFrame(rows)
    for _, row in telemetry[telemetry["event_type"] == "sat_solver"].iterrows():
        payload = json.loads(row["payload_json"])
        rows.append(
            {
                "run_id": row["run_id"],
                "elapsed_secs": row.get("elapsed_secs"),
                "phase": payload.get("phase"),
                "result": payload.get("result"),
                "fast_path": payload.get("fast_path"),
                "forced_sat": payload.get("forced_sat"),
                "duration_ms": payload.get("duration_ms"),
                "total_duration_ms": payload.get("total_duration_ms"),
                "nodes": payload.get("nodes"),
                "edges": payload.get("edges"),
                "constraints": payload.get("constraints"),
                "outputs": payload.get("outputs"),
                "assigned_streams": payload.get("assigned_streams"),
                "clauses": payload.get("clauses"),
                "vars": payload.get("vars"),
                "atoms": payload.get("atoms"),
                "bound_values": payload.get("bound_values"),
            }
        )
    return pd.DataFrame(rows)


def sat_terminal_solver_dataframe(pd: Any, sat: Any) -> Any:
    if sat.empty:
        return pd.DataFrame()
    terminal = sat[
        (sat["phase"] == "sat_solve")
        | ((sat["phase"] == "guarded_fast_path") & (sat["result"] == "sat"))
    ].copy()
    if terminal.empty:
        return terminal
    terminal["solver_mode"] = terminal["phase"].map(
        {
            "sat_solve": "sat_solve",
            "guarded_fast_path": "guarded_fast_path",
        }
    )
    terminal["solver_duration_ms"] = terminal["total_duration_ms"].where(
        terminal["total_duration_ms"].notna(),
        terminal["duration_ms"],
    )
    return terminal


def mape_phase_mean(mape: Any, phase: str) -> float | None:
    if mape.empty:
        return None
    values = mape[mape["phase"] == phase]["duration_ms"].dropna()
    return values.mean() if not values.empty else None


def mape_phase_quantile(mape: Any, phase: str, quantile: float) -> float | None:
    if mape.empty:
        return None
    values = mape[mape["phase"] == phase]["duration_ms"].dropna()
    return values.quantile(quantile) if not values.empty else None


def series_quantile(values: Any, quantile: float) -> float | None:
    if values is None or values.empty:
        return None
    values = values.dropna()
    return values.quantile(quantile) if not values.empty else None


def safe_div(numerator: Any, denominator: Any) -> float | None:
    if numerator is None or denominator is None:
        return None
    try:
        numerator = float(numerator)
        denominator = float(denominator)
    except (TypeError, ValueError):
        return None
    if denominator <= 0.0:
        return None
    return numerator / denominator


def numeric_sum(frame: Any, column: str) -> float | None:
    if frame.empty or column not in frame:
        return None
    values = frame[column].dropna()
    return values.sum() if not values.empty else None


def bool_column_count(frame: Any, column: str) -> int:
    if frame.empty or column not in frame:
        return 0
    return int((frame[column] == True).sum())


def max_mean_ratio(values: Any) -> float | None:
    if values is None or values.empty:
        return None
    values = values.dropna()
    if values.empty:
        return None
    mean = values.mean()
    if mean <= 0.0:
        return None
    return values.max() / mean


def pad_worker_series(values: Any, robot_count: int) -> Any:
    if robot_count <= 0:
        return values
    padded = values.copy()
    for worker_index in range(1, robot_count + 1):
        worker = f"R{worker_index}"
        if worker not in padded.index:
            padded.loc[worker] = 0.0
    return padded


def normalized_solver_cost(sat_terminal: Any, denominator_column: str) -> float | None:
    if sat_terminal.empty or denominator_column not in sat_terminal:
        return None
    frame = sat_terminal.dropna(subset=["solver_duration_ms", denominator_column])
    if frame.empty:
        return None
    denominator = frame[denominator_column].sum()
    if denominator <= 0:
        return None
    return frame["solver_duration_ms"].sum() / denominator


def worker_reconfig_counts(pd: Any, telemetry: Any) -> Any:
    if telemetry.empty:
        return pd.Series(dtype="float64")
    rows = []
    for _, row in telemetry[telemetry["event_type"] == "worker_reconfiguration"].iterrows():
        payload = json.loads(row["payload_json"])
        rows.append(payload.get("worker"))
    if not rows:
        return pd.Series(dtype="float64")
    return pd.Series(rows).value_counts()


def reconfiguration_latency_series(pd: Any, telemetry: Any) -> Any:
    if telemetry.empty or "elapsed_secs" not in telemetry:
        return pd.Series(dtype="float64")
    scheduler = mape_phase_dataframe(pd, telemetry)
    if scheduler.empty:
        return pd.Series(dtype="float64")
    scheduler = scheduler[
        (scheduler["phase"] == "execute")
        & (scheduler["should_execute"] == True)
        & scheduler["elapsed_secs"].notna()
    ].sort_values("elapsed_secs")
    if scheduler.empty:
        return pd.Series(dtype="float64")
    worker = telemetry[
        (telemetry["event_type"] == "worker_reconfiguration")
        & telemetry["elapsed_secs"].notna()
    ].copy()
    if worker.empty:
        return pd.Series(dtype="float64")
    latencies = []
    scheduler_elapsed = scheduler["elapsed_secs"].astype(float)
    for _, row in worker.sort_values("elapsed_secs").iterrows():
        elapsed = float(row["elapsed_secs"])
        previous = scheduler_elapsed[scheduler_elapsed <= elapsed]
        if previous.empty:
            continue
        latencies.append((elapsed - float(previous.iloc[-1])) * 1000.0)
    return pd.Series(latencies, dtype="float64")


def final_process_samples(process: Any) -> Any:
    if process.empty:
        return process
    return process.sort_values("elapsed_secs").groupby(["run_id", "pid"], as_index=False).tail(1)


def checker_processes(process: Any) -> Any:
    if process.empty:
        return process
    return process[process["role"].isin(["scheduler", "worker", "trustworthiness_checker"])]


def telemetry_payload_count(telemetry: Any, event_type: str) -> int:
    if telemetry.empty:
        return 0
    return int((telemetry["event_type"] == event_type).sum())


def max_sim_tick_payload_value(telemetry: Any, key: str) -> int | None:
    if telemetry.empty:
        return None
    values = []
    for _, row in telemetry[telemetry["event_type"] == "sim_tick"].iterrows():
        payload = json.loads(row["payload_json"])
        if key in payload:
            values.append(payload[key])
    return max(values) if values else None


def first_reconfig_time(telemetry: Any) -> float | None:
    if telemetry.empty:
        return None
    rows = telemetry[telemetry["event_type"] == "sim_tick"]
    for _, row in rows.sort_values("elapsed_secs").iterrows():
        payload = json.loads(row["payload_json"])
        if payload.get("reconfig_messages_received", 0) > 0:
            return row["elapsed_secs"]
    return None


def robot_plot_width(frame: Any, minimum: float = 8.0) -> float:
    if frame.empty or "robots" not in frame:
        return minimum
    return max(minimum, float(frame["robots"].nunique()) * 0.7)


def configure_matplotlib() -> None:
    import matplotlib.pyplot as plt

    plt.rcParams.update(
        {
            "font.size": PLOT_FONT_SIZE,
            "axes.labelsize": PLOT_LABEL_SIZE,
            "xtick.labelsize": PLOT_TICK_SIZE,
            "ytick.labelsize": PLOT_TICK_SIZE,
            "legend.fontsize": PLOT_LEGEND_SIZE,
            "figure.titlesize": PLOT_LABEL_SIZE,
            "axes.titlesize": PLOT_LABEL_SIZE,
            "savefig.dpi": 200,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


def clear_plot_titles() -> None:
    import matplotlib.pyplot as plt

    figure = plt.gcf()
    if figure._suptitle is not None:
        figure._suptitle.set_text("")
    for axis in figure.axes:
        axis.set_title("")


def format_existing_plot_text() -> None:
    import matplotlib.pyplot as plt

    for axis in plt.gcf().axes:
        axis.xaxis.label.set_size(PLOT_LABEL_SIZE)
        axis.yaxis.label.set_size(PLOT_LABEL_SIZE)
        axis.tick_params(axis="both", labelsize=PLOT_TICK_SIZE)
        legend = axis.get_legend()
        if legend is not None:
            for text in legend.get_texts():
                text.set_fontsize(PLOT_LEGEND_SIZE)


def dynamic_boxplot_kwargs(flier_markersize: float = 1.0) -> dict[str, Any]:
    return {
        "patch_artist": True,
        "boxprops": {
            "facecolor": DYNAMIC_BOXPLOT_COLOR,
            "edgecolor": DYNAMIC_BOXPLOT_EDGE_COLOR,
            "alpha": 0.65,
            "linewidth": 1.8,
        },
        "medianprops": {"color": DYNAMIC_BOXPLOT_EDGE_COLOR, "linewidth": 2.1},
        "whiskerprops": {"color": DYNAMIC_BOXPLOT_EDGE_COLOR, "linewidth": 1.8},
        "capprops": {"color": DYNAMIC_BOXPLOT_EDGE_COLOR, "linewidth": 1.8},
        "flierprops": {
            "marker": "o",
            "markersize": flier_markersize,
            "markerfacecolor": DYNAMIC_BOXPLOT_EDGE_COLOR,
            "markeredgecolor": DYNAMIC_BOXPLOT_EDGE_COLOR,
            "markeredgewidth": 0.35,
            "alpha": 0.6,
        },
    }


def color_current_boxplots() -> None:
    import matplotlib.pyplot as plt

    axis = plt.gca()
    for patch in axis.patches:
        patch.set_facecolor(DYNAMIC_BOXPLOT_COLOR)
        patch.set_alpha(0.65)
        patch.set_edgecolor(DYNAMIC_BOXPLOT_EDGE_COLOR)
        patch.set_linewidth(1.8)


def finish_robot_plot(path: Path) -> None:
    import matplotlib.pyplot as plt

    configure_matplotlib()
    clear_plot_titles()
    format_existing_plot_text()
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(path)
    plt.savefig(path.with_suffix(".pdf"))
    plt.close()


def finish_paper_panel_plot(path: Path) -> None:
    import matplotlib.pyplot as plt

    configure_matplotlib()
    clear_plot_titles()
    figure = plt.gcf()
    for axis in figure.axes:
        axis.xaxis.label.set_size(8.8)
        axis.yaxis.label.set_size(8.8)
        axis.tick_params(axis="both", labelsize=8.3)
    plt.xticks(rotation=45, ha="right")
    figure.subplots_adjust(left=0.15, right=0.995, bottom=0.30, top=0.98)
    plt.savefig(path)
    plt.savefig(path.with_suffix(".pdf"))
    plt.close()


def plot_checker_cpu_by_role(process: Any, runs: Any, path: Path) -> None:
    import matplotlib.pyplot as plt

    final = checker_processes(measured_process_samples(process, runs))
    if final.empty:
        return
    grouped = final.groupby(["robots", "role"])["cpu_time_secs"].sum().unstack(fill_value=0)
    grouped = grouped.rename(columns={"trustworthiness_checker": "launcher"})
    grouped.plot(kind="bar", stacked=True, figsize=(robot_plot_width(final), 5))
    plt.ylabel("monitoring CPU time (s)")
    plt.title("Total monitoring CPU by role")
    finish_robot_plot(path)


def checker_run_costs(process: Any, runs: Any) -> Any:
    import pandas as pd

    final = checker_processes(measured_process_samples(process, runs))
    if final.empty:
        return pd.DataFrame()
    grouped = (
        final.groupby(["run_id", "robots", "seed", "role"])["cpu_time_secs"]
        .sum()
        .unstack(fill_value=0)
        .reset_index()
    )
    for role in ["scheduler", "worker", "trustworthiness_checker"]:
        if role not in grouped:
            grouped[role] = 0.0
    grouped["total_checker_cpu_time_secs"] = (
        grouped["scheduler"] + grouped["worker"] + grouped["trustworthiness_checker"]
    )
    run_meta = runs[["run_id", "duration_secs"]].drop_duplicates()
    grouped = grouped.merge(run_meta, on="run_id", how="left")
    grouped["total_checker_cpu_per_second"] = (
        grouped["total_checker_cpu_time_secs"] / grouped["duration_secs"]
    )
    grouped["scheduler_cpu_per_second"] = grouped["scheduler"] / grouped["duration_secs"]
    grouped["worker_cpu_per_second"] = grouped["worker"] / grouped["duration_secs"]
    return grouped


def plot_total_checker_cpu_by_run(process: Any, runs: Any, path: Path) -> None:
    import matplotlib.pyplot as plt

    costs = checker_run_costs(process, runs)
    if costs.empty:
        return
    costs.boxplot(
        column="total_checker_cpu_time_secs",
        by="robots",
        figsize=PAPER_TWO_COLUMN_PANEL_FIGSIZE,
        **dynamic_boxplot_kwargs(flier_markersize=3.6),
    )
    color_current_boxplots()
    plt.suptitle("")
    plt.title("Total monitoring CPU per run across scheduler and workers")
    plt.ylabel("total CPU time per run (s)")
    finish_paper_panel_plot(path)


def plot_total_checker_cpu_per_second_by_run(process: Any, runs: Any, path: Path) -> None:
    import matplotlib.pyplot as plt

    costs = checker_run_costs(process, runs)
    if costs.empty:
        return
    grouped = costs.groupby("robots")[
        ["scheduler_cpu_per_second", "worker_cpu_per_second"]
    ].mean()
    grouped.plot(kind="bar", stacked=True, figsize=(robot_plot_width(costs), 5))
    plt.ylabel("CPU seconds / benchmark second")
    plt.title("Total monitoring CPU rate per run across scheduler and workers")
    finish_robot_plot(path)


def scheduler_process_samples(process: Any, runs: Any) -> Any:
    final = measured_process_samples(process, runs)
    if final.empty:
        return final
    scheduler = final[final["role"] == "scheduler"].copy()
    if scheduler.empty:
        return scheduler
    run_meta = runs[["run_id", "duration_secs"]].drop_duplicates()
    scheduler = scheduler.merge(run_meta, on="run_id", how="left")
    scheduler["cpu_time_per_measured_sec"] = (
        scheduler["cpu_time_secs"] / scheduler["duration_secs"]
    )
    scheduler["user_cpu_time_per_measured_sec"] = (
        scheduler["user_cpu_time_secs"] / scheduler["duration_secs"]
    )
    scheduler["system_cpu_time_per_measured_sec"] = (
        scheduler["system_cpu_time_secs"] / scheduler["duration_secs"]
    )
    return scheduler


def plot_scheduler_cpu_per_second(process: Any, runs: Any, path: Path) -> None:
    import matplotlib.pyplot as plt

    scheduler = scheduler_process_samples(process, runs)
    if scheduler.empty:
        return
    scheduler.boxplot(
        column="cpu_time_per_measured_sec",
        by="robots",
        figsize=(robot_plot_width(scheduler), 5),
    )
    plt.suptitle("")
    plt.title("Per-node scheduler CPU rate")
    plt.ylabel("scheduler CPU seconds / measured second")
    finish_robot_plot(path)


def plot_scheduler_cpu_user_system_per_second(process: Any, runs: Any, path: Path) -> None:
    import matplotlib.pyplot as plt

    scheduler = scheduler_process_samples(process, runs)
    if scheduler.empty:
        return
    grouped = scheduler.groupby("robots")[
        ["user_cpu_time_per_measured_sec", "system_cpu_time_per_measured_sec"]
    ].mean()
    grouped = grouped.rename(
        columns={
            "user_cpu_time_per_measured_sec": "user CPU",
            "system_cpu_time_per_measured_sec": "system CPU",
        }
    )
    grouped.plot(kind="bar", stacked=True, figsize=(robot_plot_width(scheduler), 5))
    plt.ylabel("scheduler CPU seconds / measured second")
    plt.title("Per-node scheduler CPU rate split by user/system time")
    finish_robot_plot(path)


def plot_checker_cpu_rate_timeseries(process: Any, runs: Any, role: str, path: Path) -> None:
    import matplotlib.pyplot as plt
    import pandas as pd

    if process.empty:
        return
    samples = measured_rows(process, runs, keep_unknown_elapsed=False)
    samples = samples[samples["role"] == role].copy() if not samples.empty else samples
    if samples.empty:
        return
    rows = []
    for (run_id, pid), group in samples.sort_values("elapsed_secs").groupby(["run_id", "pid"]):
        group = group.dropna(subset=["elapsed_secs", "cpu_time_secs"])
        if len(group) < 2:
            continue
        delta_cpu = group["cpu_time_secs"].diff()
        delta_elapsed = group["elapsed_secs"].diff()
        rate = delta_cpu / delta_elapsed
        for elapsed, value in zip(group["elapsed_secs"], rate):
            if pd.notna(value) and value >= 0.0:
                rows.append({"run_id": run_id, "elapsed_secs": elapsed, "cpu_rate": value})
    if not rows:
        return
    df = pd.DataFrame(rows).merge(runs[["run_id", "robots"]], on="run_id", how="left")
    df["elapsed_bucket_secs"] = (df["elapsed_secs"].astype(float) // 5.0) * 5.0
    per_run = df.groupby(["run_id", "robots", "elapsed_bucket_secs"])["cpu_rate"].sum().reset_index()
    grouped = per_run.groupby(["robots", "elapsed_bucket_secs"])["cpu_rate"].mean().reset_index()
    plt.figure(figsize=(robot_plot_width(grouped), 5))
    for robots, group in grouped.groupby("robots"):
        plt.plot(group["elapsed_bucket_secs"], group["cpu_rate"], marker="o", label=f"{robots} robots")
    plt.xlabel("elapsed benchmark seconds")
    plt.ylabel(f"{role} CPU seconds / wall second")
    plt.title(f"{role.capitalize()} CPU rate over time")
    plt.grid(True, axis="both", alpha=0.3)
    if grouped["robots"].nunique() <= 12:
        plt.legend(fontsize="small")
    finish_robot_plot(path)


def plot_worker_cpu(process: Any, runs: Any, path: Path) -> None:
    import matplotlib.pyplot as plt

    worker = measured_process_samples(process, runs)
    worker = worker[worker["role"] == "worker"] if not worker.empty else worker
    if worker.empty:
        return
    worker.boxplot(column="cpu_time_secs", by="robots", figsize=(robot_plot_width(worker), 5))
    plt.suptitle("")
    plt.title("Per-node worker CPU distribution")
    plt.ylabel("per-node worker CPU time (s)")
    finish_robot_plot(path)


def plot_per_node_checker_cpu(process: Any, runs: Any, path: Path) -> None:
    import matplotlib.pyplot as plt

    final = checker_processes(measured_process_samples(process, runs))
    if final.empty:
        return
    final.boxplot(column="cpu_time_secs", by="robots", figsize=(robot_plot_width(final), 5))
    plt.suptitle("")
    plt.title("Per-node monitoring CPU distribution")
    plt.ylabel("per-node CPU time (scheduler or worker, s)")
    finish_robot_plot(path)


def plot_per_node_checker_cpu_without_outliers(process: Any, runs: Any, path: Path) -> None:
    import matplotlib.pyplot as plt

    final = checker_processes(measured_process_samples(process, runs))
    if final.empty:
        return
    final.boxplot(
        column="cpu_time_secs",
        by="robots",
        figsize=(robot_plot_width(final), 5),
        showfliers=False,
    )
    plt.suptitle("")
    plt.title("Per-node monitoring CPU distribution without outliers")
    plt.ylabel("per-node CPU time (scheduler or worker, s)")
    finish_robot_plot(path)


def plot_checker_memory_by_role(process: Any, runs: Any, path: Path) -> None:
    import matplotlib.pyplot as plt

    final = checker_processes(measured_process_samples(process, runs))
    if final.empty:
        return
    final = final.copy()
    final["rss_mib"] = final["rss_bytes"] / (1024 * 1024)
    grouped = final.groupby(["robots", "role"])["rss_mib"].max().unstack(fill_value=0)
    grouped = grouped.rename(columns={"trustworthiness_checker": "launcher"})
    grouped.plot(kind="bar", figsize=(robot_plot_width(final), 5))
    plt.ylabel("max RSS (MiB)")
    plt.title("Monitoring memory by role")
    finish_robot_plot(path)


def plot_total_checker_memory_by_run(process: Any, runs: Any, path: Path) -> None:
    import matplotlib.pyplot as plt

    final = checker_processes(measured_process_samples(process, runs))
    if final.empty:
        return
    grouped = final.groupby(["run_id", "robots", "seed"])["rss_bytes"].sum().reset_index()
    grouped["rss_mib"] = grouped["rss_bytes"] / (1024 * 1024)
    grouped.boxplot(column="rss_mib", by="robots", figsize=(robot_plot_width(grouped), 5))
    plt.suptitle("")
    plt.title("Total monitoring RSS across scheduler and workers")
    plt.ylabel("total final RSS per run (MiB)")
    finish_robot_plot(path)


def plot_per_node_checker_memory(process: Any, runs: Any, path: Path) -> None:
    import matplotlib.pyplot as plt

    final = checker_processes(measured_process_samples(process, runs))
    if final.empty:
        return
    final = final.copy()
    final["rss_mib"] = final["rss_bytes"] / (1024 * 1024)
    final.boxplot(column="rss_mib", by="robots", figsize=(robot_plot_width(final), 5))
    plt.suptitle("")
    plt.title("Per-node monitoring memory distribution")
    plt.ylabel("per-node RSS (scheduler or worker, MiB)")
    finish_robot_plot(path)


def plot_worker_memory(process: Any, runs: Any, path: Path) -> None:
    import matplotlib.pyplot as plt

    final = measured_process_samples(process, runs)
    worker = final[final["role"] == "worker"] if not final.empty else final
    if worker.empty:
        return
    worker = worker.copy()
    worker["rss_mib"] = worker["rss_bytes"] / (1024 * 1024)
    worker.boxplot(column="rss_mib", by="robots", figsize=(robot_plot_width(worker), 5))
    plt.suptitle("")
    plt.title("Per-node worker memory distribution")
    plt.ylabel("per-node worker RSS (MiB)")
    finish_robot_plot(path)


def plot_ros_shared_memory(process: Any, runs: Any, path: Path) -> None:
    import matplotlib.pyplot as plt

    samples = measured_rows(process, runs, keep_unknown_elapsed=False)
    shm = samples[samples["role"] == ROS_SHM_ROLE] if not samples.empty else samples
    if shm.empty:
        return
    grouped = shm.groupby(["run_id", "robots", "seed"])["rss_bytes"].max().reset_index()
    grouped["shm_mib"] = grouped["rss_bytes"] / (1024 * 1024)
    grouped.boxplot(column="shm_mib", by="robots", figsize=(robot_plot_width(grouped), 5))
    plt.suptitle("")
    plt.title("ROS / Fast DDS shared memory usage")
    plt.ylabel("max /dev/shm fastrtps usage per run (MiB)")
    finish_robot_plot(path)


def plot_scheduler_mape(telemetry: Any, runs: Any, path: Path) -> None:
    import matplotlib.pyplot as plt
    import pandas as pd

    df = scheduler_mape_plot_dataframe(pd, measured_rows(telemetry, runs, keep_unknown_elapsed=False), runs)
    if df.empty:
        return
    stack = df[df["phase"].isin(["monitor", "analyse", "plan", "execute"])]
    if stack.empty:
        return
    grouped = stack.groupby(["robots", "phase"])["duration_ms"].mean().unstack(fill_value=0)
    phase_order = [phase for phase in ["monitor", "analyse", "plan", "execute"] if phase in grouped]
    grouped[phase_order].plot(
        kind="bar",
        stacked=True,
        figsize=(robot_plot_width(df), 5),
    )
    plt.ylabel("mean per-event duration (ms)")
    plt.title("Per-event scheduler MAPE phase cost")
    finish_robot_plot(path)


def scheduler_mape_plot_dataframe(pd: Any, telemetry: Any, runs: Any) -> Any:
    rows = []
    phases = telemetry[telemetry["event_type"] == "scheduler_mape_phase"]
    for _, row in phases.iterrows():
        payload = json.loads(row["payload_json"])
        rows.append(
            {
                "run_id": row["run_id"],
                "elapsed_secs": row.get("elapsed_secs"),
                "phase": normalize_mape_phase(payload.get("phase")),
                "duration_ms": payload.get("duration_ms"),
            }
        )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).merge(runs[["run_id", "robots", "seed"]], on="run_id", how="left")


def plot_scheduler_mape_total(telemetry: Any, runs: Any, path: Path) -> None:
    import matplotlib.pyplot as plt
    import pandas as pd

    df = scheduler_mape_plot_dataframe(pd, measured_rows(telemetry, runs, keep_unknown_elapsed=False), runs)
    if df.empty:
        return
    stack = df[df["phase"].isin(["monitor", "analyse", "plan", "execute"])]
    if stack.empty:
        return
    per_run = (
        stack.groupby(["run_id", "robots", "seed", "phase"])["duration_ms"]
        .sum()
        .unstack(fill_value=0)
        .reset_index()
    )
    phase_order = [phase for phase in ["monitor", "analyse", "plan", "execute"] if phase in per_run]
    grouped = per_run.groupby("robots")[phase_order].mean()
    grouped.plot(kind="bar", stacked=True, figsize=(robot_plot_width(per_run), 5))
    plt.ylabel("mean total duration per run (ms)")
    plt.title("Total scheduler MAPE phase cost per run")
    finish_robot_plot(path)


def plot_scheduler_mape_tail_latency(telemetry: Any, runs: Any, path: Path) -> None:
    import matplotlib.pyplot as plt
    import pandas as pd

    df = scheduler_mape_plot_dataframe(pd, measured_rows(telemetry, runs, keep_unknown_elapsed=False), runs)
    if df.empty:
        return
    df = df[df["phase"].isin(["monitor", "analyse", "plan", "execute"])].dropna(subset=["duration_ms"])
    if df.empty:
        return
    grouped = df.groupby(["robots", "phase"])["duration_ms"].quantile(0.95).unstack(fill_value=0)
    phase_order = [phase for phase in ["monitor", "analyse", "plan", "execute"] if phase in grouped]
    grouped[phase_order].plot(kind="bar", figsize=(robot_plot_width(df), 5))
    plt.ylabel("p95 per-event duration (ms)")
    plt.title("Scheduler MAPE phase p95 latency")
    finish_robot_plot(path)


def plot_scheduler_iteration_tail_latency(telemetry: Any, runs: Any, path: Path) -> None:
    import matplotlib.pyplot as plt
    import pandas as pd

    df = scheduler_mape_plot_dataframe(pd, measured_rows(telemetry, runs, keep_unknown_elapsed=False), runs)
    if df.empty:
        return
    df = df[(df["phase"] == "iteration_total")].dropna(subset=["duration_ms"])
    if df.empty:
        return
    grouped = df.groupby("robots")["duration_ms"].quantile([0.50, 0.95, 0.99]).unstack()
    grouped = grouped.rename(columns={0.50: "p50", 0.95: "p95", 0.99: "p99"})
    grouped.plot(kind="line", marker="o", figsize=(robot_plot_width(df), 5))
    plt.xlabel("robots")
    plt.ylabel("iteration duration (ms)")
    plt.title("Scheduler iteration latency percentiles")
    plt.grid(True, axis="both", alpha=0.3)
    finish_robot_plot(path)


def plot_scheduler_phase_latency_timeseries(telemetry: Any, runs: Any, path: Path) -> None:
    import matplotlib.pyplot as plt
    import pandas as pd

    df = scheduler_mape_plot_dataframe(pd, measured_rows(telemetry, runs, keep_unknown_elapsed=False), runs)
    if df.empty or "elapsed_secs" not in df:
        return
    df = df[df["phase"].isin(["plan", "execute", "iteration_total"])].dropna(
        subset=["elapsed_secs", "duration_ms"]
    )
    if df.empty:
        return
    df["elapsed_bucket_secs"] = (df["elapsed_secs"].astype(float) // 5.0) * 5.0
    grouped = (
        df.groupby(["robots", "elapsed_bucket_secs", "phase"])["duration_ms"]
        .quantile(0.95)
        .reset_index()
    )
    plt.figure(figsize=(robot_plot_width(grouped), 5))
    for (robots, phase), group in grouped.groupby(["robots", "phase"]):
        plt.plot(
            group["elapsed_bucket_secs"],
            group["duration_ms"],
            marker="o",
            linewidth=1.2,
            label=f"{robots} robots {phase}",
        )
    plt.xlabel("elapsed benchmark seconds")
    plt.ylabel("5s-bucket p95 duration (ms)")
    plt.title("Scheduler phase latency over time")
    plt.grid(True, axis="both", alpha=0.3)
    if grouped[["robots", "phase"]].drop_duplicates().shape[0] <= 12:
        plt.legend(fontsize="small")
    finish_robot_plot(path)


def sat_solver_dataframe(pd: Any, telemetry: Any, runs: Any) -> Any:
    rows = []
    telemetry = measured_rows(telemetry, runs, keep_unknown_elapsed=False)
    sat_events = telemetry[telemetry["event_type"] == "sat_solver"]
    for _, row in sat_events.iterrows():
        payload = json.loads(row["payload_json"])
        rows.append(
            {
                "run_id": row["run_id"],
                "elapsed_secs": row.get("elapsed_secs"),
                "phase": payload.get("phase"),
                "result": payload.get("result"),
                "fast_path": payload.get("fast_path"),
                "forced_sat": payload.get("forced_sat"),
                "duration_ms": payload.get("duration_ms"),
                "total_duration_ms": payload.get("total_duration_ms"),
                "nodes": payload.get("nodes"),
                "clauses": payload.get("clauses"),
                "vars": payload.get("vars"),
                "atoms": payload.get("atoms"),
            }
        )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).merge(runs[["run_id", "robots"]], on="run_id", how="left")


def plot_sat_solver_time_boxplot(telemetry: Any, runs: Any, path: Path) -> None:
    import matplotlib.pyplot as plt
    import pandas as pd

    df = sat_solver_dataframe(pd, telemetry, runs)
    if df.empty:
        return
    solve = sat_terminal_solver_dataframe(pd, df).dropna(subset=["solver_duration_ms"])
    if solve.empty:
        return
    solve.boxplot(
        column="solver_duration_ms",
        by="robots",
        figsize=PAPER_TWO_COLUMN_PANEL_FIGSIZE,
        **dynamic_boxplot_kwargs(),
    )
    color_current_boxplots()
    plt.suptitle("")
    plt.title("Distribution solver time by robot count")
    plt.ylabel("terminal solver duration (ms)")
    finish_robot_plot(path)


def plot_sat_solver_time_scatter(telemetry: Any, runs: Any, path: Path) -> None:
    import matplotlib.pyplot as plt
    import pandas as pd

    df = sat_solver_dataframe(pd, telemetry, runs)
    if df.empty:
        return
    solve = sat_terminal_solver_dataframe(pd, df).dropna(subset=["solver_duration_ms"])
    if solve.empty:
        return
    plt.figure(figsize=(robot_plot_width(solve), 5))
    scatter = plt.scatter(
        solve["robots"],
        solve["solver_duration_ms"],
        c=solve["clauses"].fillna(0),
        cmap="viridis",
        alpha=0.8,
    )
    plt.xlabel("robots")
    plt.ylabel("terminal solver duration (ms)")
    plt.title("Distribution solver time by robot count")
    plt.colorbar(scatter, label="CNF clauses")
    finish_robot_plot(path)


def plot_sat_solver_total(telemetry: Any, runs: Any, path: Path) -> None:
    import matplotlib.pyplot as plt
    import pandas as pd

    df = sat_solver_dataframe(pd, telemetry, runs)
    if df.empty:
        return
    solve = sat_terminal_solver_dataframe(pd, df).dropna(subset=["solver_duration_ms"])
    if solve.empty:
        return
    per_run = solve.groupby(["run_id", "robots"])["solver_duration_ms"].sum().reset_index()
    per_run.boxplot(
        column="solver_duration_ms",
        by="robots",
        figsize=PAPER_TWO_COLUMN_PANEL_FIGSIZE,
        **dynamic_boxplot_kwargs(flier_markersize=3.6),
    )
    color_current_boxplots()
    plt.suptitle("")
    plt.title("Total SAT solver time per run")
    plt.ylabel("SAT solver time per run (ms)")
    finish_paper_panel_plot(path)


def plot_sat_solver_normalized_cost(summaries: Any, path: Path) -> None:
    import matplotlib.pyplot as plt

    if summaries.empty:
        return
    columns = [
        "sat_solver_ms_per_clause",
        "sat_solver_ms_per_var",
        "sat_solver_ms_per_constraint",
        "sat_solver_ms_per_assigned_stream",
    ]
    available = [column for column in columns if column in summaries]
    if not available:
        return
    df = summaries.dropna(subset=available, how="all")
    if df.empty:
        return
    grouped = df.groupby("robots")[available].mean()
    grouped = grouped.rename(
        columns={
            "sat_solver_ms_per_clause": "ms / clause",
            "sat_solver_ms_per_var": "ms / var",
            "sat_solver_ms_per_constraint": "ms / constraint",
            "sat_solver_ms_per_assigned_stream": "ms / assigned stream",
        }
    )
    grouped.plot(kind="line", marker="o", figsize=(robot_plot_width(df), 5))
    plt.xlabel("robots")
    plt.ylabel("terminal solver normalized duration")
    plt.title("SAT solver normalized cost")
    plt.grid(True, axis="both", alpha=0.3)
    finish_robot_plot(path)


def plot_reconfiguration_activity(telemetry: Any, runs: Any, path: Path) -> None:
    import matplotlib.pyplot as plt
    import pandas as pd

    telemetry = measured_rows(telemetry, runs, keep_unknown_elapsed=False)
    ticks = telemetry[telemetry["event_type"] == "sim_tick"]
    worker_reconfigs = telemetry[telemetry["event_type"] == "worker_reconfiguration"]
    if ticks.empty and worker_reconfigs.empty:
        return
    rows = []
    for _, row in ticks.iterrows():
        payload = json.loads(row["payload_json"])
        rows.append(
            {
                "run_id": row["run_id"],
                "reconfig_messages_received": payload.get("reconfig_messages_received", 0),
            }
        )
    tick_df = (
        pd.DataFrame(rows).groupby("run_id")["reconfig_messages_received"].max().reset_index()
        if rows
        else pd.DataFrame(columns=["run_id", "reconfig_messages_received"])
    )
    worker_df = (
        worker_reconfigs.groupby("run_id").size().rename("worker_reconfiguration_events").reset_index()
        if not worker_reconfigs.empty
        else pd.DataFrame(columns=["run_id", "worker_reconfiguration_events"])
    )
    df = runs[["run_id", "robots"]].merge(tick_df, on="run_id", how="left").merge(
        worker_df, on="run_id", how="left"
    )
    df[["reconfig_messages_received", "worker_reconfiguration_events"]] = df[
        ["reconfig_messages_received", "worker_reconfiguration_events"]
    ].fillna(0)
    df.groupby("robots")[
        ["reconfig_messages_received", "worker_reconfiguration_events"]
    ].mean().plot(kind="bar", figsize=(robot_plot_width(df), 5))
    plt.ylabel("events per run")
    plt.title("Reconfiguration activity")
    finish_robot_plot(path)


def plot_reconfiguration_activity_timeseries(telemetry: Any, runs: Any, path: Path) -> None:
    import matplotlib.pyplot as plt

    telemetry = measured_rows(telemetry, runs, keep_unknown_elapsed=False)
    df = telemetry[
        (telemetry["event_type"] == "worker_reconfiguration")
        & telemetry["elapsed_secs"].notna()
    ].merge(runs[["run_id", "robots"]], on="run_id", how="left")
    if df.empty:
        return
    df["elapsed_bucket_secs"] = (df["elapsed_secs"].astype(float) // 5.0) * 5.0
    per_run = df.groupby(["run_id", "robots", "elapsed_bucket_secs"]).size().reset_index(name="events")
    grouped = per_run.groupby(["robots", "elapsed_bucket_secs"])["events"].mean().reset_index()
    plt.figure(figsize=(robot_plot_width(grouped), 5))
    for robots, group in grouped.groupby("robots"):
        plt.plot(group["elapsed_bucket_secs"], group["events"], marker="o", label=f"{robots} robots")
    plt.xlabel("elapsed benchmark seconds")
    plt.ylabel("worker reconfiguration events per 5s bucket")
    plt.title("Reconfiguration activity over time")
    plt.grid(True, axis="both", alpha=0.3)
    if grouped["robots"].nunique() <= 12:
        plt.legend(fontsize="small")
    finish_robot_plot(path)


def plot_reconfiguration_latency(summaries: Any, path: Path) -> None:
    import matplotlib.pyplot as plt

    columns = [
        "reconfiguration_latency_p50_ms",
        "reconfiguration_latency_p95_ms",
        "reconfiguration_latency_p99_ms",
    ]
    if summaries.empty or not all(column in summaries for column in columns):
        return
    df = summaries.dropna(subset=columns, how="all")
    if df.empty:
        return
    grouped = df.groupby("robots")[columns].mean().rename(
        columns={
            "reconfiguration_latency_p50_ms": "p50",
            "reconfiguration_latency_p95_ms": "p95",
            "reconfiguration_latency_p99_ms": "p99",
        }
    )
    grouped.plot(kind="line", marker="o", figsize=(robot_plot_width(df), 5))
    plt.xlabel("robots")
    plt.ylabel("execute-to-worker reconfiguration latency (ms)")
    plt.title("Best-effort reconfiguration latency")
    plt.grid(True, axis="both", alpha=0.3)
    finish_robot_plot(path)


def plot_coverage(
    coverage: Any,
    runs: Any,
    path: Path,
    y_min: float = 0.0,
    title: str = "Monitoring coverage by robot count",
) -> None:
    import matplotlib.pyplot as plt

    coverage = measured_rows(coverage, runs, keep_unknown_elapsed=False)
    df = coverage.merge(runs[["run_id", "robots"]], on="run_id")
    run_cov = df.groupby(["run_id", "robots"])["coverage"].mean().reset_index()
    grouped = run_cov.groupby("robots")["coverage"].agg(["mean", "std"]).fillna(0)
    grouped["mean"].plot(
        kind="bar",
        yerr=grouped["std"],
        capsize=3,
        figsize=(robot_plot_width(run_cov), 5),
    )
    plt.ylim(y_min, 1)
    plt.ylabel("mean run coverage")
    plt.title(title)
    plt.grid(True, axis="both", alpha=0.3)
    for x in [tick - 0.5 for tick in range(1, len(grouped.index))]:
        plt.axvline(x, color="0.85", linewidth=0.8, zorder=0)
    finish_robot_plot(path)


def plot_coverage_scatter_mean(
    coverage: Any,
    runs: Any,
    path: Path,
    y_min: float = 0.0,
    title: str = "Monitoring coverage by robot count (scatter)",
) -> None:
    import matplotlib.pyplot as plt

    coverage = measured_rows(coverage, runs, keep_unknown_elapsed=False)
    df = coverage.merge(runs[["run_id", "robots"]], on="run_id")
    run_cov = df.groupby(["run_id", "robots"])["coverage"].mean().reset_index()
    if run_cov.empty:
        return
    grouped = run_cov.groupby("robots")["coverage"].agg(["mean", "std"]).fillna(0).reset_index()
    plt.figure(figsize=(robot_plot_width(run_cov), 5))
    plt.errorbar(
        grouped["robots"],
        grouped["mean"],
        yerr=grouped["std"],
        fmt="o-",
        capsize=3,
        linewidth=1.5,
    )
    plt.ylim(y_min, 1)
    plt.xlabel("robots")
    plt.ylabel("mean run coverage")
    plt.title(title)
    plt.grid(True, axis="both", alpha=0.3)
    finish_robot_plot(path)


def coverage_run_means(coverage: Any, runs: Any) -> Any:
    coverage = measured_rows(coverage, runs, keep_unknown_elapsed=False)
    df = coverage.merge(runs[["run_id", "robots", "seed"]], on="run_id")
    return df.groupby(["run_id", "robots", "seed"])["coverage"].mean().reset_index()


def ordinary_least_squares_line(x_values: Any, y_values: Any) -> tuple[float, float] | None:
    import numpy as np

    x = np.asarray(x_values, dtype=float)
    y = np.asarray(y_values, dtype=float)
    if len(x) < 2:
        return None
    design = np.column_stack([np.ones_like(x), x])
    intercept, slope = np.linalg.lstsq(design, y, rcond=None)[0]
    return float(intercept), float(slope)


def tight_ylim(values: Any, lower_bound: float = 0.0, upper_bound: float = 1.0) -> tuple[float, float]:
    values = values.dropna()
    if values.empty:
        return lower_bound, upper_bound
    low = float(values.min())
    high = float(values.max())
    span = high - low
    margin = max(0.0025, span * 0.25)
    return max(lower_bound, low - margin), min(upper_bound, high + margin)


def plot_coverage_trend_zoom(coverage: Any, runs: Any, path: Path) -> None:
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd

    run_cov = coverage_run_means(coverage, runs)
    if run_cov.empty:
        return
    grouped = (
        run_cov.groupby("robots")["coverage"]
        .agg(["mean", "std", "count"])
        .reset_index()
        .sort_values("robots")
    )
    if grouped.empty:
        return
    grouped["sem"] = grouped["std"].fillna(0.0) / np.sqrt(grouped["count"].clip(lower=1))
    grouped["ci95"] = 1.96 * grouped["sem"]
    fit = ordinary_least_squares_line(run_cov["robots"], run_cov["coverage"])

    plt.figure(figsize=(robot_plot_width(run_cov), 5))
    plt.scatter(run_cov["robots"], run_cov["coverage"], alpha=0.28, s=18, label="run mean")
    plt.errorbar(
        grouped["robots"],
        grouped["mean"],
        yerr=grouped["ci95"],
        fmt="o-",
        capsize=3,
        linewidth=1.6,
        label="mean +/- 95% CI",
    )
    if fit is not None:
        intercept, slope = fit
        xs = np.linspace(grouped["robots"].min(), grouped["robots"].max(), 100)
        plt.plot(xs, intercept + slope * xs, linestyle="--", linewidth=1.4, label="linear fit")
        plt.text(
            0.02,
            0.04,
            f"slope: {slope * 10:+.4f} coverage / 10 robots",
            transform=plt.gca().transAxes,
            fontsize="small",
        )
    band_values = pd.concat(
        [grouped["mean"], grouped["mean"] - grouped["ci95"], grouped["mean"] + grouped["ci95"]]
    )
    low, high = tight_ylim(band_values)
    plt.ylim(low, high)
    plt.xlabel("robots")
    plt.ylabel("run mean coverage")
    plt.title("Monitoring coverage trend by robot count (tight scale)")
    plt.grid(True, axis="both", alpha=0.3)
    plt.legend(fontsize="small")
    finish_robot_plot(path)


def plot_coverage_change_from_baseline(coverage: Any, runs: Any, path: Path) -> None:
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd

    run_cov = coverage_run_means(coverage, runs)
    if run_cov.empty:
        return
    baseline_robots = run_cov["robots"].min()
    baseline = run_cov[run_cov["robots"] == baseline_robots][["seed", "coverage"]].rename(
        columns={"coverage": "baseline_coverage"}
    )
    paired = run_cov.merge(baseline, on="seed", how="inner")
    if paired.empty:
        return
    paired["coverage_delta_pp"] = (paired["coverage"] - paired["baseline_coverage"]) * 100.0
    grouped = (
        paired.groupby("robots")["coverage_delta_pp"]
        .agg(["mean", "std", "count"])
        .reset_index()
        .sort_values("robots")
    )
    if grouped.empty:
        return
    grouped["sem"] = grouped["std"].fillna(0.0) / np.sqrt(grouped["count"].clip(lower=1))
    grouped["ci95"] = 1.96 * grouped["sem"]
    plt.figure(figsize=(robot_plot_width(paired), 5))
    plt.scatter(
        paired["robots"],
        paired["coverage_delta_pp"],
        color="0.6",
        alpha=0.18,
        s=8,
        label="paired seed delta",
    )
    plt.errorbar(
        grouped["robots"],
        grouped["mean"],
        yerr=grouped["ci95"],
        fmt="o-",
        color="tab:blue",
        capsize=3,
        linewidth=1.8,
        label="mean +/- 95% CI",
    )
    plt.axhline(0.0, color="black", linewidth=1.0, alpha=0.7)
    band_values = pd.concat(
        [
            grouped["mean"],
            grouped["mean"] - grouped["ci95"],
            grouped["mean"] + grouped["ci95"],
            grouped["mean"].iloc[0:1] * 0.0,
        ]
    )
    low, high = tight_ylim(band_values, lower_bound=-100.0, upper_bound=100.0)
    plt.ylim(low, high)
    plt.xlabel("robots")
    plt.ylabel(f"coverage change from {int(baseline_robots)} robots (percentage points)")
    plt.title("Paired coverage change from smallest robot count")
    plt.grid(True, axis="both", alpha=0.3)
    plt.legend(fontsize="small")
    finish_robot_plot(path)


def plot_coverage_distribution(
    coverage: Any,
    runs: Any,
    path: Path,
    y_min: float = 0.0,
    title: str = "Coverage distribution across seeds",
) -> None:
    import matplotlib.pyplot as plt

    coverage = measured_rows(coverage, runs, keep_unknown_elapsed=False)
    df = coverage.merge(runs[["run_id", "robots"]], on="run_id")
    run_cov = df.groupby(["run_id", "robots"])["coverage"].mean().reset_index()
    if run_cov.empty:
        return
    run_cov.boxplot(column="coverage", by="robots", figsize=(robot_plot_width(run_cov), 5))
    plt.suptitle("")
    plt.ylim(y_min, 1)
    plt.ylabel("run mean coverage")
    plt.title(title)
    plt.grid(True, axis="both", alpha=0.3)
    finish_robot_plot(path)


def plot_coverage_violin(
    coverage: Any,
    runs: Any,
    path: Path,
    y_min: float = 0.0,
    title: str = "Coverage distribution across seeds (violin)",
) -> None:
    import matplotlib.pyplot as plt

    coverage = measured_rows(coverage, runs, keep_unknown_elapsed=False)
    df = coverage.merge(runs[["run_id", "robots"]], on="run_id")
    run_cov = df.groupby(["run_id", "robots"])["coverage"].mean().reset_index()
    if run_cov.empty:
        return
    robots = sorted(run_cov["robots"].dropna().unique())
    data = [run_cov[run_cov["robots"] == robots_count]["coverage"].dropna() for robots_count in robots]
    if not any(len(values) for values in data):
        return
    plt.figure(figsize=(robot_plot_width(run_cov), 5))
    parts = plt.violinplot(data, positions=range(len(robots)), showmeans=True, showextrema=True)
    for body in parts["bodies"]:
        body.set_alpha(0.65)
    plt.xticks(range(len(robots)), [str(robots_count) for robots_count in robots])
    plt.ylim(y_min, 1)
    plt.xlabel("robots")
    plt.ylabel("run mean coverage")
    plt.title(title)
    plt.grid(True, axis="both", alpha=0.3)
    finish_robot_plot(path)


def plot_coverage_run_scatter(coverage: Any, runs: Any, path: Path) -> None:
    import matplotlib.pyplot as plt

    coverage = measured_rows(coverage, runs, keep_unknown_elapsed=False)
    df = coverage.merge(runs[["run_id", "robots", "seed", "status"]], on="run_id")
    run_cov = df.groupby(["run_id", "robots", "seed", "status"])["coverage"].mean().reset_index()
    if run_cov.empty:
        return
    ok = run_cov["status"] == "ok"
    plt.figure(figsize=(robot_plot_width(run_cov), 5))
    plt.scatter(run_cov.loc[ok, "robots"], run_cov.loc[ok, "coverage"], alpha=0.75, label="ok")
    if (~ok).any():
        plt.scatter(
            run_cov.loc[~ok, "robots"],
            run_cov.loc[~ok, "coverage"],
            marker="x",
            alpha=0.9,
            label="failed/timeout",
        )
        plt.legend()
    plt.ylim(0, 1)
    plt.xlabel("robots")
    plt.ylabel("run mean coverage")
    plt.title("Coverage for each run")
    plt.grid(True, axis="both", alpha=0.3)
    finish_robot_plot(path)


def property_coverage_dataframe(pd: Any, coverage: Any, runs: Any) -> Any:
    rows = []
    coverage = measured_rows(coverage, runs, keep_unknown_elapsed=False)
    df = coverage.merge(runs[["run_id", "robots", "seed"]], on="run_id")
    for property_name in ["CPred", "SPred", "VPred", "HPred"]:
        possible_col = f"{property_name}_possible"
        covered_col = f"{property_name}_covered"
        if possible_col not in df or covered_col not in df:
            continue
        possible = df[df[possible_col] == True]
        if possible.empty:
            continue
        grouped = possible.groupby(["run_id", "robots", "seed"])[covered_col].mean().reset_index()
        grouped["property"] = property_name
        grouped = grouped.rename(columns={covered_col: "coverage"})
        rows.extend(grouped[["run_id", "robots", "seed", "property", "coverage"]].to_dict("records"))
    return pd.DataFrame(rows)


def plot_property_coverage(coverage: Any, runs: Any, path: Path) -> None:
    import matplotlib.pyplot as plt
    import pandas as pd

    df = property_coverage_dataframe(pd, coverage, runs)
    if df.empty:
        return
    grouped = df.groupby(["robots", "property"])["coverage"].mean().unstack()
    grouped.plot(kind="line", marker="o", figsize=(robot_plot_width(df), 5))
    plt.ylim(0, 1)
    plt.xlabel("robots")
    plt.ylabel("coverage when property possible")
    plt.title("Per-property monitoring coverage")
    plt.grid(True, axis="both", alpha=0.3)
    finish_robot_plot(path)


def plot_possible_property_ticks(coverage: Any, runs: Any, path: Path) -> None:
    import matplotlib.pyplot as plt

    coverage = measured_rows(coverage, runs, keep_unknown_elapsed=False)
    df = coverage.merge(runs[["run_id", "robots"]], on="run_id")
    if df.empty:
        return
    run_possible = (
        df.groupby(["run_id", "robots"])["possible_property_ticks"].sum().reset_index()
    )
    run_possible.boxplot(
        column="possible_property_ticks",
        by="robots",
        figsize=(robot_plot_width(run_possible), 5),
    )
    plt.suptitle("")
    plt.ylabel("possible property ticks per run")
    plt.title("Monitoring opportunities by robot count")
    finish_robot_plot(path)


def plot_coverage_vs_checker_cpu(coverage: Any, runs: Any, summaries: Any, path: Path) -> None:
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.colors import LinearSegmentedColormap, Normalize

    if coverage.empty or summaries.empty:
        return
    coverage = measured_rows(coverage, runs, keep_unknown_elapsed=False)
    cov = coverage.merge(runs[["run_id", "robots", "seed"]], on="run_id")
    cov = cov.groupby("run_id")["coverage"].mean().reset_index()
    df = summaries.merge(cov, on="run_id", how="inner")
    df = df.dropna(subset=["coverage", "checker_cpu_time_secs"])
    if df.empty:
        return
    grouped = (
        df.groupby("robots")[["coverage", "checker_cpu_time_secs"]]
        .mean()
        .reset_index()
        .sort_values("checker_cpu_time_secs")
    )
    fit = ordinary_least_squares_line(
        df["checker_cpu_time_secs"],
        df["coverage"],
    )
    plt.figure(figsize=PAPER_SINGLE_COLUMN_SQUARE_FIGSIZE)
    robot_cmap = LinearSegmentedColormap.from_list(
        "robot_count_scale",
        ["#2c7fb8", "#41b6c4", "#7fcdbb", "#fdae61", "#b2182b"],
    )
    robot_norm = Normalize(vmin=df["robots"].min(), vmax=df["robots"].max())
    scatter = plt.scatter(
        df["checker_cpu_time_secs"],
        df["coverage"],
        c=df["robots"],
        cmap=robot_cmap,
        norm=robot_norm,
        alpha=0.45,
        s=8,
        edgecolors="none",
        label="run mean",
    )
    if not grouped.empty:
        plt.plot(
            grouped["checker_cpu_time_secs"],
            grouped["coverage"],
            color="black",
            marker="o",
            linewidth=0.8,
            markersize=2.0,
            label="mean by robot count",
        )
        y_low, y_high = tight_ylim(df["coverage"], upper_bound=1.005)
        plt.ylim(y_low, y_high)
        labeled_robot_counts = {
            int(grouped["robots"].min()),
            10,
            14,
            20,
            25,
            30,
            35,
            40,
            45,
            50,
            55,
            60,
            65,
            70,
            75,
            int(grouped["robots"].max()),
        }
        labeled = grouped[grouped["robots"].astype(int).isin(labeled_robot_counts)].reset_index(drop=True)
        axis = plt.gca()
        occupied_label_boxes = []
        candidate_offsets = [
            (0, 20),
            (0, -24),
            (22, 12),
            (-22, 12),
            (22, -16),
            (-22, -16),
            (34, 0),
            (-34, 0),
            (0, 34),
            (0, -38),
        ]

        def overlaps_existing_label(center_x: float, center_y: float, text: str) -> bool:
            half_width = max(16.0, len(text) * 4.8 + 8.0)
            half_height = 9.0
            left = center_x - half_width
            right = center_x + half_width
            bottom = center_y - half_height
            top = center_y + half_height
            for other_left, other_right, other_bottom, other_top in occupied_label_boxes:
                if left <= other_right and right >= other_left and bottom <= other_top and top >= other_bottom:
                    return True
            occupied_label_boxes.append((left, right, bottom, top))
            return False

        for index, row in labeled.iterrows():
            label_text = f"{int(row['robots'])}"
            base_x, base_y = axis.transData.transform(
                (
                    row["checker_cpu_time_secs"],
                    row["coverage"],
                )
            )
            x_offset, y_offset = candidate_offsets[index % len(candidate_offsets)]
            for candidate_x_offset, candidate_y_offset in candidate_offsets:
                if not overlaps_existing_label(
                    base_x + candidate_x_offset,
                    base_y + candidate_y_offset,
                    label_text,
                ):
                    x_offset, y_offset = candidate_x_offset, candidate_y_offset
                    break
            plt.annotate(
                label_text,
                (
                    row["checker_cpu_time_secs"],
                    row["coverage"],
                ),
                xytext=(0, y_offset),
                textcoords="offset points",
                ha="center",
                va="center",
                fontsize=6.2,
                fontweight="normal",
                color="black",
                bbox={
                    "boxstyle": "round,pad=0.18",
                    "facecolor": "white",
                    "alpha": 0.95,
                    "edgecolor": "0.25",
                    "linewidth": 0.25,
                },
                arrowprops={
                    "arrowstyle": "-",
                    "color": "0.25",
                    "linewidth": 0.35,
                    "alpha": 0.8,
                },
            )
    if fit is not None:
        intercept, slope = fit
        xs = np.linspace(
            df["checker_cpu_time_secs"].min(),
            df["checker_cpu_time_secs"].max(),
            100,
        )
        plt.plot(xs, intercept + slope * xs, color="tab:red", linestyle="--", linewidth=0.55, label="linear fit")
    plt.xlabel("total monitoring CPU time per run (s)")
    plt.ylabel("run mean coverage")
    if grouped.empty:
        y_low, y_high = tight_ylim(df["coverage"], upper_bound=1.005)
        plt.ylim(y_low, y_high)
    plt.title("Coverage versus total monitoring CPU cost")
    plt.grid(True, axis="both", alpha=0.3)
    plt.gca().set_box_aspect(1)
    plt.legend(fontsize=5, loc="lower left")
    colorbar = plt.colorbar(scatter, label="robots", fraction=0.035, pad=0.02, aspect=35)
    colorbar.ax.tick_params(labelsize=5, width=0.4, length=2)
    colorbar.set_label("robots", fontsize=6)
    finish_robot_plot(path)


def plot_checker_cpu_per_second(summaries: Any, path: Path) -> None:
    import matplotlib.pyplot as plt

    if summaries.empty or "checker_cpu_time_per_measured_sec" not in summaries:
        return
    df = summaries.dropna(subset=["checker_cpu_time_per_measured_sec"])
    if df.empty:
        return
    df.groupby("robots")["checker_cpu_time_per_measured_sec"].mean().plot(
        kind="bar",
        figsize=(robot_plot_width(df), 5),
    )
    plt.ylabel("monitoring CPU seconds / measured second")
    plt.title("Distributed monitoring CPU cost")
    finish_robot_plot(path)


def plot_scheduler_throughput(summaries: Any, path: Path) -> None:
    import matplotlib.pyplot as plt

    columns = [
        "scheduler_iterations_per_sec",
        "scheduler_plan_attempts_per_sec",
        "scheduler_successful_plans_per_sec",
        "scheduler_execute_events_per_sec",
    ]
    if summaries.empty or not all(column in summaries for column in columns):
        return
    df = summaries.dropna(subset=columns, how="all")
    if df.empty:
        return
    grouped = df.groupby("robots")[columns].mean().rename(
        columns={
            "scheduler_iterations_per_sec": "iterations/s",
            "scheduler_plan_attempts_per_sec": "plan attempts/s",
            "scheduler_successful_plans_per_sec": "successful plans/s",
            "scheduler_execute_events_per_sec": "execute events/s",
        }
    )
    grouped.plot(kind="line", marker="o", figsize=(robot_plot_width(df), 5))
    plt.xlabel("robots")
    plt.ylabel("events per measured second")
    plt.title("Scheduler throughput")
    plt.grid(True, axis="both", alpha=0.3)
    finish_robot_plot(path)


def plot_scheduler_normalized_cost(summaries: Any, path: Path) -> None:
    import matplotlib.pyplot as plt

    columns = [
        "scheduler_cpu_per_iteration",
        "scheduler_cpu_per_plan_attempt",
        "scheduler_cpu_per_successful_plan",
    ]
    if summaries.empty or not all(column in summaries for column in columns):
        return
    df = summaries.dropna(subset=columns, how="all")
    if df.empty:
        return
    grouped = df.groupby("robots")[columns].mean().rename(
        columns={
            "scheduler_cpu_per_iteration": "CPU s / iteration",
            "scheduler_cpu_per_plan_attempt": "CPU s / plan attempt",
            "scheduler_cpu_per_successful_plan": "CPU s / successful plan",
        }
    )
    grouped.plot(kind="line", marker="o", figsize=(robot_plot_width(df), 5))
    plt.xlabel("robots")
    plt.ylabel("scheduler CPU seconds per work unit")
    plt.title("Scheduler normalized CPU cost")
    plt.grid(True, axis="both", alpha=0.3)
    finish_robot_plot(path)


def plot_worker_monitoring_throughput(summaries: Any, path: Path) -> None:
    import matplotlib.pyplot as plt

    columns = [
        "worker_monitoring_steps_per_sec",
        "worker_expr_evaluators_per_sec",
        "worker_non_aux_expr_evaluators_per_sec",
    ]
    if summaries.empty or not all(column in summaries for column in columns):
        return
    df = summaries.dropna(subset=columns, how="all")
    if df.empty:
        return
    grouped = df.groupby("robots")[columns].mean().rename(
        columns={
            "worker_monitoring_steps_per_sec": "monitoring steps/s",
            "worker_expr_evaluators_per_sec": "expr evaluators/s",
            "worker_non_aux_expr_evaluators_per_sec": "non-aux expr evaluators/s",
        }
    )
    grouped.plot(kind="line", marker="o", figsize=(robot_plot_width(df), 5))
    plt.xlabel("robots")
    plt.ylabel("worker events per measured second")
    plt.title("Worker monitoring throughput")
    plt.grid(True, axis="both", alpha=0.3)
    finish_robot_plot(path)


def plot_worker_monitoring_load_balance(summaries: Any, path: Path) -> None:
    import matplotlib.pyplot as plt

    columns = [
        "worker_step_count_imbalance_ratio",
        "worker_monitoring_duration_imbalance_ratio",
    ]
    if summaries.empty or not all(column in summaries for column in columns):
        return
    df = summaries.dropna(subset=columns, how="all")
    if df.empty:
        return
    grouped = df.groupby("robots")[columns].mean().rename(
        columns={
            "worker_step_count_imbalance_ratio": "max/mean step count",
            "worker_monitoring_duration_imbalance_ratio": "max/mean monitoring duration",
        }
    )
    grouped.plot(kind="line", marker="o", figsize=(robot_plot_width(df), 5))
    plt.xlabel("robots")
    plt.ylabel("imbalance ratio")
    plt.title("Worker monitoring load balance")
    plt.grid(True, axis="both", alpha=0.3)
    finish_robot_plot(path)


def plot_worker_reconfiguration_load_balance(summaries: Any, path: Path) -> None:
    import matplotlib.pyplot as plt

    column = "worker_reconfiguration_imbalance_ratio"
    if summaries.empty or column not in summaries:
        return
    df = summaries.dropna(subset=[column])
    if df.empty:
        return
    df.groupby("robots")[column].mean().plot(kind="line", marker="o", figsize=(robot_plot_width(df), 5))
    plt.xlabel("robots")
    plt.ylabel("max/mean worker reconfiguration count")
    plt.title("Worker reconfiguration load balance")
    plt.grid(True, axis="both", alpha=0.3)
    finish_robot_plot(path)


def plot_pose_publish_backlog(summaries: Any, path: Path) -> None:
    import matplotlib.pyplot as plt

    columns = ["pose_publish_failure_rate", "pose_publish_failures_per_sec"]
    if summaries.empty or not all(column in summaries for column in columns):
        return
    df = summaries.dropna(subset=columns, how="all")
    if df.empty:
        return
    grouped = df.groupby("robots")[columns].mean().rename(
        columns={
            "pose_publish_failure_rate": "try_send failure rate",
            "pose_publish_failures_per_sec": "try_send failures/s",
        }
    )
    grouped.plot(kind="line", marker="o", figsize=(robot_plot_width(df), 5))
    plt.xlabel("robots")
    plt.ylabel("simulator-to-ROS queue pressure")
    plt.title("Pose publish backlog indicator")
    plt.grid(True, axis="both", alpha=0.3)
    finish_robot_plot(path)


def plot_time_to_reconfig(telemetry: Any, runs: Any, path: Path) -> None:
    import matplotlib.pyplot as plt
    import pandas as pd

    telemetry = measured_rows(telemetry, runs, keep_unknown_elapsed=False)
    rows = [
        {"run_id": run_id, "first_reconfig_elapsed_secs": first_reconfig_time(group)}
        for run_id, group in telemetry.groupby("run_id")
    ]
    df = pd.DataFrame(rows).merge(runs[["run_id", "robots"]], on="run_id")
    if df["first_reconfig_elapsed_secs"].notna().any():
        df.groupby("robots")["first_reconfig_elapsed_secs"].mean().plot(
            kind="bar",
            figsize=(robot_plot_width(df), 5),
        )
        plt.ylabel("seconds")
        finish_robot_plot(path)


def plot_worker_monitoring_cost(telemetry: Any, runs: Any, path: Path) -> None:
    import matplotlib.pyplot as plt
    import pandas as pd

    df = worker_monitoring_step_dataframe(pd, measured_rows(telemetry, runs, keep_unknown_elapsed=False))
    if df.empty:
        return
    df = df.merge(runs[["run_id", "robots"]], on="run_id", how="left")
    df = df.dropna(subset=["eval_expr_duration_ms"])
    if df.empty:
        return
    df.boxplot(
        column="eval_expr_duration_ms",
        by="robots",
        figsize=(robot_plot_width(df), 5),
    )
    plt.suptitle("")
    plt.title("Worker monitor expression evaluation cost")
    plt.ylabel("per-node expression evaluation duration (ms)")
    finish_robot_plot(path)


def plot_worker_monitoring_total(telemetry: Any, runs: Any, path: Path) -> None:
    import matplotlib.pyplot as plt
    import pandas as pd

    df = worker_monitoring_step_dataframe(pd, measured_rows(telemetry, runs, keep_unknown_elapsed=False))
    if df.empty:
        return
    df = df.merge(runs[["run_id", "robots"]], on="run_id", how="left")
    df = df.dropna(subset=["eval_expr_duration_ms"])
    if df.empty:
        return
    per_run = df.groupby(["run_id", "robots"])["eval_expr_duration_ms"].sum().reset_index()
    per_run.boxplot(
        column="eval_expr_duration_ms",
        by="robots",
        figsize=(robot_plot_width(per_run), 5),
    )
    plt.suptitle("")
    plt.title("Total worker monitor expression evaluation cost per run")
    plt.ylabel("total worker expression evaluation duration per run (ms)")
    finish_robot_plot(path)


def plot_constraint_monitoring_cost(telemetry: Any, runs: Any, path: Path) -> None:
    import matplotlib.pyplot as plt
    import pandas as pd

    df = constraint_monitoring_dataframe(pd, measured_rows(telemetry, runs, keep_unknown_elapsed=False))
    if df.empty:
        return
    df = df.merge(runs[["run_id", "robots"]], on="run_id", how="left")
    df = df.dropna(subset=["duration_ms"])
    if df.empty:
        return
    df.boxplot(
        column="duration_ms",
        by="robots",
        figsize=(robot_plot_width(df), 5),
    )
    plt.suptitle("")
    plt.title("Per-event distributed constraint monitoring latency")
    plt.ylabel("per-event constraint monitoring duration (ms)")
    finish_robot_plot(path)


def plot_constraint_monitoring_total(telemetry: Any, runs: Any, path: Path) -> None:
    import matplotlib.pyplot as plt
    import pandas as pd

    df = constraint_monitoring_dataframe(pd, measured_rows(telemetry, runs, keep_unknown_elapsed=False))
    if df.empty:
        return
    df = df.merge(runs[["run_id", "robots"]], on="run_id", how="left")
    df = df.dropna(subset=["duration_ms"])
    if df.empty:
        return
    per_run = df.groupby(["run_id", "robots"])["duration_ms"].sum().reset_index()
    per_run.boxplot(column="duration_ms", by="robots", figsize=(robot_plot_width(per_run), 5))
    plt.suptitle("")
    plt.title("Total distributed constraint monitoring latency per run")
    plt.ylabel("total constraint monitoring duration per run (ms)")
    finish_robot_plot(path)


def plot_failure_rate(runs: Any, path: Path) -> None:
    import matplotlib.pyplot as plt

    rates = runs.assign(failed=runs["status"].isin(["failed", "timeout", "error"]))
    rates.groupby("robots")["failed"].mean().plot(kind="bar", figsize=(robot_plot_width(rates), 5))
    plt.ylim(0, 1)
    plt.ylabel("failure/timeout rate")
    finish_robot_plot(path)


if __name__ == "__main__":
    raise SystemExit(main())
