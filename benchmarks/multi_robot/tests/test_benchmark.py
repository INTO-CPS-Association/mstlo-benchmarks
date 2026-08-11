import pytest

from mstlo_bench.benchmark import (
    MAX_RETRIES,
    Point,
    _output_lock,
    load_config,
    run_attempts,
)


def test_minimal_config(tmp_path):
    path = tmp_path / "benchmark.toml"
    path.write_text(
        """
[benchmark]
robots = [1, 10]
seeds = [7]
property_sets = ["confined"]
transports = ["direct", "ros"]
duration_s = 1
publish_rate_hz = 20
""",
        encoding="utf-8",
    )
    config = load_config(path)
    assert config.sim_hz == 60
    assert config.transports == ["direct", "ros"]
    assert config.semantics == ["delayed-qualitative"]
    assert config.algorithm == "incremental"
    assert (
        Point(10, 7, "confined", "direct", "delayed-qualitative").name()
        == "confined-delayed-qualitative-direct-r10-s7"
    )


def _attempts(outcomes):
    calls = iter(outcomes)

    def attempt():
        return {"ok": next(calls), "error": "ROS runner exited 1"}

    return attempt


def test_run_attempts_returns_the_first_success():
    row = run_attempts(_attempts([True]))
    assert row["ok"]
    assert row["attempts"] == 1


def test_run_attempts_retries_until_a_point_succeeds():
    row = run_attempts(_attempts([False, False, True]))
    assert row["ok"]
    assert row["attempts"] == 3


def test_run_attempts_gives_up_after_five_retries():
    row = run_attempts(_attempts([False] * (MAX_RETRIES + 1)))
    assert not row["ok"]
    assert row["attempts"] == MAX_RETRIES + 1


def test_output_directory_rejects_a_concurrent_benchmark(tmp_path):
    with (
        _output_lock(tmp_path),
        pytest.raises(RuntimeError, match="another benchmark is already writing"),
    ):
        with _output_lock(tmp_path):
            pass
