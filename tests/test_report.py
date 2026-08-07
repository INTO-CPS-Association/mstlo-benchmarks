import json

from mstlo_bench.report import aggregate, write_report


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
