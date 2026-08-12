from __future__ import annotations

import csv
import tomllib
from collections import defaultdict
from itertools import product
from pathlib import Path
from statistics import fmean
from typing import Any

from .collect import read_results

PERCENTILES = ("p50", "p95", "p99")
TRANSPORTS = ("direct", "ros")
SUMMARY_COLUMNS = (
    "semantics",
    "property_set",
    "transport",
    "robots",
    "runs",
    "expected_runs",
    "complete",
    "latency_samples_mean",
    "latency_overhead_ms_p50_mean",
    "latency_overhead_ms_p95_mean",
    "latency_overhead_ms_p99_mean",
    "result_latency_ms_p50_mean",
    "result_latency_ms_p95_mean",
    "result_latency_ms_p99_mean",
)
COVERAGE_COLUMNS = (
    "semantics",
    "property_set",
    "transport",
    "status",
    "complete_robot_counts",
    "planned_robot_counts",
)


def _successful(row: dict[str, Any]) -> bool:
    return bool(row.get("ok") and row.get("latency_samples", 0) > 0)


def _latest_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest = {}
    for row in rows:
        key = (
            row["semantics"],
            row["property_set"],
            row["transport"],
            row["robots"],
            row["seed"],
        )
        latest[key] = row
    return list(latest.values())


def aggregate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in _latest_rows(rows):
        if _successful(row):
            key = (
                row["semantics"],
                row["property_set"],
                row["transport"],
                row["robots"],
            )
            groups[key].append(row)

    summary = []
    for (semantics, property_set, transport, robots), group in sorted(groups.items()):
        summary.append(
            {
                "semantics": semantics,
                "property_set": property_set,
                "transport": transport,
                "robots": robots,
                "runs": len(group),
                "latency_samples_mean": fmean(row["latency_samples"] for row in group),
                **{
                    f"latency_overhead_ms_{percentile}_mean": fmean(
                        row[f"latency_overhead_ms_{percentile}"] for row in group
                    )
                    for percentile in PERCENTILES
                },
                **{
                    f"result_latency_ms_{percentile}_mean": fmean(
                        row[f"result_latency_ms_{percentile}"] for row in group
                    )
                    for percentile in PERCENTILES
                },
            }
        )
    return summary


def _read_plan(output_dir: Path, rows: list[dict[str, Any]]) -> dict[str, list[Any]]:
    path = output_dir / "config.toml"
    if path.exists():
        benchmark = tomllib.loads(path.read_text(encoding="utf-8"))["benchmark"]
        return {
            "robots": list(benchmark["robots"]),
            "seeds": list(benchmark["seeds"]),
            "property_sets": list(benchmark["property_sets"]),
            "transports": list(benchmark["transports"]),
            "semantics": list(benchmark.get("semantics", ["delayed-qualitative"])),
        }
    if not rows:
        raise ValueError(f"no benchmark config or results in {output_dir}")
    return {
        "robots": sorted({row["robots"] for row in rows}),
        "seeds": sorted({row["seed"] for row in rows}),
        "property_sets": sorted({row["property_set"] for row in rows}),
        "transports": sorted({row["transport"] for row in rows}),
        "semantics": sorted({row["semantics"] for row in rows}),
    }


def series_coverage(
    rows: list[dict[str, Any]],
    summary: list[dict[str, Any]],
    plan: dict[str, list[Any]],
) -> list[dict[str, Any]]:
    attempted = {
        (row["semantics"], row["property_set"], row["transport"])
        for row in _latest_rows(rows)
    }
    complete = {
        (row["semantics"], row["property_set"], row["transport"], row["robots"])
        for row in summary
        if row["complete"]
    }
    coverage = []
    for semantics, property_set, transport in product(
        plan["semantics"], plan["property_sets"], TRANSPORTS
    ):
        key = (semantics, property_set, transport)
        complete_robots = sum(
            (semantics, property_set, transport, robots) in complete
            for robots in plan["robots"]
        )
        if transport not in plan["transports"]:
            status = "not configured"
        elif complete_robots == len(plan["robots"]):
            status = "complete"
        elif key not in attempted:
            status = "not run"
        else:
            status = "partial"
        coverage.append(
            {
                "semantics": semantics,
                "property_set": property_set,
                "transport": transport,
                "status": status,
                "complete_robot_counts": complete_robots,
                "planned_robot_counts": len(plan["robots"]),
            }
        )
    return coverage


