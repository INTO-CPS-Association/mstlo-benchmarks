from __future__ import annotations

import json
from pathlib import Path

import pytest

from mstlo_bench import benchmark, cli, metadata


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


def test_fresh_result_directories_are_unique(tmp_path):
    first = benchmark.fresh_result_directory(tmp_path, "quick")
    second = benchmark.fresh_result_directory(tmp_path, "quick")

    assert first.is_dir()
    assert second.is_dir()
    assert first != second
    assert first.parent == tmp_path
    assert first.name.startswith("quick-")


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


def test_run_and_report_uses_fresh_directory_and_returns_failure_status(
    tmp_path, monkeypatch
):
    config = tmp_path / "quick.toml"
    config.write_text("[benchmark]\n", encoding="utf-8")
    calls: dict[str, object] = {}

    def fake_run(path, output, *, resume):
        calls["run"] = (path, output, resume)
        output.mkdir(parents=True, exist_ok=True)
        (output / "config.toml").write_bytes(config.read_bytes())
        (output / "results.jsonl").write_text("{}\n", encoding="utf-8")
        return [{"ok": False}]

    def fake_report(output, report_dir):
        calls["report"] = (output, report_dir)
        return [output / "report" / "latency.md"]

    monkeypatch.setattr(cli, "run", fake_run)
    monkeypatch.setattr(cli, "write_report", fake_report)

    status = cli.run_and_report(
        config,
        results_root=tmp_path / "results",
        suite_name="quick",
    )

    assert status == 1
    run_call = calls["run"]
    assert isinstance(run_call, tuple)
    assert run_call[2] is False
    report_call = calls["report"]
    assert isinstance(report_call, tuple)
    assert Path(report_call[0]).parent == tmp_path / "results"


def test_metadata_degrades_when_platform_fields_are_unavailable(tmp_path, monkeypatch):
    config = tmp_path / "config.toml"
    config.write_text("[benchmark]\n", encoding="utf-8")
    monkeypatch.setattr(metadata, "_read_cpu_model", lambda: None)
    monkeypatch.setattr(metadata, "_memory_limit_bytes", lambda: None)
    monkeypatch.setattr(
        metadata.platform, "uname", lambda: (_ for _ in ()).throw(OSError())
    )

    result = metadata.collect_metadata(config)

    assert result["config_sha256"]
    assert result["cpu_model"] is None
    assert result["memory_limit_bytes"] is None
    assert result["kernel"] is None
    assert result["completed_at_utc"] is None
    json.dumps(result)
