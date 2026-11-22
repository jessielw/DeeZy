"""--keep-logs: a job's command lines and tool output, beside its output, when it fails too."""

import logging
from pathlib import Path

import pytest

from deezy.audio_processors import dee, ffmpeg, pipe, truehdd
import deezy.cli as cli
from deezy.pipeline import encode as encode_mod, run
from deezy.pipeline.plan import DeeStep, FfmpegStep, JobPlan
from deezy.track_info.track_index import TrackIndex
from deezy.utils.tool_log import ToolLog, log_path
from tests.utils.payload_helpers import generate_dummy_core_payload


@pytest.fixture(autouse=True)
def limits() -> None:
    run.init_phase_limits(max_parallel=1)


@pytest.fixture
def info_level(monkeypatch):
    for module in (ffmpeg, truehdd):
        monkeypatch.setattr(module.logger, "getEffectiveLevel", lambda: logging.INFO)


def test_the_log_tags_each_line_and_drops_empty_ones(tmp_path):
    log = ToolLog()
    log.command("dee_ddp_encoder -i x")
    log.add("dee", "Exit code: 0")
    log.add("ffmpeg", "")
    path = tmp_path / "out.ec3.log"
    log.write(path)
    assert path.read_text(encoding="utf-8").splitlines() == [
        "$ dee_ddp_encoder -i x",
        "[dee] Exit code: 0",
    ]


def test_the_log_goes_beside_the_output_and_is_named_after_it(tmp_path):
    assert log_path(tmp_path / "Movie [5.1].ec3") == tmp_path / "Movie [5.1].ec3.log"


# --- tool levels and filters


def test_ffmpeg_runs_at_info_while_its_log_is_kept(info_level):
    cmd = ["ffmpeg", "-v", "-i", "in.wav"]
    assert ffmpeg.with_loglevel(cmd) == ["ffmpeg", "-v", "quiet", "-i", "in.wav"]
    assert ffmpeg.with_loglevel(cmd, keep_logs=True)[2] == "info"


def test_the_truehd_extract_runs_at_warning_while_its_log_is_kept(info_level):
    def level(keep_logs: bool) -> str:
        cmd = truehdd.truehd_extract_command(
            Path("ffmpeg"), Path("in.mkv"), TrackIndex.audio(0), keep_logs
        )
        return cmd[cmd.index("-v") + 1]

    assert (level(False), level(True)) == ("quiet", "warning")


@pytest.mark.parametrize(
    ("line", "progress"),
    [
        ("[>                                       ] 1 %", True),
        ("[=====================>                  ] 54.5 %", True),
        ("[2026-11-22 16:07:47.552] Step 1/2 : Loudness Measurement", False),
        ("[2026-11-22 16:07:47.761] [Source loudness] measured_loudness=-8.0", False),
        ("Exit code: 0", False),
    ],
)
def test_only_dee_progress_bars_are_left_out(line, progress):
    assert dee._is_progress(line) is progress


def test_ffmpeg_stats_ticks_are_left_out_of_the_truehdd_log():
    tick = "size=    4525kB time=00:00:10.18 bitrate=3640.3kbits/s speed=20.4x"
    assert truehdd._FFMPEG_STATS.match(tick)
    assert not truehdd._FFMPEG_STATS.match("Error while decoding stream #0:0")


def test_a_piping_ffmpeg_logs_all_but_its_progress_report():
    log = ToolLog()
    feeder = pipe._Feeder(["ffmpeg"], "deezy-1-job", log)
    feeder._read("total_size=1024")
    feeder._read("progress=continue")
    feeder._read("Stream mapping:")
    assert log.lines == ["[ffmpeg] Stream mapping:"]
    assert feeder.written == 1024


# --- run_plan


def job(tmp_path: Path) -> JobPlan:
    temp = tmp_path / "temp"
    wav = FfmpegStep(
        argv=("ffmpeg", "-y", "-v", "-i", "in.wav", str(temp / "job.wav")),
        output=temp / "job.wav",
        reuse_id="ddp",
    )
    encode = DeeStep(
        argv=("dee_ddp_encoder", "--loglevel", "info", "-o", str(temp / "x.ec3")),
        output=temp / "x.ec3",
    )
    return JobPlan(
        format="ddp",
        source=tmp_path / "in.wav",
        output=tmp_path / "Movie.ec3",
        temp_dir=temp,
        steps=(wav, encode),
        free_space_needed=1,
    )


