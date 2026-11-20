from pathlib import Path

from deezy.pipeline import run


def test_per_track_dir_stable(tmp_path: Path):
    file_input = tmp_path / "movie.mkv"
    base = tmp_path / "base"

    d1 = run.temp_dir_path(file_input, base, track_label="t0", keep_temp=True)
    d2 = run.temp_dir_path(file_input, base, track_label="t0", keep_temp=True)

    assert d1 == d2
    assert d1.parent == base


def test_per_run_dir_unique(tmp_path: Path):
    file_input = tmp_path / "movie.mkv"
    base = tmp_path / "base"

    d1 = run.temp_dir_path(file_input, base, track_label="t0", keep_temp=False)
    d2 = run.temp_dir_path(file_input, base, track_label="t0", keep_temp=False)

    assert d1 != d2


def test_planning_creates_no_temp_dir(tmp_path: Path):
    d = run.temp_dir_path(tmp_path / "movie.mkv", tmp_path / "base", "t0")
    assert not d.exists()


def test_cleanup_respects_keep_flag(tmp_path: Path):
    per_run = tmp_path / "run"
    per_run.mkdir()
    run.clean_temp(per_run, keep_temp=False)
    assert not per_run.exists()

    kept = tmp_path / "kept"
    kept.mkdir()
    run.clean_temp(kept, keep_temp=True)
    assert kept.exists()
