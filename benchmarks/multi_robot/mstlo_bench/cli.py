"""The tool the multi-robot stage scripts drive.

Which directory to write to, what to record about the machine, and when to
allocate a new one are decided by ``benchmarks/entrypoint.sh`` for all three
benchmarks alike, so both commands here take the directory they are given.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from .benchmark import ROOT, run
from .report import write_report

TESTS_ROOT = Path(os.environ.get("MSTLO_BENCH_TESTS_DIR", ROOT / "tests"))


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
        "--config", type=Path, default=ROOT / "configs" / "default.toml"
    )
    benchmark.add_argument("--output-dir", type=Path, required=True)
    _add_resume_argument(benchmark)

    report = commands.add_parser("report", help="generate the latency report")
    report.add_argument("--output-dir", type=Path, required=True)
    report.add_argument("--report-dir", type=Path)

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
        return _run_tests(args.pytest_args)
    except (OSError, RuntimeError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
