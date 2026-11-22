"""encode thd-atmos: the options, the inputs it takes and what it logs."""

import argparse
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

from pymediainfo import Track
import pytest

import deezy.cli as cli
from deezy.cli.utils import apply_default_bitrate, handle_dependencies
from deezy.dee import spec
from deezy.dee.commands import check_thd_options
from deezy.dee.shim import DeeShim
from deezy.enums.atmos import WarpMode
from deezy.enums.shared import DeeDRC
from deezy.exceptions import InvalidAtmosInputError, UnsupportedDeeFeatureError
from deezy.pipeline.plan import (
    DeeStep,
    PlanContext,
    TruehddStep,
    plan_job,
    thd_atmos_fits,
)
from deezy.track_info.audio_track_info import AudioTrackInfo
from deezy.track_info.mediainfo import MediainfoParser


@pytest.fixture
def parser():
    main = cli.create_main_parser()
    sub = main.add_subparsers(dest="sub_command")
    cli.create_encode_parsers(sub, cli.create_common_argument_groups())
    return main


def payload_for(parser, *args: str, source: str = "x.mkv"):
    ns = parser.parse_args(["encode", "thd-atmos", *args, source])
    return cli.PayloadBuilder.build_thd_atmos_payload(
        ns, Path(source), Path("ffmpeg"), Path("truehdd"), Path("dee")
    )


def track(**probed) -> AudioTrackInfo:
    fields = {"channels": 8, "delay_relative_to_video": 0, "sample_rate": 48000}
    fields |= {"fps": 24, "duration": 1000.0}
    return AudioTrackInfo(mi_track=cast("Track", None), **{**fields, **probed})


def plan(payload, info, tmp_path):
    ctx = PlanContext(namer=cast("cli.OutputNamer", None), temp_dir=tmp_path)
    payload.file_output = tmp_path / "out.thd"
    return plan_job(payload, info, ctx)


def test_truehd_atmos_is_lossless_and_starts_on_time():
    fmt = spec.get_format("thd-atmos")
    assert set(fmt.mode().layouts) == {"atmos"}
    with pytest.raises(ValueError, match="lossless"):
        fmt.rates("atmos")
    assert fmt.extensions == (".thd", ".mlp")
    assert (fmt.delay_samples, fmt.channel_change_samples) == (0, 0)
    assert fmt.tool.name == "dee_dthd_encoder"


def test_the_payload_takes_the_truehd_atmos_options(parser):
    payload = payload_for(
        parser,
        *("--drc", "speech", "--custom-dialnorm", "-27"),
        *("--thd-warp-mode", "loro", "--legacy-authoring"),
    )
    assert payload.drc is DeeDRC.SPEECH
    assert payload.custom_dialnorm == -27
    assert payload.thd_warp_mode is WarpMode.LORO
    assert payload.legacy_authoring is True


def test_the_defaults_follow_d7_and_d6(parser):
    payload = payload_for(parser)
    assert payload.drc is DeeDRC.FILM_LIGHT
    assert payload.custom_dialnorm == 0
    assert payload.thd_warp_mode is None
    assert payload.legacy_authoring is False


@pytest.mark.parametrize("args", [["--channels", "8"], ["--bitrate", "640"]])
def test_options_truehd_atmos_has_no_value_for_are_not_offered(parser, args):
    with pytest.raises(SystemExit):
        parser.parse_args(["encode", "thd-atmos", *args, "x.mkv"])


def test_drc_none_needs_dee_shim(parser):
    payload = payload_for(parser, "--drc", "none")
    with pytest.raises(UnsupportedDeeFeatureError, match="needs dee_shim"):
        check_thd_options(payload)
    check_thd_options(payload, shim=True)


def test_as_is_is_on_unless_turned_off(parser):
    assert payload_for(parser).as_is is True
    assert payload_for(parser, "--no-as-is").as_is is False


def test_truehd_atmos_takes_no_bitrate(parser):
    args = parser.parse_args(["encode", "thd-atmos", "x.mkv"])

    class Config:
        def get_default_bitrate(self, *_args):
            raise AssertionError("TrueHD Atmos has no default bitrate to look up")

    apply_default_bitrate(args, Config())
    assert getattr(args, "bitrate", None) is None


def test_truehdd_is_required(parser):
    args = parser.parse_args(["encode", "thd-atmos", "x.mkv"])
    assert isinstance(args, argparse.Namespace)
    with patch("deezy.cli.utils.FindDependencies") as finder:
        finder.return_value.get_dependencies.return_value.truehdd = "truehdd"
        handle_dependencies(args, None)
    assert finder.return_value.get_dependencies.call_args.kwargs == {
        "require_truehdd": True
    }


@pytest.mark.parametrize("probed", [{"channels": 8}, {"channels": 2}])
def test_channel_based_audio_is_refused_with_a_pointer_to_thd(parser, tmp_path, probed):
    with pytest.raises(InvalidAtmosInputError, match="'thd'"):
        plan(payload_for(parser), track(**probed), tmp_path)


