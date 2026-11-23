"""FFmpeg piped into DEE: the transport choice, the command lines, and which
failure a pipe job reports. Fake processes stand in for DEE and FFmpeg."""

import argparse
import subprocess
import sys
import time

import pytest

from deezy.audio_processors import pipe
from deezy.cli.utils import apply_config_defaults_to_args
from deezy.enums.shared import PipeMode
from deezy.exceptions import PipeError
from deezy.pipeline import run
from deezy.pipeline.plan import (
    DeeStep,
    JobPlan,
    PipeStep,
    PlanContext,
    choose_transport,
)
from deezy.pipeline.show import command_lines, shell_line, step_lines
from deezy.pipeline.transport import NamedPipe, WavFile, expected_samples
from tests.utils.payload_helpers import generate_dummy_core_payload


def payload(mode: PipeMode, reuse: bool = False):
    p = generate_dummy_core_payload()
    p.pipe = mode
    p.reuse_temp_files = reuse
    return p


def ctx(tmp_path, pipe_name: str | None = "deezy-1-job") -> PlanContext:
    return PlanContext(namer=None, temp_dir=tmp_path, pipe_name=pipe_name)  # type: ignore[arg-type]


# --- choosing the transport


@pytest.mark.parametrize("mode", [PipeMode.AUTO, PipeMode.ALWAYS])
def test_pipes_where_it_can(tmp_path, mode):
    transport = choose_transport(payload(mode), ctx(tmp_path), tmp_path / "x.wav", 6)
    assert transport == NamedPipe("deezy-1-job", 6)


def test_pipe_counts_the_samples_of_a_known_length(tmp_path):
    transport = choose_transport(
        payload(PipeMode.AUTO), ctx(tmp_path), tmp_path / "x.wav", 2, 3000.0
    )
    assert transport == NamedPipe("deezy-1-job", 2, expected_samples(3000.0))


@pytest.mark.parametrize(
    ("duration_ms", "count"),
    # MediaInfo's milliseconds, plus 1% and a second at 48 kHz
    [(3000.0, 145_440 + 48_000), (1.0, 49 + 48_000), (None, None), (0.0, None)],
)
def test_expected_samples(duration_ms, count):
    assert expected_samples(duration_ms) == count


def test_never_writes_the_wav(tmp_path):
    wav = tmp_path / "x.wav"
    assert choose_transport(payload(PipeMode.NEVER), ctx(tmp_path), wav, 6) == (
        WavFile(wav)
    )


@pytest.mark.parametrize(("pipe_name", "reuse"), [(None, False), ("deezy-1-job", True)])
def test_auto_falls_back_to_the_wav(tmp_path, pipe_name, reuse):
    wav = tmp_path / "x.wav"
    chosen = choose_transport(
        payload(PipeMode.AUTO, reuse), ctx(tmp_path, pipe_name), wav, 6
    )
    assert chosen == WavFile(wav)


@pytest.mark.parametrize(
    ("pipe_name", "reuse", "reason"),
    [(None, False, "only on Windows"), ("deezy-1-job", True, "--reuse-temp-files")],
)
def test_always_refuses_where_it_cant_pipe(tmp_path, pipe_name, reuse, reason):
    with pytest.raises(PipeError, match=reason):
        choose_transport(
            payload(PipeMode.ALWAYS, reuse),
            ctx(tmp_path, pipe_name),
            tmp_path / "x.wav",
            6,
        )


def test_named_pipe_tells_dee_the_raw_format():
    named = NamedPipe("deezy-1-job", 8)
    assert named.path == "\\\\.\\pipe\\deezy-1-job"
    assert named.ffmpeg_output() == ["-f", "s24le", named.path]
    assert named.dee_input == "named_pipe://\\\\.\\pipe\\deezy-1-job"
    assert named.dee_input_format == (
        "pcm_s24le:sample_rate=48000:channels=8:streaming=1"
    )
    assert named.frame_bytes == 24


def test_named_pipe_tells_dee_its_sample_count():
    assert NamedPipe("deezy-1-job", 2, 1000).dee_input_format == (
        "pcm_s24le:sample_rate=48000:channels=2:sample_count=1000:streaming=1"
    )


# --- the config key


def namespace(**kwargs) -> argparse.Namespace:
    return argparse.Namespace(jitter_ms=0, output_template="x", **kwargs)


