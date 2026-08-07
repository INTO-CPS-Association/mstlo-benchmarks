import time

from mstlo_bench.benchmark import Point
from mstlo_bench import progress as progress_module
from mstlo_bench.progress import (
    PROGRESS_BAR_FORMAT,
    PROGRESS_BAR_MIN_WIDTH,
    PROGRESS_DECORATION_WIDTH,
    PROGRESS_ERASE_LINE,
    PROGRESS_PHASE_WIDTH,
    erase_line_printer,
    expected_progress_seconds,
    format_progress_label,
    progress_label_width,
    progress_layout,
    progress_line_width,
    progress_status,
    progress_status_width,
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
    status_width = progress_status_width(4)
    assert status_width == PROGRESS_PHASE_WIDTH + 2 * 4 + 3
    natural = progress_line_width(40, 4)
    assert natural - 40 - status_width - PROGRESS_DECORATION_WIDTH == PROGRESS_BAR_MIN_WIDTH


def test_progress_decoration_matches_the_bar_format():
    rendered = PROGRESS_BAR_FORMAT.format(
        desc="", bar="", percentage=100.0, raw_postfix=""
    )
    assert len(rendered) == PROGRESS_DECORATION_WIDTH


def test_progress_line_stays_inside_the_terminal():
    short = Point(1, 1, "dwell", "direct", "eager-qualitative")
    long = Point(1000, 1009, "occupancy", "ros", "delayed-quantitative")
    overnight_width = max(
        len(format_progress_label(1, 1200, short)),
        len(format_progress_label(1200, 1200, long)),
    )
    for terminal_width in (200, 120, 100, 80, 60, 40):
        line_width = progress_line_width(
            overnight_width, 4, terminal_width=terminal_width
        )
        label_width = progress_label_width(overnight_width, 4, line_width)
        fixed_width = label_width + progress_status_width(4) + PROGRESS_DECORATION_WIDTH
        # The line never reaches the final column, and the bar always has room.
        assert line_width < terminal_width
        assert fixed_width <= line_width
        assert len(format_progress_label(1200, 1200, long, label_width)) == label_width
        # Below 60 columns the bar is squeezed past its minimum to keep the fit.
        if terminal_width >= 60:
            assert line_width - fixed_width >= PROGRESS_BAR_MIN_WIDTH


def test_progress_layout_follows_a_resize(monkeypatch):
    widths = iter([120, 70, 160])
    monkeypatch.setattr(progress_module, "progress_terminal_width", lambda: next(widths))
    assert progress_layout(36, 4)[1] == 119
    assert progress_layout(36, 4)[1] == 69
    assert progress_layout(36, 4)[1] == 159

    # An explicit line width pins the layout instead of measuring the terminal.
    assert progress_layout(36, 4, line_width=80)[1] == 80


def test_erase_line_printer_only_touches_terminals():
    class Stream:
        def __init__(self, tty):
            self.tty = tty
            self.written = []

        def isatty(self):
            return self.tty

        def write(self, text):
            self.written.append(text)

        def flush(self):
            pass

    class FakeProgress:
        def __init__(self, stream):
            self.fp = stream
            self.sp = lambda status: stream.write(f"padded:{status}")

    terminal = Stream(tty=True)
    progress = FakeProgress(terminal)
    erase_line_printer(progress)
    progress.sp("bar")
    assert terminal.written == [f"\r{PROGRESS_ERASE_LINE}bar"]

    log = Stream(tty=False)
    redirected = FakeProgress(log)
    erase_line_printer(redirected)
    redirected.sp("bar")
    assert log.written == ["padded:bar"]


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