def test_truehd_atmos_goes_through_truehdd(parser, tmp_path):
    payload = payload_for(parser, "--thd-warp-mode", "normal")
    job = plan(payload, track(thd_atmos=True), tmp_path)
    truehdd, dee = job.steps
    assert isinstance(truehdd, TruehddStep)
    assert truehdd.warp_mode is WarpMode.NORMAL
    assert isinstance(dee, DeeStep)
    assert dee.argv[dee.argv.index("-i") + 1] == str(truehdd.output)


@pytest.mark.parametrize(
    ("probed", "source"),
    [({"damf_atmos": True}, "in.atmos"), ({"adm_atmos_wav": True}, "in.wav")],
)
def test_a_master_goes_to_dee_as_it_is(parser, tmp_path, probed, source):
    job = plan(payload_for(parser, source=source), track(**probed), tmp_path)
    (dee,) = job.steps
    assert isinstance(dee, DeeStep)
    assert dee.argv[dee.argv.index("-i") + 1] == source


def warnings_and_info(payload, info, tmp_path) -> tuple[list[str], list[str]]:
    with patch("deezy.pipeline.plan.logger") as log:
        plan(payload, info, tmp_path)
    return (
        [call.args[0] for call in log.warning.call_args_list],
        [call.args[0] for call in log.info.call_args_list],
    )


def test_legacy_authoring_says_the_stream_has_no_warp_mode(parser, tmp_path):
    warnings, info = warnings_and_info(
        payload_for(parser, "--legacy-authoring"), track(thd_atmos=True), tmp_path
    )
    assert not warnings
    assert any("carries no warp mode" in line for line in info)


def test_legacy_authoring_with_a_warp_mode_warns(parser, tmp_path):
    payload = payload_for(parser, "--legacy-authoring", "--thd-warp-mode", "normal")
    warnings, _ = warnings_and_info(payload, track(thd_atmos=True), tmp_path)
    assert warnings == [
        "With --legacy-authoring the stream reports no warp mode, whatever "
        "--thd-warp-mode sets."
    ]


def test_a_warp_mode_for_a_master_warns_once(parser, tmp_path):
    payload = payload_for(
        parser, "--legacy-authoring", "--thd-warp-mode", "normal", source="in.atmos"
    )
    warnings, _ = warnings_and_info(payload, track(damf_atmos=True), tmp_path)
    assert len(warnings) == 1
    assert "TrueHD Atmos only" in warnings[0]


def test_the_element_count_is_16_unless_chosen(parser):
    assert payload_for(parser).atmos_elements == 16
    assert payload_for(parser, "--atmos-elements", "12").atmos_elements == 12
    with pytest.raises(SystemExit):
        payload_for(parser, "--atmos-elements", "13")


@pytest.mark.parametrize(
    ("chosen", "probed", "fits"),
    [
        # truehdd decodes at most 16 elements, so 16 always fits
        (16, {"thd_atmos": True}, True),
        (12, {"thd_atmos": True}, False),
        (12, {"thd_atmos": True, "atmos_elements": 12}, True),
        (14, {"thd_atmos": True, "atmos_elements": 16}, False),
        (16, {"thd_atmos": True, "atmos_elements": 16}, True),
        (14, {"damf_atmos": True, "channels": 14}, True),
        (14, {"damf_atmos": True, "channels": 16}, False),
        (12, {"adm_atmos_wav": True, "channels": 10}, True),
    ],
)
def test_a_master_fits_when_it_has_no_more_elements_than_chosen(
    parser, chosen, probed, fits
):
    payload = payload_for(parser, "--atmos-elements", str(chosen))
    assert thd_atmos_fits(payload, track(**probed)) is fits


def test_a_master_that_does_not_fit_says_why_through_the_shim(parser):
    payload = payload_for(parser, "--atmos-elements", "12")
    payload.dee_shim = cast("DeeShim", object())
    with patch("deezy.pipeline.plan.logger") as log:
        thd_atmos_fits(payload, track(thd_atmos=True, atmos_elements=16))
        thd_atmos_fits(payload, track(thd_atmos=True))
    said = [call.args[0] for call in log.info.call_args_list]
    assert "16 elements, more than the 12 the stream codes" in said[0]
    assert "doesn't say how many elements" in said[1]


@pytest.mark.parametrize(
    ("attrs", "elements"),
    [
        ({"bed_channel_count": "1", "number_of_dynamic_objects": "15"}, 16),
        ({"bed_channel_count": "1", "number_of_dynamic_objects": "11"}, 12),
        ({"bed_channel_count": "10", "number_of_dynamic_objects": "4"}, 14),
        # every stream reports 16-ch, whatever its element count
        ({"format_additionalfeatures": "16-ch"}, None),
        ({"bed_channel_count": "1"}, None),
    ],
)
def test_mediainfo_counts_a_truehd_atmos_streams_elements(attrs, elements):
    namer = object.__new__(MediainfoParser)
    fields = dict.fromkeys(
        ("bed_channel_count", "number_of_dynamic_objects", "format_additionalfeatures")
    )
    namer.mi_audio_obj = cast("Track", SimpleNamespace(**{**fields, **attrs}))
    assert namer._thd_atmos_elements() == elements
