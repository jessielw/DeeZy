"""DeeZy finding and running the real dee_shim, and reading its failures."""

from pathlib import Path

import pytest

from deezy.audio_processors.dee import process_dee_job
from deezy.dee.shim import DeeShim, resolve_shim

from .harness import noise_wav


@pytest.fixture(scope="module")
def dee_shim(shim) -> DeeShim:
    found = resolve_shim(Path(), None, shim.shim)
    assert found is not None
    return found


@pytest.fixture(scope="module")
def wav(work) -> Path:
    return noise_wav(work / "shim_noise71.wav", 8, seconds=1.0)


def ddp_argv(shim, work, wav, out: str) -> list[str]:
    return [
        str(shim.tool("dee_ddp_encoder")), *map(str, shim.license_args()),
        "--overwrite", "1", "--loglevel", "info", "--progress", "1",
        "--input-format", "wav", "-i", str(wav), "-o", str(work / out),
        "--temp-dir", str(work), "--loudness-management", "measure_only",
    ]  # fmt: skip


def run(argv, *shim_args, shim: DeeShim):
    return process_dee_job(list(shim.argv(argv, *shim_args)), no_progress_bars=True)


def test_deezy_reads_the_shims_version(dee_shim):
    assert dee_shim.version.startswith("0.2.1")


def test_a_run_through_the_shim(shim, work, wav, dee_shim):
    argv = ddp_argv(shim, work, wav, "shim_ok.ec3")
    assert run(argv, "--layout", "7.1/eac3", shim=dee_shim)
    assert (work / "shim_ok.ec3").stat().st_size > 0


def test_a_refused_job_says_why(shim, work, wav, dee_shim):
    argv = ddp_argv(shim, work, wav, "shim_rate.ec3")
    with pytest.raises(ValueError, match="dee_shim refused the job: --bitrate 123"):
        run(argv, "--layout", "7.1/eac3", "--bitrate", "123", shim=dee_shim)


def test_a_dee_build_without_a_profile(shim, work, wav, dee_shim):
    argv = ddp_argv(shim, work, wav, "shim_build.ec3")
    argv[0] = str(shim.ffmpeg)
    with pytest.raises(ValueError, match="doesn't support this DEE build"):
        process_dee_job(
            [str(dee_shim.path), "ddp_encoder", "--layout", "7.1/eac3", "--binary",
             str(shim.ffmpeg), "--", *argv[1:]],
            no_progress_bars=True,
        )  # fmt: skip


def test_deees_own_failure_passes_through(shim, work, dee_shim):
    argv = ddp_argv(shim, work, work / "missing.wav", "shim_missing.ec3")
    with pytest.raises(ValueError, match="DEE execution failed:"):
        run(argv, "--layout", "7.1/eac3", shim=dee_shim)


def test_the_shims_environment_is_kept_out(shim, work, wav, dee_shim, monkeypatch):
    """RUST_LOG=debug would put dee_shim's debug lines into DEE's output."""
    import deezy.audio_processors.dee as runner

    monkeypatch.setenv("RUST_LOG", "debug")
    lines: list[str] = []
    monkeypatch.setattr(runner.logger, "debug", lambda line, *_: lines.append(line))
    argv = ddp_argv(shim, work, wav, "shim_env.ec3")
    assert run(argv, "--layout", "7.1/eac3", shim=dee_shim)
    assert lines, "DEE's output was not logged"
    assert not any("dee_shim DEBUG" in line for line in lines)
