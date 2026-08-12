import csv
import json
import math

import pytest
from mstlo_bench.report import _series_values, aggregate, series_coverage, write_report


def row(transport, seed, semantics, p50, p95, p99):
    return {
        "robots": 10,
        "seed": seed,
        "property_set": "dwell",
        "transport": transport,
        "semantics": semantics,
        "algorithm": "incremental",
        "ok": True,
        "latency_samples": 20,
        "latency_overhead_ms_p50": p50,
        "latency_overhead_ms_p95": p95,
        "latency_overhead_ms_p99": p99,
        "result_latency_ms_p50": p50,
        "result_latency_ms_p95": p95,
        "result_latency_ms_p99": p99,
    }


def test_report_averages_seeds_and_separates_semantics(tmp_path):
    rows = [
        row("direct", 1, "delayed-qualitative", 1, 2, 3),
        row("direct", 2, "delayed-qualitative", 3, 4, 5),
        row("ros", 1, "robustness-interval", 5, 6, 7),
    ]
    (tmp_path / "results.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in rows), encoding="utf-8"
    )
    summary = aggregate(rows)
    delayed = next(row for row in summary if row["semantics"] == "delayed-qualitative")
    assert delayed["latency_overhead_ms_p95_mean"] == 3
    outputs = write_report(tmp_path)
    assert {path.name for path in outputs} == {
        "latency.csv",
        "latency.md",
        "latency_overhead_fan_delayed-qualitative.png",
        "latency_overhead_fan_robustness-interval.png",
    }


def test_report_marks_missing_and_partial_series(tmp_path):
    (tmp_path / "config.toml").write_text(
        """
[benchmark]
robots = [10, 100]
seeds = [1, 2]
property_sets = ["dwell"]
transports = ["direct", "ros"]
semantics = ["delayed-qualitative", "robustness-interval"]
""",
        encoding="utf-8",
    )
    failed = row("direct", 2, "delayed-qualitative", 0, 0, 0)
    failed["ok"] = False
    failed["latency_samples"] = 0
    rows = [row("direct", 1, "delayed-qualitative", 1, 2, 3), failed]
    (tmp_path / "results.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in rows), encoding="utf-8"
    )

    plan = {
        "robots": [10, 100],
        "seeds": [1, 2],
        "property_sets": ["dwell"],
        "transports": ["direct", "ros"],
        "semantics": ["delayed-qualitative", "robustness-interval"],
    }
    summary = aggregate(rows)
    for item in summary:
        item["expected_runs"] = 2
        item["complete"] = item["runs"] == 2
    statuses = series_coverage(rows, summary, plan)
    direct = next(
        item
        for item in statuses
        if item["semantics"] == "delayed-qualitative" and item["transport"] == "direct"
    )
    ros = next(
        item
        for item in statuses
        if item["semantics"] == "delayed-qualitative" and item["transport"] == "ros"
    )
    assert direct["status"] == "partial"
    assert direct["complete_robot_counts"] == 0
    assert direct["planned_robot_counts"] == 2
    assert ros["status"] == "not run"
    assert ros["complete_robot_counts"] == 0

    outputs = write_report(tmp_path)
    assert "latency_overhead_fan_robustness-interval.png" in {
        path.name for path in outputs
    }
    markdown = (tmp_path / "report" / "latency.md").read_text(encoding="utf-8")
    assert "| delayed-qualitative | dwell | ros | not run | 0 | 2 |" in markdown
    assert "| robustness-interval | dwell | direct | not run | 0 | 2 |" in markdown
    with (tmp_path / "report" / "latency.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        result = next(csv.DictReader(handle))
    assert result["runs"] == "1"
    assert result["expected_runs"] == "2"
    assert result["complete"] == "False"


def test_report_aggregates_dual_metric_rows():
    item = row("direct", 1, "eager-qualitative", 0, 2, 4)
    item.update(
        {
            "result_latency_ms_p50": 10_000,
            "result_latency_ms_p95": 10_002,
            "result_latency_ms_p99": 10_004,
        }
    )
    summary = aggregate([item])
    assert summary[0]["latency_overhead_ms_p95_mean"] == 2
    assert summary[0]["result_latency_ms_p95_mean"] == 10_002


def test_report_rejects_missing_metrics():
    item = row("direct", 1, "eager-qualitative", 0, 2, 4)
    del item["result_latency_ms_p95"]
    with pytest.raises(KeyError, match="result_latency_ms_p95"):
        aggregate([item])


def test_series_values_leave_gaps_for_incomplete_robot_counts():
    points = {
        10: {"p95": 2.0},
        500: {"p95": 9.0},
    }
    values = _series_values(points, [10, 100, 500], "p95")
    assert values[0] == 2.0
    assert math.isnan(values[1])
    assert values[2] == 9.0
