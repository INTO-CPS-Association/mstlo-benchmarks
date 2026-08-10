"""Where a run's files go.  The same answer for all three benchmarks.

    results.py new <benchmark> <config>                    # allocate one
    results.py latest <benchmark> [--stage S] [--config C] # find the newest

The layout is

    $RESULTS_ROOT/<benchmark>/<config>-<UTC timestamp>-<id>/
    $RESULTS_ROOT/<benchmark>/latest -> the newest of them

Every measuring stage -- `gather`, `run` -- gets a directory of its own, so one
set of measurements is never mixed into another and nothing is overwritten by a
re-run.  The stages that only read -- `analyze` -- are pointed at the newest
directory holding what they need, which is why they ask by stage: `analyze`
wants the newest `run`, and the incubator's `run` wants the newest `gather`.
Which stages a directory holds is recorded in its metadata.json.

$RESULTS_DIR overrides all of this, for both kinds of stage.
"""

import argparse
import json
import os
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

LATEST = "latest"


def root() -> Path:
    """The directory the results of every benchmark live under."""
    default = Path(__file__).resolve().parent.parent / "results"
    return Path(os.environ.get("RESULTS_ROOT") or default)


def timestamp(moment: datetime) -> str:
    return moment.strftime("%Y%m%dT%H%M%SZ")


def identifier(moment: datetime) -> str:
    """An id that also orders two runs made within the same second.

    A readable timestamp only resolves to the second, so the id carries the
    microsecond within it, zero-padded to keep string order numeric.  The random
    tail is what keeps two runs made in the same microsecond apart -- the name
    has to be unique, and mtimes are too coarse on some filesystems to order
    anything.
    """
    return f"{moment.microsecond:06d}{random.randbytes(1).hex()}"


def slug(name: str) -> str:
    cleaned = "".join(c if c.isalnum() or c in "-_" else "-" for c in name).strip("-")
    return cleaned or "run"


def stages(directory: Path) -> list[str]:
    """The stages that have written to a result directory, oldest first."""
    try:
        with (directory / "metadata.json").open() as f:
            meta = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    return [record.get("stage") for record in meta.get("stages", [])]


def new(benchmark: str, config: str) -> Path:
    """Create and return a fresh result directory for a measuring stage."""
    parent = root() / benchmark
    parent.mkdir(parents=True, exist_ok=True)
    stamp = timestamp(datetime.now(timezone.utc))
    for _ in range(10):
        moment = datetime.now(timezone.utc)
        candidate = parent / f"{slug(config)}-{stamp}-{identifier(moment)}"
        try:
            candidate.mkdir()
        except FileExistsError:
            continue
        point_latest_at(candidate)
        return candidate
    raise SystemExit(f"could not allocate a result directory under {parent}")


def point_latest_at(directory: Path) -> None:
    """Move the benchmark's `latest` symlink onto a directory.

    A convenience for people, never for the stages themselves, so a filesystem
    that cannot do symlinks -- a bind mount on Windows, say -- costs nothing.
    """
    link = directory.parent / LATEST
    try:
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(directory.name, target_is_directory=True)
    except OSError:
        pass


def age_key(directory: Path) -> tuple[str, str]:
    """Sort key putting the newest directory last.

    Age is read from the name, never from an mtime: a copy, a bind mount or a
    stage writing another file into an older directory all rewrite mtimes, and
    none of them make a run newer.  The config prefix is dropped so that runs
    sort by when they were made rather than by what they were made with.
    """
    parts = directory.name.rsplit("-", 2)
    return (parts[1], parts[2]) if len(parts) == 3 else ("", "")


def candidates(benchmark: str) -> list[Path]:
    """Every result directory of a benchmark, newest first."""
    parent = root() / benchmark
    if not parent.is_dir():
        return []
    found = [
        entry
        for entry in parent.iterdir()
        if entry.is_dir() and entry.name != LATEST and not entry.is_symlink()
    ]
    return sorted(found, key=age_key, reverse=True)


def resolve(benchmark: str, target: str) -> Path:
    """The directory a stage was pointed at by name or by path.

    A bare name is looked up under the benchmark's own results, so the short
    name printed when a run started is the name to type to come back to it.
    `latest` is one of those names, and resolves to what it points at.
    """
    candidate = Path(target)
    if not candidate.is_absolute() and "/" not in target:
        candidate = root() / benchmark / target
    if candidate.is_dir():
        return candidate.resolve()
    raise SystemExit(f"no result directory {target} under {root() / benchmark}")


def latest(benchmark: str, stage: str | None = None, config: str | None = None) -> Path:
    for directory in candidates(benchmark):
        if config and not directory.name.startswith(f"{slug(config)}-"):
            continue
        if stage and stage not in stages(directory):
            continue
        return directory

    wanted = f"no {stage + ' ' if stage else ''}results for {benchmark}"
    if config:
        wanted += f" with the {config} config"
    raise SystemExit(
        f"{wanted} under {root() / benchmark} -- "
        f"run it first, or set RESULTS_DIR to the directory to use"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    allocate = commands.add_parser("new", help="allocate a fresh result directory")
    allocate.add_argument("benchmark")
    allocate.add_argument("config")

    newest = commands.add_parser("latest", help="print the newest result directory")
    newest.add_argument("benchmark")
    newest.add_argument("--stage", help="only directories this stage wrote to")
    newest.add_argument("--config", help="only directories made with this config")

    named = commands.add_parser("resolve", help="print the named result directory")
    named.add_argument("benchmark")
    named.add_argument("target", help="a directory name under the benchmark, or a path")

    args = parser.parse_args()
    if args.command == "new":
        print(new(args.benchmark, args.config))
    elif args.command == "resolve":
        print(resolve(args.benchmark, args.target))
    else:
        print(latest(args.benchmark, args.stage, args.config))


if __name__ == "__main__":
    sys.exit(main())
