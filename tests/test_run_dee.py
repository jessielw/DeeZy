"""The DEE step: a failed run leaves no partial encode and returns its slot."""


import pytest

from deezy.audio_encoders.dee import base
from deezy.audio_encoders.dee.base import BaseDeeAudioEncoder
from tests.test_phase_staggering import DummyEncoder
from tests.utils.payload_helpers import generate_dummy_core_payload

LIMIT = 2


@pytest.fixture
def encoder() -> DummyEncoder:
    BaseDeeAudioEncoder.init_phase_limits(max_parallel=LIMIT, dee_limit=LIMIT)
    return DummyEncoder(generate_dummy_core_payload())


def free_slots() -> int:
    sem = BaseDeeAudioEncoder._dee_sem
    assert sem is not None
    taken = 0
    while taken <= LIMIT and sem.acquire(blocking=False):
        taken += 1
    for _ in range(taken):
        sem.release()
    return taken


def test_a_failed_run_deletes_its_partial_output(encoder, tmp_path, monkeypatch):
    partial = tmp_path / "job.ec3"

    def fail(**_kwargs):
        partial.write_bytes(b"")  # DEE leaves a 0-byte file when it fails
        raise ValueError("DEE execution failed")

    monkeypatch.setattr(base, "process_dee_job", fail)
    with pytest.raises(ValueError, match="DEE execution failed"):
        encoder._run_dee(["dee_ddp_encoder"], partial)
    assert not partial.exists()
    assert free_slots() == LIMIT


def test_a_good_run_keeps_its_output(encoder, tmp_path, monkeypatch):
    out = tmp_path / "job.ec3"

    def succeed(**_kwargs):
        out.write_bytes(b"\x0b\x77")
        return True

    monkeypatch.setattr(base, "process_dee_job", succeed)
    encoder._run_dee(["dee_ddp_encoder"], out)
    assert out.read_bytes() == b"\x0b\x77"
    assert free_slots() == LIMIT


def test_custom_dialnorm_reaches_the_progress_display(encoder, tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(base, "process_dee_job", lambda **kw: seen.update(kw))
    encoder._run_dee(["dee_ddp_encoder"], tmp_path / "job.ec3", custom_dialnorm=-27)
    assert seen["custom_dialnorm"] == -27
