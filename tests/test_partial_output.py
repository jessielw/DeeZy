"""A failed or interrupted job leaves no cut-off file where DeeZy or a later run would take it for a finished one."""

import json
import os
from pathlib import Path

import pytest

from deezy.enums.atmos import WarpMode
from deezy.exceptions import OutputFileNotFoundError
from deezy.pipeline import run
from deezy.pipeline.plan import DeeStep, FfmpegStep, JobPlan, TruehddStep
from deezy.track_info.track_index import TrackIndex
from tests.utils.payload_helpers import generate_dummy_core_payload


@pytest.fixture(autouse=True)
def limits() -> None:
    run.init_phase_limits(max_parallel=1)


@pytest.fixture
def across_volumes(monkeypatch):
    """os.replace refuses the first move (temp on another volume), then works."""
    real = os.replace
    calls = []

    def replace(src, dst):
        calls.append((src, dst))
        if len(calls) == 1:
            raise OSError(18, "Invalid cross-device link")
        return real(src, dst)

    monkeypatch.setattr(run.os, "replace", replace)
    return calls


def encode(tmp_path: Path, data: bytes = b"\x0b\x77new") -> Path:
    temp = tmp_path / "temp"
    temp.mkdir(exist_ok=True)
    dee_output = temp / "encoded.ec3"
    dee_output.write_bytes(data)
    return dee_output


def partials(directory: Path) -> list[Path]:
    return sorted(directory.glob(f"*{run.PARTIAL_SUFFIX}"))


# --- finalize_output


def test_across_volumes_the_encode_lands_whole(tmp_path, across_volumes):
    dee_output = encode(tmp_path)
    output = tmp_path / "out" / "Movie.ec3"
    run.finalize_output(dee_output, output)
    assert output.read_bytes() == b"\x0b\x77new"
    assert not dee_output.exists()
    assert partials(output.parent) == []
    # the copy was renamed into place, never written at the output itself
    assert Path(across_volumes[1][0]).name == f"Movie.ec3{run.PARTIAL_SUFFIX}"


def test_an_interrupted_copy_leaves_the_old_output_and_no_partial(
    tmp_path, across_volumes, monkeypatch
):
    dee_output = encode(tmp_path)
    output = tmp_path / "Movie.ec3"
    output.write_bytes(b"old")

    def cut_off(_src, dst):
        Path(dst).write_bytes(b"\x0b")
        raise KeyboardInterrupt

    monkeypatch.setattr(run.shutil, "copyfile", cut_off)
    with pytest.raises(KeyboardInterrupt):
        run.finalize_output(dee_output, output)
    assert output.read_bytes() == b"old"
    assert partials(tmp_path) == []


def test_an_empty_encode_is_refused(tmp_path):
    dee_output = encode(tmp_path, b"")
    output = tmp_path / "Movie.ec3"
    with pytest.raises(OutputFileNotFoundError, match="empty"):
        run.finalize_output(dee_output, output)
    assert not output.exists()


def test_a_save_permission_error_identifies_the_final_path(
    tmp_path, across_volumes, monkeypatch
):
    dee_output = encode(tmp_path)
    output = tmp_path / "Movie.ec3"
    output.write_bytes(b"old")
    plan = JobPlan(
        format="ddp",
        source=tmp_path / "in.mkv",
        output=output,
        temp_dir=dee_output.parent,
        steps=(),
        free_space_needed=1,
    )
    monkeypatch.setattr(run, "run_steps", lambda *_args: dee_output)

    def access_denied(_src, dst):
        Path(dst).write_bytes(b"\x0b")
        raise PermissionError("Access denied")

    monkeypatch.setattr(run.shutil, "copyfile", access_denied)
    payload = generate_dummy_core_payload()
    payload.overwrite = True
    with pytest.raises(
        PermissionError, match="Could not save the completed encode"
    ) as failure:
        run.run_plan(plan, payload)

    assert str(output) in str(failure.value)
    assert "Access denied" in str(failure.value)
    assert output.read_bytes() == b"old"
    assert partials(tmp_path) == []


