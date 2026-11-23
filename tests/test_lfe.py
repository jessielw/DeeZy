"""Sources without an LFE (5.0, 7.0) and --disable-lfe."""

from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

from pymediainfo import Track
import pytest

import deezy.cli as cli
from deezy.dee.commands import DeeFiles, DeeTools, ddp_command
from deezy.delay import Delay
from deezy.enums.dd import DolbyDigitalChannels
from deezy.enums.ddp_bluray import DolbyDigitalPlusBlurayChannels
from deezy.enums.shared import DDEncodingMode, DeeFPS
from deezy.exceptions import ChannelMixError, UnsupportedDeeFeatureError
from deezy.pipeline.plan import (
    PlanContext,
    _silent_lfe,
    lfe_label,
    plan_job,
    source_lfe,
)
from deezy.track_info.audio_track_info import AudioTrackInfo
from deezy.track_info.mediainfo import MediainfoParser

BUILDERS = {
    "dd": cli.PayloadBuilder.build_dd_payload,
    "ddp": cli.PayloadBuilder.build_ddp_payload,
    "ddp-bluray": cli.PayloadBuilder.build_ddp_payload,
    "thd": cli.PayloadBuilder.build_thd_payload,
    "ac4": cli.PayloadBuilder.build_ac4_channel_payload,
}
SUFFIX = {
    "dd": ".ac3",
    "ddp": ".ec3",
    "ddp-bluray": ".ec3",
    "thd": ".thd",
    "ac4": ".ac4",
}


@pytest.fixture
def parser():
    main = cli.create_main_parser()
    sub = main.add_subparsers(dest="sub_command")
    cli.create_encode_parsers(sub, cli.create_common_argument_groups())
    return main


def payload_for(parser, fmt: str, *args: str):
    ns = parser.parse_args(["encode", fmt, *args, "x.mkv"])
    return BUILDERS[fmt](
        ns, Path("x.mkv"), Path("ffmpeg"), Path("truehdd"), Path("dee")
    )


def track(channels: int, lfe: bool | None = None) -> AudioTrackInfo:
    return AudioTrackInfo(
        mi_track=cast("Track", None),
        channels=channels,
        delay_relative_to_video=0,
        fps=24,
        duration=1000.0,
        sample_rate=48000,
        lfe=lfe,
    )


def logged(parser, tmp_path, fmt, info, *args) -> list[str]:
    payload = payload_for(parser, fmt, *args)
    payload.file_output = tmp_path / f"out{SUFFIX[fmt]}"
    ctx = PlanContext(namer=cast("cli.OutputNamer", None), temp_dir=tmp_path)
    with patch("deezy.pipeline.plan.logger") as log:
        plan_job(payload, info, ctx)
    return [call.args[0] for call in log.info.call_args_list]


@pytest.mark.parametrize("fmt", ["dd", "ddp", "ddp-bluray", "thd", "ac4"])
def test_the_channel_formats_take_disable_lfe(parser, fmt):
    assert payload_for(parser, fmt).disable_lfe is False
    assert payload_for(parser, fmt, "--disable-lfe").disable_lfe is True


@pytest.mark.parametrize(
    "fmt", ["ddp-atmos", "thd-atmos", "ac4-ims", "ac4-atmos", "aac"]
)
def test_the_other_formats_dont(parser, fmt):
    with pytest.raises(SystemExit):
        parser.parse_args(["encode", fmt, "--disable-lfe", "x.mkv"])


@pytest.mark.parametrize(
    ("attrs", "lfe"),
    [
        ({"channel_layout": "L R C Ls Rs"}, False),
        ({"channel_layout": "L R C LFE Cb"}, True),
        ({"channel_layout": "C L R Ls Rs LFE"}, True),
        ({"channel_layout": "L R C Lb Rb Ls Rs"}, False),
        ({"channel_positions": "Front: L C R, Side: L R, LFE"}, True),
        ({"channel_positions": "Front: L C R, Side: L R"}, False),
        ({}, None),
    ],
)
def test_mediainfo_says_whether_a_track_has_an_lfe(attrs, lfe):
    parser = object.__new__(MediainfoParser)
    fields = dict.fromkeys(("channel_layout", "channel_positions"))
    parser.mi_audio_obj = cast("Track", SimpleNamespace(**{**fields, **attrs}))
    assert parser._has_lfe() is lfe


