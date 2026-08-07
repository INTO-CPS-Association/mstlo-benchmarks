import time

from mstlo_bench.benchmark import Point
from mstlo_bench.progress import (
    PROGRESS_BAR_MIN_WIDTH,
    PROGRESS_PHASE_WIDTH,
    expected_progress_seconds,
    format_progress_label,
    progress_line_width,
    progress_status,
    run_with_progress,
)


def test_progress_layout_is_fixed_across_points():
    short = Point(1, 1, "dwell", "direct", "eager-qualitative")
    long = Point(1000, 1009, "occupancy", "ros", "delayed-quantitative")
    width = max(
        len(format_progress_label(1, 2, short)),
        len(format_progress_label(2, 2, long)),
    )
    assert len(format_progress_label(1, 2, short, width)) == width
    assert len(format_progress_label(2, 2, long, width)) == width

    statuses = [
        progress_status(phase, 1.2, 19.0, 4)
        for phase in ("settle", "warmup", "measure", "analysing", "finished", "failed")
    ]
    assert len({len(status) for status in statuses}) == 1
    assert PROGRESS_PHASE_WIDTH == len("Analysing")
    status_width = PROGRESS_PHASE_WIDTH + 2 * 4 + 3
    assert progress_line_width(40, 4) - 40 - status_width - 12 == PROGRESS_BAR_MIN_WIDTH

    overnight_width = max(
        len(format_progress_label(1, 1200, short)),
        len(format_progress_label(1200, 1200, long)),
    )
    assert progress_line_width(overnight_width, 4, terminal_width=80) == 80


def test_progress_timing_and_runner():
    direct = Point(1, 1, "confined", "direct", "delayed-qualitative")
    ros = Point(1, 1, "confined", "ros", "delayed-qualitative")
    assert expected_progress_seconds(direct, 14, 2, 2, 1) == 14
    assert expected_progress_seconds(ros, 14, 2, 2, 1) == 19

    result = run_with_progress(
        direct,
        1,
        1,
        duration_s=0.01,
        settle_s=0,
        warmup_s=0,
        drain_s=0,
        runner=lambda: (time.sleep(0.01), "done")[1],
        line_width=80,
    )
    assert result == "done"
