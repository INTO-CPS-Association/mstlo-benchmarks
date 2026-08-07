from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from statistics import fmean
from typing import Any

from .collect import read_results

PERCENTILES = ("p50", "p95", "p99")


def aggregate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("ok") and row.get("latency_samples", 0) > 0:
            groups[
                (
                    row["semantics"],
                    row["property_set"],
                    row["transport"],
                    row["robots"],
                )
            ].append(row)
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
            }
        )
    return summary


def write_report(output_dir: Path, report_dir: Path | None = None) -> list[Path]:
    rows = read_results(output_dir)
    summary = aggregate(rows)
    if not summary:
        raise ValueError(f"no successful latency results in {output_dir}")
    report_dir = report_dir or output_dir / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    csv_path = report_dir / "latency.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)
    markdown_path = report_dir / "latency.md"
    columns = list(summary[0])
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in summary:
        lines.append("| " + " | ".join(_cell(row[column]) for column in columns) + " |")
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    figures = [
        _plot_fan(
            [row for row in summary if row["semantics"] == semantics],
            report_dir / f"latency_overhead_fan_{semantics}.png",
            semantics,
        )
        for semantics in sorted({row["semantics"] for row in summary})
    ]
    return [csv_path, markdown_path, *figures]


def _cell(value: Any) -> str:
    return f"{value:.4g}" if isinstance(value, float) else str(value)


def _plot_fan(summary: list[dict[str, Any]], path: Path, semantics: str) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    properties = sorted({row["property_set"] for row in summary})
    transports = [
        name
        for name in ("direct", "ros")
        if any(row["transport"] == name for row in summary)
    ]
    colors = {"direct": "tab:blue", "ros": "tab:orange"}
    fig, axes = plt.subplots(
        len(properties),
        1,
        figsize=(8, max(3.2, 2.8 * len(properties))),
        squeeze=False,
        sharex=True,
        sharey=True,
    )
    for axis, property_set in zip(axes[:, 0], properties):
        for transport in transports:
            points = sorted(
                (
                    row
                    for row in summary
                    if row["property_set"] == property_set
                    and row["transport"] == transport
                ),
                key=lambda row: row["robots"],
            )
            if not points:
                continue
            x = [row["robots"] for row in points]
            p50 = [row["latency_overhead_ms_p50_mean"] for row in points]
            p95 = [row["latency_overhead_ms_p95_mean"] for row in points]
            p99 = [row["latency_overhead_ms_p99_mean"] for row in points]
            color = colors[transport]
            axis.fill_between(x, p50, p95, color=color, alpha=0.18, linewidth=0)
            axis.fill_between(x, p95, p99, color=color, alpha=0.08, linewidth=0)
            for values, style in ((p50, "-"), (p95, "--"), (p99, ":")):
                axis.plot(x, values, color=color, linestyle=style, linewidth=1.8)
        axis.set_title(property_set)
        axis.set_yscale("log")
        axis.grid(True, which="both", alpha=0.25)
    axes[-1, 0].set_xlabel("robots")
    fig.supylabel("latency overhead (ms)")
    handles = [Patch(color=colors[name], label=name) for name in transports]
    handles += [
        Line2D([], [], color="black", linestyle=style, label=label)
        for label, style in (("p50", "-"), ("p95", "--"), ("p99", ":"))
    ]
    fig.legend(handles=handles, loc="upper center", ncol=len(handles))
    fig.suptitle(semantics)
    fig.tight_layout(rect=(0.02, 0, 1, 0.92))
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path
