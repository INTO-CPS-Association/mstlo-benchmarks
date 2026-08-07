from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Protocol, TypeVar, cast

from tqdm import tqdm

PROGRESS_PHASES = ("settle", "warmup", "measure", "analysing", "finished", "failed")
PROGRESS_PHASE_WIDTH = max(len(phase.capitalize()) for phase in PROGRESS_PHASES)
PROGRESS_BAR_MIN_WIDTH = 8

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
    return f"{label:<{width}}" if width is not None else label


def progress_status(
    phase: str, elapsed: float, total: float, seconds_width: int
) -> str:
    label = phase.capitalize()
    return (
        f"{label:<{PROGRESS_PHASE_WIDTH}} "
        f"{min(elapsed, total):>{seconds_width}.1f}/{total:>{seconds_width}.1f}s"
    )


def progress_line_width(
    label_width: int,
    seconds_width: int,
    terminal_width: int | None = None,
) -> int:
    status_width = PROGRESS_PHASE_WIDTH + 2 * seconds_width + 3
    side_width = label_width + status_width + 12
    return max(terminal_width or 0, side_width + PROGRESS_BAR_MIN_WIDTH)


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
    label = format_progress_label(
        benchmark_index, total_benchmarks, point, width=label_width
    )
    resolved_label_width = label_width or len(label)
    resolved_seconds_width = seconds_width or len(f"{expected:.1f}")
    resolved_line_width = line_width or progress_line_width(
        resolved_label_width, resolved_seconds_width
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
        ncols=resolved_line_width,
        dynamic_ncols=False,
        leave=True,
        bar_format="{desc}: {bar}| {percentage:3.0f}% [ {raw_postfix} ]",
    ) as progress:
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
            progress.refresh()
            time.sleep(0.1)

        worker.join()
        elapsed = time.monotonic() - started
        progress.update(max(0.0, min(elapsed, expected) - progress.n))
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