def test_an_unwritable_output_directory_fails_before_the_encode(tmp_path, monkeypatch):
    blocked = tmp_path / "blocked"
    blocked.touch()
    plan = JobPlan(
        "ddp", tmp_path / "in.mkv", blocked / "out.ec3", tmp_path / "job", ()
    )

    def unexpected_encode(*_args):
        pytest.fail("An encode started with an unusable output directory")

    monkeypatch.setattr(run, "run_steps", unexpected_encode)
    with pytest.raises(OSError, match="Could not write to output directory") as failure:
        run.run_plan(plan, generate_dummy_core_payload())

    assert str(blocked) in str(failure.value)
    assert not plan.temp_dir.exists()


# --- intermediates a later --reuse-temp-files run could pick up


def ffmpeg_job(tmp_path: Path) -> tuple[FfmpegStep, JobPlan]:
    step = FfmpegStep(
        argv=("ffmpeg",), output=tmp_path / "job.wav", reuse_id="ddp", duration=1.0
    )
    plan = JobPlan(
        format="ddp",
        source=tmp_path / "in.mkv",
        output=tmp_path / "out.ec3",
        temp_dir=tmp_path,
        steps=(step,),
    )
    return step, plan


@pytest.mark.parametrize("stop", [KeyboardInterrupt, ValueError])
def test_a_stopped_ffmpeg_run_deletes_its_wav(tmp_path, monkeypatch, stop):
    step, plan = ffmpeg_job(tmp_path)

    def cut_off(**_kwargs):
        step.output.write_bytes(b"RIFF")
        raise stop

    monkeypatch.setattr(run, "process_ffmpeg_job", cut_off)
    with pytest.raises(stop):
        run.run_ffmpeg(step, plan, generate_dummy_core_payload())
    assert not step.output.exists()


def test_a_finished_ffmpeg_run_keeps_its_wav(tmp_path, monkeypatch):
    step, plan = ffmpeg_job(tmp_path)
    monkeypatch.setattr(
        run, "process_ffmpeg_job", lambda **_kw: step.output.write_bytes(b"RIFF")
    )
    run.run_ffmpeg(step, plan, generate_dummy_core_payload())
    assert step.output.read_bytes() == b"RIFF"


@pytest.mark.parametrize("stop", [KeyboardInterrupt, RuntimeError])
def test_a_stopped_decode_deletes_its_damf_and_nothing_else(
    tmp_path, monkeypatch, stop
):
    step = TruehddStep(
        file_input=tmp_path / "in.mkv",
        track_index=TrackIndex.audio(0),
        ffmpeg=Path("ffmpeg"),
        truehdd=Path("truehdd"),
        warp_mode=WarpMode.NORMAL,
        output_dir=tmp_path,
    )
    other = tmp_path / "keep.wav"
    other.write_bytes(b"RIFF")

    def cut_off(**_kwargs):
        for path in run.damf_files(step.output):
            path.write_bytes(b"part")
        raise stop

    monkeypatch.setattr(run, "decode_truehd_to_atmos", cut_off)
    with pytest.raises(stop):
        run.run_truehdd(step, generate_dummy_core_payload())
    assert [p.exists() for p in run.damf_files(step.output)] == [False] * 3
    assert other.exists()


# --- the measure manifest


def test_an_interrupted_manifest_save_leaves_no_partial(tmp_path, monkeypatch):
    temp = tmp_path / "temp"
    dee = DeeStep(argv=("dee_measure_loudness",), output=temp / "loudness.json")
    out = tmp_path / "in.loudness.json"
    plan = JobPlan(
        format="measure",
        source=tmp_path / "in.mkv",
        output=out,
        temp_dir=temp,
        steps=(dee,),
        free_space_needed=1,
    )

    def dee_writes(plan, _payload):
        dee.output.write_text(json.dumps({"loudness_manifest": {}}), encoding="utf-8")
        return dee.output

    def interrupted(_src, _dst):
        raise KeyboardInterrupt

    monkeypatch.setattr(run, "run_steps", dee_writes)
    monkeypatch.setattr(run.os, "replace", interrupted)
    payload = generate_dummy_core_payload()
    payload.overwrite = False
    with pytest.raises(KeyboardInterrupt):
        run.run_measure(plan, payload)
    assert not out.exists()
    assert partials(tmp_path) == []
