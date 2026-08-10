from __future__ import annotations

import os
import shutil
import sys
import threading
import time
from collections.abc import Callable
from typing import Protocol, TypeVar, cast

from tqdm import tqdm

PROGRESS_PHASES = ("settle", "warmup", "measure", "analysing", "finished", "failed")
PROGRESS_PHASE_WIDTH = max(len(phase.capitalize()) for phase in PROGRESS_PHASES)
PROGRESS_BAR_MIN_WIDTH = 8
# Literal characters PROGRESS_BAR_FORMAT adds around the label, bar, and status.
PROGRESS_DECORATION_WIDTH = len(": | 100% [  ]")
PROGRESS_MIN_LINE_WIDTH = PROGRESS_DECORATION_WIDTH + PROGRESS_BAR_MIN_WIDTH
PROGRESS_BAR_FORMAT = "{desc}: {bar}| {percentage:3.0f}% [ {raw_postfix} ]"
PROGRESS_ERASE_LINE = "\x1b[2K"

T = TypeVar("T")


class ProgressPoint(Protocol):
    robots: int
    seed: int
    property_set: str
    transport: str
    semantics: str


def format_progress_label(
    benchmark_index: int,
    total_benchmarks: int,
    point: ProgressPoint,
    width: int | None = None,
) -> str:
    index_width = len(str(total_benchmarks))
    transport = {"direct": "D", "ros": "R"}.get(point.transport, point.transport)
    property_set = {
        "confined": "C",
        "dwell": "D",
        "occupancy": "O",
    }.get(point.property_set, point.property_set)
    semantics = {
        "delayed-qualitative": "DQual",
        "delayed-quantitative": "DQuant",
        "eager-qualitative": "EQual",
        "robustness-interval": "RoSI",
    }.get(point.semantics, point.semantics)
    label = (
        f"[{benchmark_index:>{index_width}}/{total_benchmarks}] "
        f"r={point.robots} s={point.seed} {property_set}/{semantics}/{transport}"
    )
    if width is None:
        return label
    return f"{label[:width]:<{width}}"


def progress_status(
    phase: str, elapsed: float, total: float, seconds_width: int
) -> str:
    label = phase.capitalize()
    return (
        f"{label:<{PROGRESS_PHASE_WIDTH}} "
        f"{min(elapsed, total):>{seconds_width}.1f}/{total:>{seconds_width}.1f}s"
    )


def progress_status_width(seconds_width: int) -> int:
    return PROGRESS_PHASE_WIDTH + 2 * seconds_width + 3


def progress_terminal_width(fallback: int = 80) -> int:
    """Columns available on the stream the progress bar renders to.

    tqdm writes to stderr, so the width has to come from stderr: with stdout
    redirected to a log, `shutil.get_terminal_size` reports the fallback width
    while the bar still renders into the real terminal.
    """
    try:
        return os.get_terminal_size(sys.stderr.fileno()).columns
    except (AttributeError, OSError, ValueError):
        return shutil.get_terminal_size(fallback=(fallback, 20)).columns


def progress_line_width(
    label_width: int,
    seconds_width: int,
    terminal_width: int | None = None,
) -> int:
    """Total width of one progress line, always inside the terminal.

    A line as wide as the terminal wraps onto a second row, after which the
    carriage return only rewrites that last row and every refresh leaves
    another row of scrollback behind. Reserving the final column keeps the
    whole display on one line.
    """
    natural_width = (
        label_width
        + progress_status_width(seconds_width)
        + PROGRESS_DECORATION_WIDTH
        + PROGRESS_BAR_MIN_WIDTH
    )
    if not terminal_width:
        return natural_width
    return max(terminal_width - 1, PROGRESS_MIN_LINE_WIDTH)


def progress_label_width(label_width: int, seconds_width: int, line_width: int) -> int:
    """Label width that leaves room for the bar, status, and decorations.

    Labels are truncated rather than allowed to push the line past the
    terminal, so a narrow window loses the end of the label instead of the
    single-line display.
    """
    budget = (
        line_width
        - progress_status_width(seconds_width)
        - PROGRESS_DECORATION_WIDTH
        - PROGRESS_BAR_MIN_WIDTH
    )
    return max(min(label_width, budget), 0)