@pytest.fixture
def tools(monkeypatch):
    """FFmpeg and DEE stand-ins that print a line into the log they are given."""
    seen = {}

    def ffmpeg_job(*, log=None, **_kwargs):
        seen["ffmpeg"] = log
        if log is not None:
            log.add("ffmpeg", "Stream mapping:")
        return True

    def dee_job(*, cmd, log=None, **_kwargs):
        seen["dee"] = log
        if seen.get("fail"):
            raise ValueError("DEE execution failed")
        Path(cmd[cmd.index("-o") + 1]).write_bytes(b"\x0b\x77")
        if log is not None:
            log.add("dee", "Exit code: 0")
        return True

    monkeypatch.setattr(run, "process_ffmpeg_job", ffmpeg_job)
    monkeypatch.setattr(run, "process_dee_job", dee_job)
    return seen


def payload(keep_logs: bool, overwrite: bool = True):
    p = generate_dummy_core_payload()
    p.keep_logs = keep_logs
    p.overwrite = overwrite
    p.no_progress_bars = True
    p.print_commands = False
    return p


def test_a_kept_log_has_the_job_its_commands_and_its_tools(tmp_path, tools, info_level):
    plan = job(tmp_path)
    run.run_plan(plan, payload(keep_logs=True))
    lines = log_path(plan.output).read_text(encoding="utf-8").splitlines()
    assert lines[0] == f"[deezy] ddp: {plan.source} -> {plan.output}"
    assert lines[1].startswith("$ ffmpeg -y -v info -i in.wav")
    assert lines[2] == "[ffmpeg] Stream mapping:"
    assert lines[3].startswith("$ dee_ddp_encoder --loglevel info")
    assert lines[4:] == ["[dee] Exit code: 0"]


def test_a_failed_job_keeps_its_log_and_says_why(tmp_path, tools):
    tools["fail"] = True
    plan = job(tmp_path)
    with pytest.raises(ValueError, match="DEE execution failed"):
        run.run_plan(plan, payload(keep_logs=True))
    assert not plan.output.exists()
    lines = log_path(plan.output).read_text(encoding="utf-8").splitlines()
    assert lines[-1] == "[deezy] failed: ValueError: DEE execution failed"


def test_without_keep_logs_no_log_is_written_or_given(tmp_path, tools):
    plan = job(tmp_path)
    run.run_plan(plan, payload(keep_logs=False))
    assert plan.output.exists()
    assert not log_path(plan.output).exists()
    assert tools["ffmpeg"] is None
    assert tools["dee"] is None


def test_a_skipped_job_leaves_the_earlier_log_alone(tmp_path, tools):
    plan = job(tmp_path)
    plan.output.write_bytes(b"old")
    log_path(plan.output).write_text("earlier run", encoding="utf-8")
    with pytest.raises(run.OutputExistsError):
        run.run_plan(plan, payload(keep_logs=True, overwrite=False))
    assert log_path(plan.output).read_text(encoding="utf-8") == "earlier run"


# --- the option


def test_keep_logs_is_an_encode_option():
    main = cli.create_main_parser()
    sub = main.add_subparsers(dest="sub_command")
    cli.create_encode_parsers(sub, cli.create_common_argument_groups())
    assert main.parse_args(["encode", "ddp", "--keep-logs", "a.wav"]).keep_logs
    assert not main.parse_args(["encode", "ddp", "a.wav"]).keep_logs


def test_a_dry_run_shows_ffmpeg_at_the_level_a_kept_log_runs_it(
    tmp_path, monkeypatch, capsys, info_level
):
    plan = job(tmp_path)
    monkeypatch.setattr(encode_mod, "plan", lambda _payload: plan)
    p = payload(keep_logs=True)
    p.dry_run = True
    encode_mod.encode(p)
    assert " -v info " in capsys.readouterr().out.splitlines()[0]
