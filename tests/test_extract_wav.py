"""The FFmpeg step: errors reach the caller and every FFmpeg slot comes back."""

from pathlib import Path

import pytest

from deezy.audio_encoders.dee import base
from deezy.audio_encoders.dee.base import BaseDeeAudioEncoder
from tests.test_phase_staggering import DummyEncoder
from tests.utils.payload_helpers import generate_dummy_core_payload

LIMIT = 2


@pytest.fixture
def encoder(tmp_path: Path) -> DummyEncoder:
    BaseDeeAudioEncoder.init_phase_limits(max_parallel=LIMIT, ffmpeg_limit=LIMIT)
    enc = DummyEncoder(generate_dummy_core_payload())
    enc.temp_dir = tmp_path
    return enc


def free_slots() -> int:
    """How many FFmpeg slots are free; leaves the semaphore as it found it."""
    sem = BaseDeeAudioEncoder._ffmpeg_sem
    assert sem is not None
    taken = 0
    while taken <= LIMIT and sem.acquire(blocking=False):
        taken += 1
    for _ in range(taken):
        sem.release()
    return taken


def extract(enc: DummyEncoder, tmp_path: Path) -> None:
    enc._extract_wav(
        ["ffmpeg"],
        encoder_id="ddp",
        wav_file_name="job.wav",
        file_input=tmp_path / "in.mkv",
        output=tmp_path / "out.ec3",
        duration=1.0,
    )


def test_ffmpeg_error_is_raised_and_the_slot_returned(encoder, tmp_path, monkeypatch):
    def fail(**_kwargs):
        raise ValueError("FFMPEG error (exit code 1).")

    monkeypatch.setattr(base, "process_ffmpeg_job", fail)
    with pytest.raises(ValueError, match="FFMPEG error"):
        extract(encoder, tmp_path)
    assert free_slots() == LIMIT


def test_a_run_returns_its_slot(encoder, tmp_path, monkeypatch):
    monkeypatch.setattr(base, "process_ffmpeg_job", lambda **_kwargs: True)
    extract(encoder, tmp_path)
    assert free_slots() == LIMIT


def test_reusing_a_wav_takes_no_slot(encoder, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(base, "process_ffmpeg_job", lambda **kw: calls.append(kw))
    encoder.payload.reuse_temp_files = True
    monkeypatch.setattr(encoder, "_check_reuse_signature", lambda *_a: True)

    extract(encoder, tmp_path)
    assert calls == []
    assert free_slots() == LIMIT
