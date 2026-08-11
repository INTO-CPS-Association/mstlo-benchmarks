from __future__ import annotations

from pathlib import Path

import pytest

from mstlo_bench import benchmark


def _executable(path: Path) -> Path:
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def test_prebuilt_mode_selects_and_validates_configured_runner(tmp_path, monkeypatch):
    runner = _executable(tmp_path / "runner")
    monkeypatch.setenv("MSTLO_BENCH_PREBUILT", "1")
    monkeypatch.setenv("MSTLO_RUNNER_BIN", str(runner))

    assert benchmark._runner_binary() == runner
    benchmark._build(needs_ros=False)

    missing = tmp_path / "missing-runner"
    monkeypatch.setenv("MSTLO_RUNNER_BIN", str(missing))
    with pytest.raises(RuntimeError, match="prebuilt runner binary not found"):
        benchmark._build(needs_ros=False)


def test_prebuilt_ros_mode_reports_missing_overlay(tmp_path, monkeypatch):
    runner = _executable(tmp_path / "runner")
    checker = _executable(tmp_path / "checker")
    monkeypatch.setenv("MSTLO_BENCH_PREBUILT", "1")
    monkeypatch.setenv("MSTLO_RUNNER_BIN", str(runner))
    monkeypatch.setenv("MSTLO_CHECKER_BIN", str(checker))
    monkeypatch.setenv("MSTLO_ROS_OVERLAY", str(tmp_path / "missing-overlay"))

    with pytest.raises(RuntimeError, match="ROS setup"):
        benchmark._build(needs_ros=True)


def test_existing_results_require_explicit_resume(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text(
        """
[benchmark]
robots = [1]
seeds = [1]
property_sets = ["confined"]
transports = ["direct"]
duration_s = 1
publish_rate_hz = 10
""",
        encoding="utf-8",
    )
    output = tmp_path / "run"
    output.mkdir()
    (output / "results.jsonl").write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="pass --resume"):
        benchmark._prepare_output_directory(config, output, resume=False)

    benchmark._prepare_output_directory(config, output, resume=True)
    assert (output / "config.toml").read_bytes() == config.read_bytes()
