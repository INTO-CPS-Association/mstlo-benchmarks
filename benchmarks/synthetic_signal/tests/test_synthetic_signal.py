"""What the synthetic-signal run stage decides before it measures anything.

The catalog of formulas and the signal used to be hardcoded, once in the Rust
bench and once in the mstlo-python one.  They are built here now, so these tests
pin the two things that move: that the defaults still produce the paper's sweep
and the paper's signal, and that the settings around them do what they say.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

SYNTHETIC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SYNTHETIC))

import formulas  # noqa: E402
import signals  # noqa: E402

# The upstream generator the new one has to agree with, in the mstlo subtree.
# The image says where that checkout is; in a working tree it is alongside
# benchmarks/, at the repository root.
MSTLO_ROOT = Path(
    os.environ.get("MSTLO_ROOT", Path(__file__).resolve().parents[3] / "mstlo")
)
UPSTREAM_GENERATOR = (
    MSTLO_ROOT
    / "benchmarks"
    / "synthetic_signal"
    / "signal_generation"
    / "signal_generator.py"
)


def catalog(**overrides):
    """The catalog the run stage would build, with the stage's own defaults."""
    settings = {
        "bound_low": 0.0,
        "bound_high": 5000.0,
        "bound_step": 100.0,
        "first_bound": 1.0,
        "formula_ids": "",
        "custom": "",
    }
    settings.update(overrides)
    return formulas.build(
        bounds=formulas.sweep(
            settings["bound_low"],
            settings["bound_high"],
            settings["bound_step"],
            settings["first_bound"],
        ),
        selected=formulas.parse_ids(settings["formula_ids"]),
        custom=formulas.parse_custom(settings["custom"]),
    )


def specs_for(catalog, formula_id):
    return [spec for identifier, spec in catalog if identifier == formula_id]


# ---------------------------------------------------------------------------
# The formulas
# ---------------------------------------------------------------------------


def test_the_defaults_are_the_sweep_the_paper_reports():
    """Four fixed formulas and three families of 51 bounds: 1, 100, ... 5000."""
    built = catalog()

    assert len(built) == 4 + 3 * 51
    assert specs_for(built, 6) == ["G[0,1] (x > 0.0)"] + [
        f"G[0,{bound}] (x > 0.0)" for bound in range(100, 5001, 100)
    ]


def test_a_sweep_that_starts_at_zero_starts_at_the_first_bound_instead():
    """G[0,0] has no temporal depth, so the zero point is moved off zero."""
    assert formulas.sweep(0, 300, 100, first=1) == [1, 100, 200, 300]
    assert formulas.sweep(100, 300, 100, first=1) == [100, 200, 300]


def test_a_first_bound_that_would_not_come_first_is_refused():
    with pytest.raises(SystemExit, match="not below the next one"):
        formulas.sweep(0, 300, 100, first=150)


def test_the_bounds_are_free_to_be_anything():
    assert formulas.sweep(50, 200, 50, first=1) == [50, 100, 150, 200]
    assert formulas.sweep(0, 1, 0.25, first=0.1) == [0.1, 0.25, 0.5, 0.75, 1]


def test_a_fractional_bound_survives_into_the_spec():
    built = catalog(bound_low=0.5, bound_high=1.5, bound_step=0.5)

    assert specs_for(built, 6) == [
        "G[0,0.5] (x > 0.0)",
        "G[0,1] (x > 0.0)",
        "G[0,1.5] (x > 0.0)",
    ]


def test_the_selection_narrows_the_built_ins():
    built = catalog(formula_ids="1,6", bound_high=200)

    assert [identifier for identifier, _ in built] == [1, 6, 6, 6]


def test_the_selection_is_written_however_is_convenient():
    assert formulas.parse_ids("1,2,3") == {1, 2, 3}
    assert formulas.parse_ids("1 2 3") == {1, 2, 3}
    assert formulas.parse_ids("1\n2\n3") == {1, 2, 3}
    assert formulas.parse_ids("  ") is None