def write_report(output_dir: Path, report_dir: Path | None = None) -> list[Path]:
    rows = read_results(output_dir)
    plan = _read_plan(output_dir, rows)
    summary = aggregate(rows)
    for row in summary:
        row["expected_runs"] = len(plan["seeds"])
        row["complete"] = row["runs"] == row["expected_runs"]
    coverage = series_coverage(rows, summary, plan)

    report_dir = report_dir or output_dir / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    csv_path = report_dir / "latency.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(summary)

    markdown_path = report_dir / "latency.md"
    lines = [
        "# Latency report",
        "",
        "- **Latency overhead:** `max(0, time to first result - semantics baseline)`, where",
        "  delayed and eager semantics use the property horizon and RoSI uses zero.",
        "- **Time to first result:** elapsed wall-clock time from publication of an evaluation",
        "  timestamp to arrival of its first valid result.",
        "",
        "## Series coverage",
        "",
    ]
    lines.extend(_table(coverage, COVERAGE_COLUMNS))
    lines.extend(
        [
            "",
            "Only robot counts with every configured seed are plotted; incomplete points are left blank.",
            "",
            "## Per-robot results",
            "",
        ]
    )
    lines.extend(_table(summary, SUMMARY_COLUMNS))
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    coverage_by_series = {
        (row["semantics"], row["property_set"], row["transport"]): row
        for row in coverage
    }
    figures = [
        _plot_fan(
            [row for row in summary if row["semantics"] == semantics],
            report_dir / f"latency_overhead_fan_{semantics}.png",
            semantics,
            plan,
            coverage_by_series,
        )
        for semantics in plan["semantics"]
    ]
    return [csv_path, markdown_path, *figures]


def _table(rows: list[dict[str, Any]], columns: tuple[str, ...]) -> list[str]:
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    lines.extend(
        "| " + " | ".join(_cell(row[column]) for column in columns) + " |"
        for row in rows
    )
    return lines


def _cell(value: Any) -> str:
    return f"{value:.4g}" if isinstance(value, float) else str(value)


def _series_values(
    points: dict[int, dict[str, Any]], robots: list[int], metric: str
) -> list[float]:
    return [
        points[count][metric] if count in points else float("nan") for count in robots
    ]


def _plot_fan(
    summary: list[dict[str, Any]],
    path: Path,
    semantics: str,
    plan: dict[str, list[Any]],
    coverage: dict[tuple[str, str, str], dict[str, Any]],
) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    colors = {"direct": "tab:blue", "ros": "tab:orange"}
    properties = plan["property_sets"]
    fig, axes = plt.subplots(
        len(properties),
        1,
        figsize=(8, max(3.2, 2.8 * len(properties))),
        squeeze=False,
        sharex=True,
        sharey=True,
    )
    for axis, property_set in zip(axes[:, 0], properties):
        notes = []
        for transport in TRANSPORTS:
            state = coverage[(semantics, property_set, transport)]
            if state["status"] != "complete":
                notes.append(f"{transport}: {state['status']}")
            points = {
                row["robots"]: row
                for row in summary
                if row["property_set"] == property_set
                and row["transport"] == transport
                and row["complete"]
            }
            if not points:
                continue
            x = plan["robots"]
            values = {
                percentile: _series_values(
                    points, x, f"latency_overhead_ms_{percentile}_mean"
                )
                for percentile in PERCENTILES
            }
            color = colors[transport]
            axis.fill_between(
                x, values["p50"], values["p95"], color=color, alpha=0.18, linewidth=0
            )
            axis.fill_between(
                x, values["p95"], values["p99"], color=color, alpha=0.08, linewidth=0
            )
            for percentile, style in zip(PERCENTILES, ("-", "--", ":")):
                axis.plot(
                    x,
                    values[percentile],
                    color=color,
                    linestyle=style,
                    linewidth=1.8,
                    marker="o",
                    markersize=3.5,
                )
        if notes:
            axis.text(
                0.98,
                0.95,
                "\n".join(notes),
                transform=axis.transAxes,
                ha="right",
                va="top",
                fontsize="small",
            )
        axis.set_title(property_set)
        axis.set_yscale("symlog", linthresh=0.01)
        axis.axhline(0, color="0.4", linewidth=0.7, alpha=0.5)
        axis.grid(True, which="both", alpha=0.25)

    axes[-1, 0].set_xlabel("robots")
    axes[-1, 0].set_xticks(plan["robots"])
    fig.supylabel("latency overhead (ms)")
    handles = [
        Line2D([], [], color=colors[name], linewidth=3, label=name)
        for name in TRANSPORTS
    ]
    handles += [
        Line2D([], [], color="black", linestyle=style, label=label)
        for label, style in zip(PERCENTILES, ("-", "--", ":"))
    ]
    fig.suptitle(semantics, y=0.99)
    fig.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.965),
        ncol=len(handles),
    )
    fig.tight_layout(rect=(0.02, 0, 1, 0.90))
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path
