from __future__ import annotations

import json
from pathlib import Path
from typing import Any

RESULTS_FILE = "results.jsonl"


def append_result(output_dir: Path, row: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / RESULTS_FILE).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def read_results(output_dir: Path) -> list[dict[str, Any]]:
    path = output_dir / RESULTS_FILE
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]
