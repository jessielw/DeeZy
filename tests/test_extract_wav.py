"""The FFmpeg step: errors reach the caller and every FFmpeg slot comes back."""

from pathlib import Path

import pytest

from deezy.pipeline import run
from deezy.pipeline.plan import FfmpegStep, JobPlan
from tests.utils.payload_helpers import generate_dummy_core_payload

LIMIT = 2


@pytest.fixture
def job(tmp_path: Path) -> tuple[FfmpegStep, JobPlan]:
    run.init_phase_limits(max_parallel=LIMIT, ffmpeg_limit=LIMIT)
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


def free_slots() -> int:
    """How many FFmpeg slots are free; leaves the semaphore as it found it."""
    sem = run._Limits.ffmpeg
    assert sem is not None
    taken = 0
    while taken <= LIMIT and sem.acquire(blocking=False):
        taken += 1
    for _ in range(taken):
        sem.release()
    return taken


def test_ffmpeg_error_is_raised_and_the_slot_returned(job, monkeypatch):
    def fail(**_kwargs):
        raise ValueError("FFMPEG error (exit code 1).")

    monkeypatch.setattr(run, "process_ffmpeg_job", fail)
    with pytest.raises(ValueError, match="FFMPEG error"):
        run.run_ffmpeg(*job, generate_dummy_core_payload())
    assert free_slots() == LIMIT


def test_a_run_returns_its_slot(job, monkeypatch):
    monkeypatch.setattr(run, "process_ffmpeg_job", lambda **_kwargs: True)
    run.run_ffmpeg(*job, generate_dummy_core_payload())
    assert free_slots() == LIMIT


def test_reusing_a_wav_takes_no_slot(job, monkeypatch):
    calls = []
    monkeypatch.setattr(run, "process_ffmpeg_job", lambda **kw: calls.append(kw))
    monkeypatch.setattr(run, "check_reuse_signature", lambda *_a: True)
    payload = generate_dummy_core_payload()
    payload.reuse_temp_files = True

    run.run_ffmpeg(*job, payload)
    assert calls == []
    assert free_slots() == LIMIT
