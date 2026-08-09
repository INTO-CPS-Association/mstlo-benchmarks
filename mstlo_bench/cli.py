from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from .benchmark import ROOT, fresh_result_directory, run
from .report import write_report

RESULTS_ROOT = Path(os.environ.get("MSTLO_BENCH_RESULTS_ROOT", ROOT / "results"))
SUITES = ("quick", "small", "paper", "overnight")
TESTS_ROOT = Path(os.environ.get("MSTLO_BENCH_TESTS_DIR", ROOT / "tests"))


def run_and_report(
    config_path: Path,
    *,
    output_dir: Path | None = None,
    results_root: Path | None = None,
    suite_name: str | None = None,
    report_dir: Path | None = None,
    resume: bool = False,
) -> int:
    """Run a suite, write its report even for point failures, and return its status."""
    config_path = config_path.resolve()
    if output_dir is None:
        output_dir = fresh_result_directory(
            (results_root or RESULTS_ROOT).resolve(), suite_name or config_path.stem
        )
    else:
        output_dir = output_dir.resolve()
    print(f"Selected result directory: {output_dir}", flush=True)

    rows: list[dict[str, Any]] = []
    benchmark_error: Exception | None = None
    try:
        rows = run(config_path, output_dir, resume=resume)
    except Exception as error:
        benchmark_error = error

    outputs: list[Path] = []
    if (output_dir / "config.toml").exists() or (output_dir / "results.jsonl").exists():
        outputs = write_report(output_dir, report_dir.resolve() if report_dir else None)
        for path in outputs:
            print(path)

    print(f"Completed result directory: {output_dir}", flush=True)
    if benchmark_error is not None:
        raise benchmark_error
    return 0 if rows and all(row.get("ok") for row in rows) else 1


def _add_resume_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--resume",
        "--append",
        action="store_true",
        dest="resume",
        help="explicitly append/retry in an existing result directory",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mstlo-bench")
    commands = parser.add_subparsers(dest="command", required=True)

    benchmark = commands.add_parser("benchmark", help="run the latency sweep")
    benchmark.add_argument(
        "--config", type=Path, default=ROOT / "configs" / "benchmark.toml"
    )
    benchmark.add_argument(
        "--output-dir", type=Path, default=RESULTS_ROOT / "benchmark"
    )
    _add_resume_argument(benchmark)

    report = commands.add_parser("report", help="generate the latency report")
    report.add_argument("--output-dir", type=Path, default=RESULTS_ROOT / "benchmark")
    report.add_argument("--report-dir", type=Path)

    for suite in SUITES:
        suite_parser = commands.add_parser(
            suite, help=f"run configs/{suite}.toml and generate its report"
        )
        suite_parser.add_argument("--output-dir", type=Path)
        suite_parser.add_argument("--results-root", type=Path, default=RESULTS_ROOT)
        suite_parser.add_argument("--report-dir", type=Path)
        _add_resume_argument(suite_parser)

    test = commands.add_parser("test", help="run the Python unit tests in the image")
    test.add_argument("pytest_args", nargs=argparse.REMAINDER)
    return parser


def _run_tests(arguments: list[str]) -> int:
    command = [sys.executable, "-m", "pytest", str(TESTS_ROOT), *arguments]
    return subprocess.run(command, check=False).returncode


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "benchmark":
            rows = run(
                args.config.resolve(), args.output_dir.resolve(), resume=args.resume
            )
            return 0 if rows and all(row["ok"] for row in rows) else 1
        if args.command == "report":
            outputs = write_report(args.output_dir.resolve(), args.report_dir)
            for path in outputs:
                print(path)
            return 0
        if args.command == "test":
            return _run_tests(args.pytest_args)

        config_path = ROOT / "configs" / f"{args.command}.toml"
        return run_and_report(
            config_path,
            output_dir=args.output_dir,
            results_root=args.results_root,
            suite_name=args.command,
            report_dir=args.report_dir,
            resume=args.resume,
        )
    except (OSError, RuntimeError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
