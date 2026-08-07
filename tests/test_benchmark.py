from mstlo_bench.benchmark import Point, load_config


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
