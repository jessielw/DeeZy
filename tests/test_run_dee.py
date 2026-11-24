"""The DEE step: a failed run leaves no partial encode and returns its slot."""

from pathlib import Path
import sys

import pytest

from deezy.pipeline import run
from deezy.pipeline.plan import DeeStep

LIMIT = 2


@pytest.fixture(autouse=True)
def limits() -> None:
    run.init_phase_limits(max_parallel=LIMIT, dee_limit=LIMIT)


def free_slots() -> int:
    sem = run._Limits.dee
    assert sem is not None
    taken = 0
    while taken <= LIMIT and sem.acquire(blocking=False):
        taken += 1
    for _ in range(taken):
        sem.release()
    return taken


def test_a_failed_run_deletes_its_partial_output(tmp_path, monkeypatch):
    partial = tmp_path / "job.ec3"

    def fail(**_kwargs):
        partial.write_bytes(b"")  # DEE leaves a 0-byte file when it fails
        raise ValueError("DEE execution failed")

    monkeypatch.setattr(run, "process_dee_job", fail)
    with pytest.raises(ValueError, match="DEE execution failed"):
        run.run_dee(DeeStep(("dee_ddp_encoder",), partial), no_progress_bars=True)
    assert not partial.exists()
    assert free_slots() == LIMIT


@pytest.mark.parametrize("summary", [False, True])
def test_a_dee_permission_failure_shows_the_reported_path_and_temp_dir(
    tmp_path, summary
):
    diagnostic = 'Access denied opening "/share/audio.wav".'
    lines = [diagnostic] + ["INFO: Shutting down."] * 10 + ["[==>   ] 10 %"]
    if summary:
        lines += ["---- Summary of errors and warnings ----", "ERROR: Encode failed."]
    output = "\n".join(lines)
    script = f"import sys; print({output!r}, file=sys.stderr); sys.exit(2)"
    step = DeeStep(
        (sys.executable, "-c", script, "--loglevel", "info"), tmp_path / "job.ec3"
    )

    with pytest.raises(ValueError) as failure:
        run.run_dee(step, no_progress_bars=True)

    message = str(failure.value)
    assert f"{Path(sys.executable).name} (exit code 2)" in message
    assert diagnostic in message
    assert str(tmp_path) in message
    assert "SMB/CIFS" in message
    assert "Shutting down" not in message
    assert "[==>" not in message


def test_a_good_run_keeps_its_output(tmp_path, monkeypatch):
    out = tmp_path / "job.ec3"

    def succeed(**_kwargs):
        out.write_bytes(b"\x0b\x77")
        return True

    monkeypatch.setattr(run, "process_dee_job", succeed)
    run.run_dee(DeeStep(("dee_ddp_encoder",), out), no_progress_bars=True)
    assert out.read_bytes() == b"\x0b\x77"
    assert free_slots() == LIMIT


def test_custom_dialnorm_reaches_the_progress_display(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(run, "process_dee_job", lambda **kw: seen.update(kw))
    step = DeeStep(("dee_ddp_encoder",), tmp_path / "job.ec3", custom_dialnorm=-27)
    run.run_dee(step, no_progress_bars=True)
    assert seen["custom_dialnorm"] == -27


def test_a_missing_dee_tool_is_named(tmp_path):
    from deezy.exceptions import DependencyNotFoundError

    tool = tmp_path / "dee_dthd_encoder.exe"
    step = DeeStep((str(tool), "--loglevel", "info"), tmp_path / "job.thd")
    with pytest.raises(DependencyNotFoundError, match="without the TrueHD encoder"):
        run.run_dee(step, no_progress_bars=True)