class FakeConfig:
    def __init__(self, **values):
        self.values = values

    def get_config_default(self, key):
        return self.values.get(key)


def test_config_pipe_fills_a_missing_option():
    args = namespace(pipe=None)
    apply_config_defaults_to_args(args, FakeConfig(pipe="Never"))
    assert args.pipe is PipeMode.NEVER


def test_option_beats_config():
    args = namespace(pipe=PipeMode.ALWAYS)
    apply_config_defaults_to_args(args, FakeConfig(pipe="never"))
    assert args.pipe is PipeMode.ALWAYS


def test_bad_config_pipe_is_ignored():
    args = namespace(pipe=None)
    apply_config_defaults_to_args(args, FakeConfig(pipe="sometimes"))
    assert args.pipe is None


def test_formats_without_the_option_get_none():
    args = namespace()
    apply_config_defaults_to_args(args, FakeConfig(pipe="always"))
    assert not hasattr(args, "pipe")


# --- the command lines


def pipe_step(tmp_path) -> PipeStep:
    named = NamedPipe("deezy-1-job", 6)
    dee = DeeStep(
        argv=("dee_ddp_encoder", "--loglevel", "info", "-i", named.dee_input),
        output=tmp_path / "x.ec3",
    )
    ffmpeg = ("ffmpeg", "-y", "-v", "-i", "in.mkv", *named.ffmpeg_output())
    return PipeStep(ffmpeg_argv=ffmpeg, dee=dee, pipe=named)


def test_dee_line_comes_before_ffmpeg_line(tmp_path):
    dee_line, ffmpeg_line = step_lines(pipe_step(tmp_path))
    assert dee_line.startswith("dee_ddp_encoder")
    assert ffmpeg_line.startswith("ffmpeg")
    # the pipe path as this platform's shell quotes it
    assert ffmpeg_line.endswith(shell_line([NamedPipe("deezy-1-job", 6).path]))


def test_dry_run_lists_both_lines(tmp_path):
    step = pipe_step(tmp_path)
    plan = JobPlan("ddp", tmp_path / "in.mkv", tmp_path / "o.ec3", tmp_path, (step,))
    assert command_lines(plan) == step_lines(step)


# --- which failure a pipe job reports

PY = sys.executable


def py(code: str) -> list[str]:
    # '-v' takes FFmpeg's log level and '-i' its progress options; the script
    # ignores both
    return [PY, "-c", code, "-v", "-i", "in.mkv"]


@pytest.fixture
def fake_dee(monkeypatch):
    """Replace DEE with a Python process running ``code``."""
    state = {"code": "pass", "pipe_exists": True}

    def process_dee_job(cmd, on_start=None, **_kwargs):
        with subprocess.Popen([PY, "-c", state["code"]]) as proc:  # noqa: S603
            if on_start:
                on_start(proc)
            rc = proc.wait()
        if rc != 0:
            raise ValueError(f"DEE execution failed with exit code {rc}.")
        return True

    monkeypatch.setattr(pipe, "process_dee_job", process_dee_job)
    monkeypatch.setattr(pipe, "pipe_exists", lambda _name: state["pipe_exists"])
    return state


def run_job(ffmpeg_code: str) -> None:
    pipe.process_pipe_job(["dee"], py(ffmpeg_code), "deezy-1-job")


def test_both_succeed(fake_dee):
    fake_dee["code"] = "import time; time.sleep(0.3)"
    run_job("pass")


def test_returns_what_ffmpeg_reported_writing(fake_dee):
    fake_dee["code"] = "import time; time.sleep(0.3)"
    report = (
        "import sys; assert sys.argv[3:6] == ['-progress', 'pipe:1', '-nostats']; "
        "print('Stream mapping:'); print('total_size=10'); "
        "print('out_time_us=5'); print('total_size=4096'); print('progress=end')"
    )
    written = pipe.process_pipe_job(["dee"], py(report), "deezy-1-job")
    assert written == 4096


def test_progress_lines_stay_out_of_ffmpeg_error(fake_dee):
    fake_dee["code"] = "pass"
    with pytest.raises(PipeError) as err:
        run_job(
            "print('total_size=1'); print('Conversion failed!'); raise SystemExit(1)"
        )
    assert "Conversion failed!" in str(err.value)
    assert "total_size" not in str(err.value)