def progress_layout(
    label_width: int, seconds_width: int, line_width: int | None = None
) -> tuple[int, int]:
    """Label and line widths for the terminal's current size.

    Recomputed on every refresh so the display follows a resize. An explicit
    `line_width` pins the layout instead of measuring the terminal.
    """
    resolved = line_width or progress_line_width(
        label_width, seconds_width, progress_terminal_width()
    )
    return progress_label_width(label_width, seconds_width, resolved), resolved


def erase_line_printer(progress: tqdm) -> None:
    """Erase the row rather than padding it out to the previous width.

    tqdm pads a line that has become shorter with trailing spaces up to its
    previous length. When the terminal has just been made narrower that write
    overruns the new width and wraps, leaving a row behind for every resize.
    Erasing the row instead costs no columns. Streams that are not terminals
    keep tqdm's padding so redirected logs stay free of escape sequences.
    """
    stream = progress.fp
    if not getattr(stream, "isatty", lambda: False)():
        return
    flush = getattr(stream, "flush", lambda: None)

    def print_status(status: str) -> None:
        stream.write(f"\r{PROGRESS_ERASE_LINE}{status}")
        flush()

    progress.sp = print_status


def expected_progress_seconds(
    point: ProgressPoint,
    duration_s: float,
    settle_s: float,
    warmup_s: float,
    drain_s: float,
) -> float:
    if point.transport != "ros":
        return max(1.0, duration_s)
    return max(1.0, settle_s + warmup_s + duration_s + drain_s)


def run_with_progress(
    point: ProgressPoint,
    benchmark_index: int,
    total_benchmarks: int,
    *,
    duration_s: float,
    settle_s: float,
    warmup_s: float,
    drain_s: float,
    runner: Callable[[], T],
    label_width: int | None = None,
    seconds_width: int | None = None,
    line_width: int | None = None,
) -> T:
    ros = point.transport == "ros"
    settle = settle_s if ros else 0.0
    warmup = warmup_s if ros else 0.0
    expected = expected_progress_seconds(point, duration_s, settle_s, warmup_s, drain_s)
    natural_label_width = label_width or len(
        format_progress_label(benchmark_index, total_benchmarks, point)
    )
    resolved_seconds_width = seconds_width or len(f"{expected:.1f}")
    layout = progress_layout(natural_label_width, resolved_seconds_width, line_width)
    label = format_progress_label(
        benchmark_index, total_benchmarks, point, width=layout[0]
    )
    result: list[T] = []
    error: list[BaseException] = []

    def invoke() -> None:
        try:
            result.append(runner())
        except BaseException as exc:
            error.append(exc)

    worker = threading.Thread(target=invoke, name="benchmark-runner")
    worker.start()

    class BenchmarkTqdm(tqdm):
        @property
        def format_dict(self) -> dict[str, object]:
            values = super().format_dict
            values["raw_postfix"] = self.postfix or ""
            return values

    started = time.monotonic()
    with BenchmarkTqdm(
        total=expected,
        desc=label,
        unit="s",
        ncols=layout[1],
        dynamic_ncols=False,
        leave=True,
        bar_format=PROGRESS_BAR_FORMAT,
    ) as progress:
        erase_line_printer(progress)

        def relayout() -> None:
            """Follow a terminal resize before the next refresh."""
            nonlocal layout
            current = progress_layout(
                natural_label_width, resolved_seconds_width, line_width
            )
            if current == layout:
                return
            layout = current
            progress.ncols = current[1]
            progress.set_description_str(
                format_progress_label(
                    benchmark_index, total_benchmarks, point, width=current[0]
                ),
                refresh=False,
            )

        while worker.is_alive():
            elapsed = time.monotonic() - started
            progress.update(max(0.0, min(elapsed, expected) - progress.n))
            if elapsed < settle:
                phase = "settle"
            elif elapsed < settle + warmup:
                phase = "warmup"
            elif elapsed < settle + warmup + duration_s:
                phase = "measure"
            else:
                phase = "analysing"
            progress.postfix = progress_status(
                phase, elapsed, expected, resolved_seconds_width
            )
            relayout()
            progress.refresh()
            time.sleep(0.1)

        worker.join()
        elapsed = time.monotonic() - started
        progress.update(max(0.0, min(elapsed, expected) - progress.n))
        relayout()
        progress.postfix = progress_status(
            "failed" if error else "finished",
            elapsed,
            expected,
            resolved_seconds_width,
        )
        progress.refresh()

    if error:
        raise error[0]
    return cast(T, result[0])
