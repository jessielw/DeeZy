"""--dry-run prints a plan's command lines and runs nothing; --print-commands
prints each one as it starts."""

import logging
from pathlib import Path

import pytest

from deezy.enums.atmos import WarpMode
from deezy.pipeline import encode as encode_mod, run
from deezy.pipeline.plan import DeeStep, FfmpegStep, JobPlan, TruehddStep
from deezy.pipeline.show import command_lines, shell_line, step_line
from deezy.track_info.track_index import TrackIndex
from deezy.utils.logger import logger
from tests.utils.payload_helpers import generate_dummy_core_payload


@pytest.fixture(autouse=True)
def info_level(monkeypatch):
    monkeypatch.setattr(logger, "level", logging.INFO)


def ffmpeg_step(tmp_path: Path) -> FfmpegStep:
    argv = ("ffmpeg", "-y", "-v", "-i", "in put.mkv", str(tmp_path / "job.wav"))
    return FfmpegStep(argv=argv, output=tmp_path / "job.wav", reuse_id="ddp")


def dee_step(tmp_path: Path) -> DeeStep:
    argv = ("dee_ddp_encoder", "--loglevel", "info", "-o", str(tmp_path / "x.ec3"))
    return DeeStep(argv=argv, output=tmp_path / "x.ec3")


def job(tmp_path: Path, *steps) -> JobPlan:
    return JobPlan(
        format="ddp",
        source=tmp_path / "in.mkv",
        output=tmp_path / "final.ec3",
        temp_dir=tmp_path / "temp",
        steps=steps,
    )


def test_ffmpeg_line_has_its_log_level_and_no_progress_options(tmp_path):
    line = step_line(ffmpeg_step(tmp_path))
    assert line == shell_line(
        ["ffmpeg", "-y", "-v", "error", "-i", "in put.mkv", str(tmp_path / "job.wav")]
    )


def test_truehdd_line_pipes_ffmpeg_into_truehdd(tmp_path):
    step = TruehddStep(
        file_input=Path("in.mkv"),
        track_index=TrackIndex.audio(1),
        ffmpeg=Path("ffmpeg"),
        truehdd=Path("truehdd"),
        warp_mode=WarpMode.LORO,
        output_dir=tmp_path,
    )
    extract, decode = step_line(step).split(" | ")
    assert "0:a:1" in extract
    assert extract.endswith("-f truehd - -v error -stats")
    assert "--warp-mode loro" in decode
    assert decode.endswith(" -")


def test_dry_run_prints_every_command_and_runs_nothing(tmp_path, monkeypatch, capsys):
    plan = job(tmp_path, ffmpeg_step(tmp_path), dee_step(tmp_path))
    monkeypatch.setattr(encode_mod, "plan", lambda _payload: plan)

    def must_not_run(*_args):
        raise AssertionError("a dry run ran the plan")

    monkeypatch.setattr(encode_mod, "run_plan", must_not_run)
    payload = generate_dummy_core_payload()
    payload.dry_run = True

    assert encode_mod.encode(payload) == plan.output
    assert capsys.readouterr().out.splitlines() == command_lines(plan)
    assert not plan.temp_dir.exists()


def test_print_commands_prints_the_line_as_the_step_starts(
    tmp_path, monkeypatch, capsys
):
    step = dee_step(tmp_path)
    printed_first = []

    def fake_dee(**_kwargs):
        printed_first.append(capsys.readouterr().out)
        return True

    monkeypatch.setattr(run, "process_dee_job", fake_dee)
    run.init_phase_limits(max_parallel=1)
    run.run_dee(step, no_progress_bars=True, print_commands=True)
    assert printed_first == [step_line(step) + "\n"]


def test_without_print_commands_nothing_is_printed(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(run, "process_dee_job", lambda **_kwargs: True)
    run.init_phase_limits(max_parallel=1)
    run.run_dee(dee_step(tmp_path), no_progress_bars=True)
    assert capsys.readouterr().out == ""