def test_custom_formulas_are_measured_after_the_built_ins_and_numbered_apart():
    """From 100, so they cannot be mistaken for a family the analysis plots."""
    built = catalog(formula_ids="1", custom="G[0,50] (x > 0.0)\n\nF[0,7] (x < 0.0)\n")

    assert built == [
        (1, formulas.FIXED[0][1]),
        (100, "G[0,50] (x > 0.0)"),
        (101, "F[0,7] (x < 0.0)"),
    ]


def test_custom_formulas_alone_are_enough_to_measure():
    built = catalog(formula_ids="0", custom="G[0,50] (x > 0.0)")

    assert built == [(100, "G[0,50] (x > 0.0)")]


def test_asking_for_nothing_at_all_is_refused():
    with pytest.raises(SystemExit, match="nothing to measure"):
        catalog(formula_ids="0")


def test_a_catalog_survives_the_round_trip_to_the_file_the_benches_read(tmp_path):
    """Both benches parse this file, so what comes back has to be what went in."""
    built = catalog(bound_high=200, custom="G[0,50] (x > 0.0)")
    path = tmp_path / "formulas.tsv"

    formulas.write(path, built)

    assert formulas.read(path) == built
    assert path.read_text().splitlines()[0] == "formula_id\tspec"


def test_a_file_without_the_header_is_refused(tmp_path):
    path = tmp_path / "formulas.tsv"
    path.write_text("6\tG[0,1] (x > 0.0)\n")

    with pytest.raises(SystemExit, match="header"):
        formulas.read(path)


# ---------------------------------------------------------------------------
# The signal
# ---------------------------------------------------------------------------


def generate(tmp_path, signal_type, num_samples=50, **overrides):
    settings = {
        "sampling_rate": 1.0,
        "frequency": 0.01,
        "start_frequency": 0.01,
        "end_frequency": 0.0001,
        "amplitude": 1.0,
        "value": 0.25,
    }
    settings.update(overrides)
    t, values = signals.generate(
        signal_type=signal_type, num_samples=num_samples, **settings
    )
    path = tmp_path / f"{signal_type}.csv"
    signals.write(path, t, values)
    return path


@pytest.mark.parametrize("signal_type", ["sine", "chirp"])
def test_the_paper_signals_are_the_ones_upstream_generates(tmp_path, signal_type):
    """The two shapes that predate this script must not have moved."""
    if signal_type == "chirp":
        pytest.importorskip("scipy", reason="chirp comes from scipy.signal")

    upstream = tmp_path / "upstream.csv"
    subprocess.run(
        [
            sys.executable,
            str(UPSTREAM_GENERATOR),
            "--num-samples", "50",
            "--signal-type", signal_type,
            "--output-path", str(upstream),
        ],
        check=True,
        capture_output=True,
    )

    assert generate(tmp_path, signal_type).read_text() == upstream.read_text()


def test_a_ramp_crosses_every_threshold_the_formulas_test_once(tmp_path):
    rows = generate(tmp_path, "linear-increasing", num_samples=5).read_text().splitlines()

    assert rows == ["timestep,value", "0.0,-1.0", "1.0,-0.5", "2.0,0.0", "3.0,0.5", "4.0,1.0"]


def test_the_ramps_are_each_other_reversed(tmp_path):
    up = generate(tmp_path / "up", "linear-increasing", amplitude=2.0)
    down = generate(tmp_path / "down", "linear-decreasing", amplitude=2.0)

    def values(path):
        return [float(line.split(",")[1]) for line in path.read_text().splitlines()[1:]]

    assert values(up) == pytest.approx(list(reversed(values(down))))


def test_the_constant_is_whatever_it_is_set_to(tmp_path):
    rows = generate(tmp_path, "constant", num_samples=3, value=-0.5).read_text().splitlines()

    assert rows == ["timestep,value", "0.0,-0.5", "1.0,-0.5", "2.0,-0.5"]


def test_the_sampling_rate_decides_the_timesteps(tmp_path):
    """1.0 Hz is what makes a bound mean the same number of steps to everything."""
    rows = generate(tmp_path, "constant", num_samples=3, sampling_rate=2.0).read_text().splitlines()

    assert [row.split(",")[0] for row in rows[1:]] == ["0.0", "0.5", "1.0"]


def test_a_shape_nobody_generates_is_refused(tmp_path):
    with pytest.raises(SystemExit, match="unknown signal type"):
        generate(tmp_path, "sawtooth")
