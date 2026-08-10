import json

import pytest

import results


@pytest.fixture(autouse=True)
def results_root(tmp_path, monkeypatch):
    monkeypatch.setenv("RESULTS_ROOT", str(tmp_path))
    return tmp_path


def write_metadata(directory, *stages):
    (directory / "metadata.json").write_text(
        json.dumps({"stages": [{"stage": stage} for stage in stages]})
    )


def test_new_directories_are_unique_and_named_after_the_config(results_root):
    first = results.new("demo", "quick")
    second = results.new("demo", "quick")

    assert first.is_dir() and second.is_dir()
    assert first != second
    assert first.parent == results_root / "demo"
    assert first.name.startswith("quick-")


def test_latest_points_at_the_newest_directory(results_root):
    results.new("demo", "quick")
    newest = results.new("demo", "quick")

    link = results_root / "demo" / "latest"
    assert link.is_symlink()
    assert link.resolve() == newest.resolve()


def test_latest_finds_the_newest_directory_holding_a_stage(results_root):
    gathered = results.new("demo", "default")
    write_metadata(gathered, "gather")
    measured = results.new("demo", "default")
    write_metadata(measured, "run", "analyze")
    # Newer than both, but nothing has finished writing to it yet.
    results.new("demo", "default")

    assert results.latest("demo", stage="run") == measured
    assert results.latest("demo", stage="gather") == gathered


def test_latest_can_be_narrowed_to_one_config(results_root):
    quick = results.new("demo", "quick")
    write_metadata(quick, "run")
    default = results.new("demo", "default")
    write_metadata(default, "run")

    assert results.latest("demo", stage="run") == default
    assert results.latest("demo", stage="run", config="quick") == quick


def test_resolve_takes_a_name_a_path_or_the_latest_link(results_root, tmp_path):
    directory = results.new("demo", "quick")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    assert results.resolve("demo", directory.name) == directory
    assert results.resolve("demo", "latest") == directory
    assert results.resolve("demo", str(directory)) == directory
    assert results.resolve("demo", str(elsewhere)) == elsewhere


def test_resolve_refuses_a_directory_that_is_not_there(results_root):
    with pytest.raises(SystemExit, match="no result directory nope"):
        results.resolve("demo", "nope")


def test_latest_explains_itself_when_there_is_nothing_to_find(results_root):
    with pytest.raises(SystemExit, match="no run results for demo"):
        results.latest("demo", stage="run")
