"""The procedure every benchmark is driven by, exercised on a fake one.

The three real benchmarks differ only in what their stage scripts do, so a
benchmark that writes a word to a file is enough to pin down the part they
share: which directory a stage gets, and what is recorded about it.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SHARED = Path(__file__).resolve().parents[1]
# The stage layer needs the python3 the images have, not whatever a bare PATH
# finds first: tomllib arrived in 3.11.
PATH = f"{Path(sys.executable).parent}:/usr/bin:/bin:/usr/local/bin"

STAGE = """#!/usr/bin/env sh
set -e
echo "$STAGE $M_RUNS" > "$RESULTS_DIR/{output}"
"""

CONFIG = """
[common]
M_RUNS = {runs}
"""


@pytest.fixture
def bench_root(tmp_path):
    """A tree shaped like benchmarks/, holding one benchmark called `demo`."""
    root = tmp_path / "stages"
    (root / "demo" / "configs").mkdir(parents=True)
    for name in ("entrypoint.sh", "config.py", "metadata.py", "results.py"):
        shutil.copy(SHARED / name, root / name)
    for stage, output in (
        ("gather", "signal.csv"),
        ("run", "measurements.csv"),
        ("analyze", "figure.pdf"),
    ):
        script = root / "demo" / f"{stage}.sh"
        script.write_text(STAGE.format(output=output))
        script.chmod(0o755)
    (root / "demo" / "configs" / "default.toml").write_text(CONFIG.format(runs=50))
    (root / "demo" / "configs" / "quick.toml").write_text(CONFIG.format(runs=2))
    return root


@pytest.fixture
def entrypoint(bench_root, tmp_path):
    """Invoke the stage layer the way a compose service does.

    The service is the benchmark, so `demo` arrives in the environment rather
    than on the command line, exactly as the image sets it.
    """

    def invoke(*arguments, expect=0, **environment):
        completed = subprocess.run(
            ["sh", str(bench_root / "entrypoint.sh"), *arguments],
            capture_output=True,
            text=True,
            env={
                "PATH": PATH,
                "BENCH": "demo",
                "RESULTS_ROOT": str(tmp_path / "results"),
                **environment,
            },
        )
        assert completed.returncode == expect, completed.stderr
        return completed

    return invoke


def written_to(completed):
    """The directory a stage announced it was writing to."""
    header = next(l for l in completed.stdout.splitlines() if l.startswith("==="))
    return Path(header.split(" -> ", 1)[1].rsplit(" ===", 1)[0])


def directories(tmp_path, benchmark="demo"):
    parent = tmp_path / "results" / benchmark
    return sorted(entry for entry in parent.iterdir() if entry.name != "latest")


def metadata(directory):
    return json.loads((directory / "metadata.json").read_text())


def test_a_run_gets_a_directory_of_its_own(entrypoint, tmp_path):
    entrypoint("run")
    entrypoint("run", "quick")

    first, second = sorted(directories(tmp_path), key=lambda p: p.name)
    assert first.name.startswith("default-")
    assert second.name.startswith("quick-")
    assert (first / "measurements.csv").read_text() == "run 50\n"
    assert (second / "measurements.csv").read_text() == "run 2\n"
    assert (tmp_path / "results" / "demo" / "latest").resolve() == second


def test_a_run_records_what_produced_it(entrypoint, tmp_path):
    entrypoint("run", "quick")

    (directory,) = directories(tmp_path)
    meta = metadata(directory)
    assert meta["benchmark"] == "demo"
    assert meta["environment"]["python"]
    (record,) = meta["stages"]
    assert record["stage"] == "run"
    assert record["config"] == "quick"
    assert record["config_sha256"]
    assert record["settings"] == {"M_RUNS": "2"}
    assert record["status"] == "ok"
    assert record["completed_utc"]
    # The config itself, so the run can be repeated without this repository.
    assert (directory / "config.toml").exists()


def test_the_environment_overrides_the_config_and_is_recorded(entrypoint, tmp_path):
    entrypoint("run", "quick", M_RUNS="7")

    (directory,) = directories(tmp_path)
    assert (directory / "measurements.csv").read_text() == "run 7\n"
    assert metadata(directory)["stages"][0]["settings"] == {"M_RUNS": "7"}


def test_a_setting_can_be_a_list_and_arrives_one_entry_per_line(
    entrypoint, bench_root, tmp_path
):
    """An STL formula contains commas and spaces, so lists are split by newline."""
    (bench_root / "demo" / "configs" / "default.toml").write_text(
        '[run]\nFORMULAS = ["G[0,1] (x > 0.0)", "F[0,2] (x < 0.0)"]\n'
    )
    (bench_root / "demo" / "run.sh").write_text(
        '#!/usr/bin/env sh\nprintf "%s" "$FORMULAS" > "$RESULTS_DIR/measurements.csv"\n'
    )
    entrypoint("run")

    (directory,) = directories(tmp_path)
    assert (directory / "measurements.csv").read_text().splitlines() == [
        "G[0,1] (x > 0.0)",
        "F[0,2] (x < 0.0)",
    ]


def test_a_failing_stage_is_recorded_and_propagated(entrypoint, bench_root, tmp_path):
    (bench_root / "demo" / "run.sh").write_text("#!/usr/bin/env sh\nexit 3\n")
    entrypoint("run", expect=3)

    (directory,) = directories(tmp_path)
    assert metadata(directory)["stages"][0]["status"] == "failed (3)"


def test_analyze_lands_in_the_newest_run(entrypoint, tmp_path):
    measured = written_to(entrypoint("run"))
    gathered = written_to(entrypoint("gather"))
    entrypoint("analyze")

    # The gather is newer, but holds no measurements to analyse.
    assert (gathered / "signal.csv").exists()
    assert not (gathered / "figure.pdf").exists()
    assert (measured / "figure.pdf").exists()
    assert [record["stage"] for record in metadata(measured)["stages"]] == [
        "run",
        "analyze",
    ]


def test_analyze_can_be_narrowed_to_a_config(entrypoint, tmp_path):
    entrypoint("run", "quick")
    entrypoint("run", "default")
    entrypoint("analyze", "quick")

    default, quick = sorted(directories(tmp_path), key=lambda p: p.name)
    assert (quick / "figure.pdf").exists()
    assert not (default / "figure.pdf").exists()


def test_analyze_takes_the_run_it_is_pointed_at(entrypoint, tmp_path):
    older = written_to(entrypoint("run", "quick"))
    newer = written_to(entrypoint("run", "quick"))

    # By the name printed when it ran, by an absolute path, and by `latest`.
    entrypoint("analyze", older.name)
    assert (older / "figure.pdf").exists()
    assert not (newer / "figure.pdf").exists()

    (older / "figure.pdf").unlink()
    entrypoint("analyze", str(older))
    assert (older / "figure.pdf").exists()

    entrypoint("analyze", "latest")
    assert (newer / "figure.pdf").exists()


def test_analyze_says_so_when_there_is_nothing_to_analyse(entrypoint):
    completed = entrypoint("analyze", expect=1)
    assert "no run results for demo" in completed.stderr


def test_a_second_argument_that_is_neither_is_rejected(entrypoint, tmp_path):
    entrypoint("run", "quick")

    completed = entrypoint("analyze", "typo", expect=1)
    assert "neither a config of demo nor a result directory" in completed.stderr

    # A measuring stage has nothing to point at, so it only takes a config.
    completed = entrypoint("run", "typo", expect=1)
    assert "no such config: demo/typo" in completed.stderr


def test_an_explicit_results_directory_wins(entrypoint, tmp_path):
    chosen = tmp_path / "somewhere-else"
    entrypoint("run", RESULTS_DIR=str(chosen))

    assert (chosen / "measurements.csv").exists()
    assert not (tmp_path / "results" / "demo").exists()


def test_a_benchmark_named_where_a_config_goes_says_which_service_it_is(entrypoint):
    """The service is the benchmark, so naming one here is a command for another.

    Both halves of the old two-argument habit end up here: the benchmark this
    service already is, and one of the others.
    """
    completed = entrypoint("run", "multi_robot", expect=2)
    assert "docker compose run --rm multi_robot run" in completed.stderr

    completed = entrypoint("run", "demo", expect=2)
    assert "the service already is demo" in completed.stderr


def test_the_image_has_to_say_which_benchmark_it_holds(entrypoint):
    completed = entrypoint("run", expect=2, BENCH="")
    assert "does not say which benchmark" in completed.stderr


def test_no_arguments_lists_what_this_service_can_do(entrypoint):
    completed = entrypoint(expect=1)

    assert "demo" in completed.stderr
    # Its own stages, the test stage every benchmark has, and its configs.
    for word in ("gather", "run", "analyze", "test", "default", "quick"):
        assert word in completed.stderr
    # And where the other benchmarks went.
    assert "docker compose run --rm incubator" in completed.stderr
