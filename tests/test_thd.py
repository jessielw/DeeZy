"""encode thd: the layout and rate choices, and the options DEE has no value for."""

import argparse
from pathlib import Path

import pytest

import deezy.cli as cli
from deezy.cli.utils import apply_default_bitrate
from deezy.dee.commands import check_thd_options
from deezy.enums.shared import DeeDRC
from deezy.enums.thd import TrueHDChannels
from deezy.exceptions import UnsupportedDeeFeatureError
from deezy.pipeline.plan import thd_channel_resolver, thd_sample_rate


@pytest.mark.parametrize(
    ("source", "layout"),
    [(1, 2), (2, 2), (3, 6), (5, 6), (6, 6), (7, 8), (8, 8), (10, 8)],
)
def test_auto_takes_the_smallest_layout_that_holds_the_source(source, layout):
    assert thd_channel_resolver(source).value == layout


@pytest.mark.parametrize(
    ("source", "rate"),
    [(32000, 48000), (44100, 48000), (48000, 48000), (88200, 96000)]
    + [(96000, 96000), (192000, 96000), (None, 48000)],
)
def test_the_rate_is_48_or_96_khz(source, rate):
    assert thd_sample_rate(source) == rate


def test_presentations_are_named_by_channel_count():
    assert [c.to_dee_cmd() for c in TrueHDChannels if c.value] == ["2ch", "6ch", "8ch"]
    with pytest.raises(ValueError):
        TrueHDChannels.AUTO.to_dee_cmd()


@pytest.fixture
def parser():
    main = cli.create_main_parser()
    sub = main.add_subparsers(dest="sub_command")
    cli.create_encode_parsers(sub, cli.create_common_argument_groups())
    return main


def test_drc_none_and_no_as_is_are_offered(parser):
    args = parser.parse_args(["encode", "thd", "--drc", "none", "--no-as-is", "x.mkv"])
    payload = cli.PayloadBuilder.build_thd_payload(
        args, Path("x.mkv"), Path("ffmpeg"), None, Path("dee")
    )
    assert payload.drc is DeeDRC.NONE
    assert payload.as_is is False


def test_drc_none_needs_dee_shim(parser):
    args = parser.parse_args(["encode", "thd", "--drc", "none", "x.mkv"])
    payload = cli.PayloadBuilder.build_thd_payload(
        args, Path("x.mkv"), Path("ffmpeg"), None, Path("dee")
    )
    assert payload.as_is is True
    with pytest.raises(UnsupportedDeeFeatureError, match="needs dee_shim"):
        check_thd_options(payload)
    check_thd_options(payload, shim=True)


def test_truehd_takes_no_bitrate(parser):
    args = parser.parse_args(["encode", "thd", "x.mkv"])
    assert not hasattr(args, "bitrate")

    class Config:
        def get_default_bitrate(self, *_args):
            raise AssertionError("TrueHD has no default bitrate to look up")

    apply_default_bitrate(args, Config())
    assert getattr(args, "bitrate", None) is None


def test_the_payload_takes_the_truehd_options(parser):
    args = parser.parse_args(
        ["encode", "thd", "--channels", "6", "--drc", "music_light"]
        + ["--custom-dialnorm", "-27", "x.mkv"]
    )
    assert isinstance(args, argparse.Namespace)
    payload = cli.PayloadBuilder.build_thd_payload(
        args, Path("x.mkv"), Path("ffmpeg"), None, Path("dee")
    )
    assert payload.channels is TrueHDChannels.SURROUND
    assert payload.drc is DeeDRC.MUSIC_LIGHT
    assert payload.custom_dialnorm == -27
