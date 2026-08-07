import json

from mstlo_bench.properties import (
    build_properties,
    semantic_horizon_ms,
    signal_names,
    write_artefacts,
)


def test_workloads_and_horizons():
    assert len(build_properties("confined", 4, 10, 5)) == 4
    assert len(build_properties("dwell", 4, 10, 5)) == 4
    assert len(build_properties("occupancy", 4, 10, 5)) == 1
    assert semantic_horizon_ms("confined", "delayed-qualitative", 10, 5) == 0
    assert semantic_horizon_ms("dwell", "delayed-quantitative", 10, 5) == 15_000
    assert semantic_horizon_ms("occupancy", "delayed-qualitative", 10, 5) == 10_000
    assert semantic_horizon_ms("dwell", "eager-qualitative", 10, 5) == 15_000
    assert semantic_horizon_ms("dwell", "robustness-interval", 10, 5) == 0


def test_ros_maps_match_runner_topics(tmp_path):
    _, input_map, output_map = write_artefacts(tmp_path, "dwell", 2, 10, 5)
    assert '"/mstlo/robot_1/y"' in input_map.read_text()
    assert '"MstloTimedValue"' in output_map.read_text()
    assert set(json.loads(output_map.read_text())) == {"dwell_0", "dwell_1"}
    assert signal_names(1) == ("robot_1_x", "robot_1_y")
