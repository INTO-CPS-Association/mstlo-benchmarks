from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

PROPERTY_SETS = ("confined", "dwell", "occupancy")


@dataclass(frozen=True)
class Property:
    name: str
    formula: str


def signal_names(robot: int) -> tuple[str, str]:
    return f"robot_{robot}_x", f"robot_{robot}_y"


def _box(robot: int, bounds: tuple[float, float, float, float]) -> str:
    x, y = signal_names(robot)
    min_x, max_x, min_y, max_y = bounds
    return f"{x} > {min_x:g} && {x} < {max_x:g} && {y} > {min_y:g} && {y} < {max_y:g}"


def build_properties(
    property_set: str, robots: int, window_s: float, dwell_s: float
) -> list[Property]:
    if property_set not in PROPERTY_SETS:
        raise ValueError(f"unknown property set {property_set!r}")
    arena = (-8.88, 8.38, -10.88, 7.88)
    lift = (-9.0, 1.0, -11.0, -1.0)
    if property_set == "confined":
        return [
            Property(f"confined_{robot}", _box(robot, arena)) for robot in range(robots)
        ]
    if property_set == "dwell":
        return [
            Property(
                f"dwell_{robot}",
                f"G[0,{window_s:g}](({_box(robot, lift)}) -> F[0,{dwell_s:g}](!({_box(robot, lift)})))",
            )
            for robot in range(robots)
        ]
    inside = " || ".join(f"({_box(robot, lift)})" for robot in range(robots))
    return [Property("occupancy_vertical_lift", f"G[0,{window_s:g}]({inside})")]


def semantic_horizon_ms(
    property_set: str, semantics: str, window_s: float, dwell_s: float
) -> int:
    if semantics == "robustness-interval":
        return 0
    seconds = {"confined": 0.0, "dwell": window_s + dwell_s, "occupancy": window_s}[
        property_set
    ]
    return round(seconds * 1000)


def write_artefacts(
    directory: Path,
    property_set: str,
    robots: int,
    window_s: float,
    dwell_s: float,
    topic_namespace: str = "",
) -> tuple[Path, Path, Path]:
    properties = build_properties(property_set, robots, window_s, dwell_s)
    directory.mkdir(parents=True, exist_ok=True)
    property_path = directory / "properties.mstlo"
    property_path.write_text(
        "\n".join(f"{prop.name}: {prop.formula}" for prop in properties) + "\n",
        encoding="utf-8",
    )
    topic_prefix = f"/{topic_namespace.strip('/')}" if topic_namespace else ""
    input_map = {
        signal: {
            "topic": f"{topic_prefix}/mstlo/robot_{robot}/{axis}",
            "msg_type": "MstloTimedValue",
        }
        for robot in range(robots)
        for axis, signal in zip(("x", "y"), signal_names(robot))
    }
    output_topics = {
        prop.name: f"{topic_prefix}/mstlo/verdict/{prop.name}" for prop in properties
    }
    output_map = {
        name: {"topic": topic, "msg_type": "MstloTimedValue"}
        for name, topic in output_topics.items()
    }
    input_path = directory / "input.json"
    output_path = directory / "output.json"
    input_path.write_text(json.dumps(input_map, indent=2) + "\n", encoding="utf-8")
    output_path.write_text(json.dumps(output_map, indent=2) + "\n", encoding="utf-8")
    return property_path, input_path, output_path