def test_ffmpeg_failing_ends_a_waiting_dee(fake_dee):
    fake_dee["code"] = "import time; time.sleep(30)"
    start = time.monotonic()
    with pytest.raises(PipeError, match="FFMPEG error \\(exit code 3\\)") as err:
        run_job("raise SystemExit(3)")
    assert time.monotonic() - start < 15
    assert isinstance(err.value.__cause__, ValueError)


def test_ffmpeg_failing_fails_a_dee_that_finished(fake_dee):
    # DEE closes a short stream cleanly, so its success can't be trusted
    fake_dee["code"] = "pass"
    with pytest.raises(PipeError, match="exit code 1"):
        run_job("import time; time.sleep(0.5); raise SystemExit(1)")


def test_dee_failing_on_its_own_reports_dee(fake_dee):
    fake_dee["code"] = "raise SystemExit(2)"
    fake_dee["pipe_exists"] = False
    with pytest.raises(ValueError, match="exit code 2"):
        run_job("raise AssertionError('FFmpeg must not start')")


def test_dee_finishing_without_a_writer_fails(fake_dee):
    fake_dee["code"] = "pass"
    fake_dee["pipe_exists"] = False
    with pytest.raises(PipeError, match="without FFmpeg"):
        run_job("pass")


def test_run_pipe_deletes_the_partial_output(tmp_path, monkeypatch):
    step = pipe_step(tmp_path)
    step.dee.output.write_bytes(b"short")

    def failing(**_kwargs):
        raise PipeError("FFMPEG error")

    monkeypatch.setattr(run, "process_pipe_job", failing)
    run.init_phase_limits(max_parallel=1)
    with pytest.raises(PipeError):
        run.run_pipe(step, no_progress_bars=True)
    assert not step.dee.output.exists()


def counted_step(tmp_path, count: int | None) -> PipeStep:
    named = NamedPipe("deezy-1-job", 2, count)
    dee = DeeStep(
        argv=("dee_ddp_encoder", "--input-format", named.dee_input_format),
        output=tmp_path / "x.ec3",
    )
    return PipeStep(("ffmpeg", "-v", "-i", "in.mkv"), dee, named)


@pytest.fixture
def pipe_runs(monkeypatch):
    """Replace the pipe job; each call records DEE's input format."""
    state = {"written": None, "formats": []}

    def fake(dee_cmd, **_kwargs):
        state["formats"].append(dee_cmd[dee_cmd.index("--input-format") + 1])
        return state["written"]

    monkeypatch.setattr(run, "process_pipe_job", fake)
    run.init_phase_limits(max_parallel=1)
    return state


@pytest.mark.parametrize(
    ("count", "written"),
    # 6 bytes is one sample of 2 channels
    [(100, 100 * 6), (100, 50 * 6), (None, None), (None, 10**9)],
)
def test_run_pipe_encodes_once_when_dee_read_everything(
    tmp_path, pipe_runs, count, written
):
    pipe_runs["written"] = written
    run.run_pipe(counted_step(tmp_path, count), no_progress_bars=True)
    assert len(pipe_runs["formats"]) == 1


@pytest.mark.parametrize("written", [101 * 6, None])
def test_run_pipe_encodes_again_when_dee_stopped_short(tmp_path, pipe_runs, written):
    pipe_runs["written"] = written
    run.run_pipe(counted_step(tmp_path, 100), no_progress_bars=True)
    assert pipe_runs["formats"] == [
        "pcm_s24le:sample_rate=48000:channels=2:sample_count=100:streaming=1",
        "pcm_s24le:sample_rate=48000:channels=2:streaming=1",
    ]


def test_run_pipe_holds_a_dee_and_an_ffmpeg_slot(tmp_path, monkeypatch):
    held = []

    def check(**_kwargs):
        # both one-slot semaphores are taken while the pipe runs
        held.append(
            (
                run._Limits.dee.acquire(blocking=False),
                run._Limits.ffmpeg.acquire(blocking=False),
            )
        )

    monkeypatch.setattr(run, "process_pipe_job", check)
    run.init_phase_limits(max_parallel=1)
    run.run_pipe(pipe_step(tmp_path), no_progress_bars=True)
    assert held == [(False, False)]