@pytest.mark.parametrize(
    ("channels", "lfe", "has"),
    [(5, None, False), (7, None, True), (6, None, True), (2, None, False)]
    + [(5, True, True), (7, False, False), (6, False, False)],
)
def test_without_a_layout_ffmpegs_guess_decides(channels, lfe, has):
    assert source_lfe(track(channels, lfe)) is has


def test_a_layout_without_its_lfe_is_named_so():
    assert [lfe_label(name, False) for name in ("5.1", "7.1", "2.0", "1.0")] == [
        "5.0",
        "7.0",
        "2.0",
        "1.0",
    ]
    assert lfe_label("5.1", True) == "5.1"


def test_the_lfe_is_silenced_as_the_fourth_channel():
    assert _silent_lfe(None, 6) == "pan=5.1|c0=c0|c1=c1|c2=c2|c3=0*c3|c4=c4|c5=c5"
    assert _silent_lfe("a,b", 5) == "a,b,pan=4.1|c0=c0|c1=c1|c2=c2|c3=0*c3|c4=c4"
    with pytest.raises(ChannelMixError, match="10-channel"):
        _silent_lfe(None, 10)


def test_a_source_without_an_lfe_says_so(parser, tmp_path):
    said = logged(parser, tmp_path, "dd", track(5, lfe=False))
    assert said[:2] == [
        "No supplied channels, defaulting to 5.0.",
        "The source has no LFE channel, so it is encoded as 5.0.",
    ]
    said = logged(parser, tmp_path, "ac4", track(5, lfe=False))
    assert "The source has no LFE channel, so the 5.1 stream's is silent." in said


def test_a_7_0_source_without_dee_shim_is_5_0(parser, tmp_path):
    said = logged(parser, tmp_path, "ddp", track(7, lfe=False))
    assert "No supplied channels, defaulting to 5.0." in said
    assert any(
        line.startswith("Dolby Digital Plus 7.0 needs dee_shim")
        and line.endswith("so the 7.0 source is encoded as 5.0.")
        for line in said
    )


def test_disable_lfe_says_when_there_is_nothing_to_drop(parser, tmp_path):
    for fmt in ("dd", "thd", "ac4"):
        said = logged(
            parser, tmp_path, fmt, track(6), "--disable-lfe", "--channels", "2"
        )
        assert "--disable-lfe: 2.0 has no LFE channel." in said


def test_a_kept_lfe_is_said_to_be_silent(parser, tmp_path):
    said = logged(parser, tmp_path, "thd", track(6), "--disable-lfe")
    assert "TrueHD 5.1 keeps its LFE channel, so it is silent." in said
    said = logged(
        parser, tmp_path, "ddp", track(6), "--bluray-secondary", "--disable-lfe"
    )
    assert "Blu-ray secondary audio keeps its LFE channel, so it is silent." in said
    said = logged(parser, tmp_path, "ddp-bluray", track(8), "--disable-lfe")
    assert any("7.1 with a silent LFE" in line for line in said)


def test_blu_ray_7_0_needs_dee_shim(parser):
    payload = payload_for(parser, "ddp-bluray")
    payload.channels = DolbyDigitalPlusBlurayChannels.SURROUNDEX
    files = DeeFiles(input=Path("in.wav"), output=Path("out.eb3"), temp_dir=Path("t"))
    with pytest.raises(UnsupportedDeeFeatureError, match="7.0 needs dee_shim"):
        ddp_command(
            DeeTools(dee_dir=Path("dee")),
            payload,
            files,
            downmix_mode_off=False,
            bitrate=1280,
            fps=DeeFPS.FPS_NOT_INDICATED,
            delay=Delay(),
            dd_mode=DDEncodingMode.BLURAY,
            lfe=False,
        )


def test_lfe_on_is_only_asked_of_dd_and_ddp(parser):
    payload = payload_for(parser, "dd")
    payload.channels = DolbyDigitalChannels.SURROUND
    files = DeeFiles(input=Path("in.wav"), output=Path("out.ac3"), temp_dir=Path("t"))
    argv = ddp_command(
        DeeTools(dee_dir=Path("dee")),
        payload,
        files,
        downmix_mode_off=False,
        bitrate=448,
        fps=DeeFPS.FPS_NOT_INDICATED,
        delay=Delay(),
        dd_mode=DDEncodingMode.DD,
        lfe=False,
    )
    assert argv[argv.index("-e") + 1].endswith(":lfe_on=0")
    assert argv[argv.index("-c") + 1] == "5.1"
