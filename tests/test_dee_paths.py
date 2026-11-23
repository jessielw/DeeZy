import os
from pathlib import Path

import pytest

from deezy.exceptions import OutputFileNotFoundError, PathTooLongError
from deezy.pipeline import run
from deezy.pipeline.plan import dee_output_path
from deezy.utils.paths import (
    MAX_ARTIFACT_NAME,
    MAX_DEE_PATH,
    artifact_stem,
    long_path_str,
)

windows_only = pytest.mark.skipif(
    os.name != "nt", reason="extended-length paths are a Windows feature"
)

# the output name that produced a 322 character job path and made DEE report a
# file that was sitting right there as "Cannot open file"
LONG_OUTPUT = Path(
    ".The.Thing.1982.ARROW.BluRay.1080p.DTS-X.7.1.AVC.HYBRID.REMUX-FraMeSToR"
    "_track2_[eng] [Audio 1] [8ch] [Eac3].00000000000000000000000000000000"
    ".part.ec3"
)


def test_artifact_stem_is_bounded_regardless_of_output_length():
    stem = artifact_stem(LONG_OUTPUT)
    assert len(f"{stem}_metadata.json") <= MAX_ARTIFACT_NAME


def test_artifact_stem_is_stable_across_calls():
    # --reuse-temp-files looks temp artifacts up by name across runs
    assert artifact_stem(LONG_OUTPUT) == artifact_stem(LONG_OUTPUT)


def test_artifact_stem_separates_outputs_sharing_a_truncated_prefix():
    shared = "A.Very.Long.Release.Name.That.Collides.When.Truncated"
    first = artifact_stem(Path(f"{shared}.track1.ec3"))
    second = artifact_stem(Path(f"{shared}.track2.ec3"))
    assert first != second


def test_long_output_now_fits_under_a_realistic_temp_base(tmp_path: Path):
    # the real-world failure: a GUI-supplied partial output name under a
    # per-user cache directory
    base = Path(r"C:\Users\someone\AppData\Local\FFmpegAudioEncoder\Cache\deezy-temp")
    file_input = tmp_path / (
        "The.Thing.1982.ARROW.BluRay.1080p.DTS-X.7.1.AVC.HYBRID."
        "REMUX-FraMeSToR_track2_[eng]_DELAY 5ms.flac"
    )
    file_input.write_text("x")

    dir_name = run.short_unique_name(file_input)
    job_json = base / dir_name / f"{artifact_stem(LONG_OUTPUT)}.ddp.json"

    assert len(str(job_json)) <= MAX_DEE_PATH


def test_long_path_str_leaves_ordinary_paths_alone():
    short = Path.cwd() / "job.json"
    assert long_path_str(short) == str(short)


@windows_only
def test_long_path_str_escapes_a_path_dee_could_not_open():
    long_path = Path("C:/") / ("d" * 200) / f"{'f' * 120}.json"
    rendered = long_path_str(long_path)
    assert rendered.startswith("\\\\?\\C:\\")
    assert rendered.endswith(".json")


@windows_only
def test_long_path_str_does_not_double_escape():
    long_path = Path("C:/") / ("d" * 200) / f"{'f' * 120}.json"
    once = long_path_str(long_path)
    assert long_path_str(once) == once


def test_relative_paths_are_never_escaped():
    # extended-length paths must be fully qualified, so a relative one is
    # passed through and left for the caller to resolve
    relative = Path("d" * 200) / f"{'f' * 120}.json"
    assert long_path_str(relative) == str(relative)


def test_temp_dir_rejects_a_base_with_no_room_for_job_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    file_input = tmp_path / "movie.mkv"
    file_input.write_text("x")

    # Simulate a smaller DEE budget so the constructed path stays below the
    # host filesystem's PATH_MAX and can safely be inspected afterward.
    monkeypatch.setattr(run, "MAX_DEE_PATH", 256)

    # a base deep enough that no job file could sit beside it
    base = tmp_path
    over_budget = run.MAX_DEE_PATH - MAX_ARTIFACT_NAME + 64
    while len(str(base)) < over_budget:
        base = base / ("x" * min(64, over_budget - len(str(base))))

    with pytest.raises(PathTooLongError):
        run.temp_dir_path(file_input, base, track_label="t0", keep_temp=True)

    # and it fails before creating anything
    assert not base.exists()


def test_dee_encodes_into_the_temp_dir_not_the_destination(tmp_path: Path):
    temp_dir = tmp_path / "job"
    dee_output = dee_output_path(temp_dir, LONG_OUTPUT)

    assert dee_output.parent == temp_dir
    assert dee_output.suffix == LONG_OUTPUT.suffix
    # whatever the destination looks like, DEE only sees a bounded name
    assert len(dee_output.name) <= MAX_ARTIFACT_NAME


def test_finalize_moves_the_encode_to_its_destination(tmp_path: Path):
    temp_dir = tmp_path / "job"
    temp_dir.mkdir()
    dee_output = temp_dir / "encoded.ec3"
    dee_output.write_bytes(b"bitstream")

    output = tmp_path / "nested" / "final.ec3"
    run.finalize_output(dee_output, output)

    assert output.read_bytes() == b"bitstream"
    assert not dee_output.exists()


def test_finalize_overwrites_an_existing_destination(tmp_path: Path):
    dee_output = tmp_path / "encoded.ec3"
    dee_output.write_bytes(b"new")
    output = tmp_path / "final.ec3"
    output.write_bytes(b"old")

    run.finalize_output(dee_output, output)

    assert output.read_bytes() == b"new"


def test_finalize_reports_a_missing_encode(tmp_path: Path):
    with pytest.raises(OutputFileNotFoundError):
        run.finalize_output(tmp_path / "never_written.ec3", tmp_path / "final.ec3")
