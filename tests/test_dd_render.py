"""dd and ddp from an Atmos master: DEE renders it, with no FFmpeg step."""

from pathlib import Path
from typing import cast
from unittest.mock import patch

from pymediainfo import Track
import pytest

import deezy.cli as cli
from deezy.exceptions import (
    ChannelMixError,
    InvalidAtmosInputError,
    UnsupportedDeeFeatureError,
)
from deezy.pipeline.plan import DeeStep, FfmpegStep, PlanContext, plan_job
from deezy.track_info.audio_track_info import AudioTrackInfo

BUILDERS = {
    "dd": cli.PayloadBuilder.build_dd_payload,
    "ddp": cli.PayloadBuilder.build_ddp_payload,
    "ddp-bluray": cli.PayloadBuilder.build_ddp_payload,
}
SUFFIX = {"dd": ".ac3", "ddp": ".ec3", "ddp-bluray": ".ec3"}


@pytest.fixture
def parser():
    main = cli.create_main_parser()
    sub = main.add_subparsers(dest="sub_command")
    cli.create_encode_parsers(sub, cli.create_common_argument_groups())
    return main


def track(**probed) -> AudioTrackInfo:
    fields = {"channels": 16, "delay_relative_to_video": 0, "sample_rate": 48000}
    fields |= {"fps": 24, "duration": 1000.0, "damf_atmos": True}
    return AudioTrackInfo(mi_track=cast("Track", None), **{**fields, **probed})


def plan(parser, tmp_path, fmt, *args, source="in.atmos", **probed):
    ns = parser.parse_args(["encode", fmt, *args, source])
    payload = BUILDERS[fmt](ns, Path(source), Path("ffmpeg"), None, Path("dee"))
    payload.file_output = tmp_path / f"out{SUFFIX[fmt]}"
    ctx = PlanContext(namer=cast("cli.OutputNamer", None), temp_dir=tmp_path)
    return plan_job(payload, track(**probed), ctx)


def logged(parser, tmp_path, fmt, *args) -> list[str]:
    with patch("deezy.pipeline.plan.logger") as log:
        plan(parser, tmp_path, fmt, *args)
    return [call.args[0] for call in log.info.call_args_list]


def value(argv, option: str) -> str:
    return argv[argv.index(option) + 1]


@pytest.mark.parametrize("fmt", ["dd", "ddp"])
@pytest.mark.parametrize(
    ("probed", "source"),
    [({"damf_atmos": True}, "in.atmos"), ({"adm_atmos_wav": True}, "in.wav")],
)
def test_a_master_goes_to_dee_as_it_is(parser, tmp_path, fmt, probed, source):
    job = plan(parser, tmp_path, fmt, source=source, **probed)
    (dee,) = job.steps
    assert isinstance(dee, DeeStep)
    assert value(dee.argv, "-i") == source
    assert value(dee.argv, "--input-format") == "atmos_mezz"


@pytest.mark.parametrize("fmt", ["dd", "ddp"])
def test_auto_renders_51(parser, tmp_path, fmt):
    lines = logged(parser, tmp_path, fmt)
    assert "No supplied channels, defaulting to 5.1." in lines
    assert "DEE renders the DAMF master to 5.1." in lines


@pytest.mark.parametrize("fmt", ["dd", "ddp"])
def test_a_truehd_atmos_stream_is_decoded_by_ffmpeg(parser, tmp_path, fmt):
    """The stream's own 7.1 presentation, as before: it is not a master."""
    job = plan(
        parser, tmp_path, fmt, source="in.mkv", channels=8, damf_atmos=False,
        thd_atmos=True,
    )  # fmt: skip
    ffmpeg, dee = job.steps
    assert isinstance(ffmpeg, FfmpegStep)
    assert value(dee.argv, "--input-format") == "wav"


def test_ddp_71_from_a_master_is_refused(parser, tmp_path):
    with pytest.raises(ChannelMixError, match="5.1 at most"):
        plan(parser, tmp_path, "ddp", "--channels", "8")


def test_ddp_bluray_refuses_a_master(parser, tmp_path):
    with pytest.raises(InvalidAtmosInputError, match="Blu-ray 7.1 mode"):
        plan(parser, tmp_path, "ddp-bluray")


@pytest.mark.parametrize("fmt", ["dd", "ddp"])
@pytest.mark.parametrize("mix", ["ltrt", "dpl2"])
def test_a_stereo_render_takes_no_downmix_mode(parser, tmp_path, fmt, mix):
    with pytest.raises(UnsupportedDeeFeatureError, match=f"--stereo-down-mix {mix}"):
        plan(parser, tmp_path, fmt, "--channels", "2", "--stereo-down-mix", mix)


def test_dd_dpl2_on_a_51_render_is_marked_ltrt(parser, tmp_path):
    job = plan(parser, tmp_path, "dd", "--stereo-down-mix", "dpl2")
    assert "preferred_downmix_mode=ltrt" in value(job.steps[0].argv, "-e")


def test_pipe_always_has_nothing_to_pipe(parser, tmp_path):
    lines = logged(parser, tmp_path, "ddp", "--pipe", "always")
    assert any("--pipe always" in line for line in lines)
