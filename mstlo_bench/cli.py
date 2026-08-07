from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .benchmark import ROOT, run
from .report import write_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mstlo-bench")
    commands = parser.add_subparsers(dest="command", required=True)

    benchmark = commands.add_parser("benchmark", help="run the latency sweep")
    benchmark.add_argument(
        "--config", type=Path, default=ROOT / "configs" / "benchmark.toml"
    )
    benchmark.add_argument(
        "--output-dir", type=Path, default=ROOT / "results" / "benchmark"
    )

    report = commands.add_parser("report", help="generate the latency report")
    report.add_argument(
        "--output-dir", type=Path, default=ROOT / "results" / "benchmark"
    )
    report.add_argument("--report-dir", type=Path)

    args = parser.parse_args(argv)
    try:
        if args.command == "benchmark":
            rows = run(args.config.resolve(), args.output_dir.resolve())
            return 0 if all(row["ok"] for row in rows) else 1
        outputs = write_report(args.output_dir.resolve(), args.report_dir)
        for path in outputs:
            print(path)
        return 0
    except (OSError, RuntimeError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
