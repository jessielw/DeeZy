"""encode ac4-atmos: the options, the inputs it takes and the rate it picks."""

import argparse
from pathlib import Path
from typing import cast
from unittest.mock import patch

from pymediainfo import Track
import pytest

import deezy.cli as cli
from deezy.cli.utils import handle_dependencies
from deezy.dee import spec
from deezy.enums.atmos import WarpMode
from deezy.enums.shared import DeeDRC, LoudnessPreset
from deezy.exceptions import InvalidAtmosInputError
from deezy.pipeline.plan import DeeStep, PlanContext, TruehddStep, plan_job
from deezy.track_info.audio_track_info import AudioTrackInfo


@pytest.fixture
def parser():
    main = cli.create_main_parser()
    sub = main.add_subparsers(dest="sub_command")
    cli.create_encode_parsers(sub, cli.create_common_argument_groups())
    return main


def payload_for(parser, *args: str, source: str = "x.mkv"):
    ns = parser.parse_args(["encode", "ac4-atmos", *args, source])
    return cli.PayloadBuilder.build_ac4_atmos_payload(
        ns, Path(source), Path("ffmpeg"), Path("truehdd"), Path("dee")
    )


def track(**probed) -> AudioTrackInfo:
    fields = {"channels": 8, "delay_relative_to_video": 0, "sample_rate": 48000}
    fields |= {"fps": 24, "duration": 1000.0}
    return AudioTrackInfo(mi_track=cast("Track", None), **{**fields, **probed})


class Config:
    """A config with only [default_bitrates.ac4-atmos]."""

    def __init__(self, atmos: int):
        self.config = {"default_bitrates": {"ac4-atmos": {"atmos": atmos}}}

    def get_default_bitrate(self, fmt, channels_or_mode):
        section = self.config["default_bitrates"].get(str(fmt), {})
        return section.get(str(channels_or_mode))


def plan(payload, info, tmp_path, config=None):
    ctx = PlanContext(
        namer=cast("cli.OutputNamer", None), temp_dir=tmp_path, config=config
    )
    payload.file_output = tmp_path / "out.ac4"
    return plan_job(payload, info, ctx)


def dee_argv(job) -> tuple[str, ...]:
    dee = job.steps[-1]
    assert isinstance(dee, DeeStep)
    return dee.argv


def value(argv, option: str) -> str:
    return argv[argv.index(option) + 1]


def test_ac4_atmos_is_level_3_with_deezys_default_rate():
    fmt = spec.get_format("ac4-atmos")
    assert fmt.tool.name == "dee_ac4ajoc_encoder"
    assert set(fmt.mode().layouts) == {"atmos"}
    rates = fmt.rates("atmos")
    assert rates.choices == (256, 320, 448, 768)
    # D5: above DEE's own 320
    assert (rates.default, rates.dee_auto) == (448, 320)
    assert fmt.extensions == (".ac4",)
    assert (fmt.delay_samples, fmt.channel_change_samples) == (2048, 0)
    # no skip mode, so DEE always measures
    assert fmt.tool.loudness_modes == {"measure_only"}


def test_the_payload_takes_the_ac4_atmos_options(parser):
    payload = payload_for(
        parser,
        *("--flat-panel-drc", "speech", "--home-theatre-drc", "none"),
        *("--portable-headphones-drc", "music_light"),
        *("--portable-speakers-drc", "film_standard"),
        *("--thd-warp-mode", "loro", "--loudness-preset", "ebu_r128"),
    )
    assert payload.flat_panel_drc is DeeDRC.SPEECH
    assert payload.home_theatre_drc is DeeDRC.NONE
    assert payload.portable_headphones_drc is DeeDRC.MUSIC_LIGHT
    assert payload.portable_speakers_drc is DeeDRC.FILM_STANDARD
    assert payload.thd_warp_mode is WarpMode.LORO
    assert payload.loudness_preset is LoudnessPreset.EBU_R128


def test_the_defaults_follow_dolby_and_d6(parser):
    payload = payload_for(parser)
    devices = (
        payload.flat_panel_drc,
        payload.home_theatre_drc,
        payload.portable_headphones_drc,
        payload.portable_speakers_drc,
    )
    assert set(devices) == {DeeDRC.FILM_LIGHT}
    assert payload.thd_warp_mode is None
    assert payload.loudness_preset is LoudnessPreset.MANUAL
    assert payload.bitrate is None


@pytest.mark.parametrize(
    "args",
    [
        ["--custom-dialnorm", "-27"],
        ["--loudness-target", "-24"],
        ["--channels", "6"],
        ["--stereo-down-mix", "loro"],
        ["--encoding-profile", "ims_music"],
        ["--ddp-drc", "none"],
        ["--legacy-authoring"],
        ["--pipe", "always"],
    ],
)
def test_options_ac4_atmos_has_no_value_for_are_not_offered(parser, args):
    with pytest.raises(SystemExit):
        parser.parse_args(["encode", "ac4-atmos", *args, "x.mkv"])


def test_the_command_has_a_level_and_a_manifest_but_no_input_format(parser, tmp_path):
    argv = dee_argv(plan(payload_for(parser), track(thd_atmos=True), tmp_path))
    assert Path(argv[0]).stem == "dee_ac4ajoc_encoder"
    assert value(argv, "--level") == "3"
    assert Path(value(argv, "--output-manifest")).parent == tmp_path
    # the encoder has neither option
    assert "--input-format" not in argv
    assert "--temp-dir" not in argv
    assert value(argv, "--loudness-management").startswith("measure_only:")
    # the manifest's 2048-sample offset, compensated
    assert value(argv, "--start") == "0.042667"


def test_drc_none_reaches_the_encoder(parser, tmp_path):
    payload = payload_for(parser, "--home-theatre-drc", "none")
    argv = dee_argv(plan(payload, track(thd_atmos=True), tmp_path))
    assert "drc_profile_home_theatre=none" in value(argv, "-e").split(":")


@pytest.mark.parametrize(
    ("args", "config", "rate"),
    [
        ([], None, "448"),
        (["--bitrate", "768"], None, "768"),
        # not a level 3 rate: the next one up
        (["--bitrate", "300"], None, "320"),
        ([], Config(256), "256"),
        ([], Config(500), "768"),
        ([], Config(1000), "768"),
        (["--bitrate", "320"], Config(768), "320"),
    ],
)
def test_the_rate_comes_from_the_option_then_the_config(
    parser, tmp_path, args, config, rate
):
    job = plan(payload_for(parser, *args), track(thd_atmos=True), tmp_path, config)
    assert value(dee_argv(job), "--data-rate") == rate


def test_truehdd_is_required(parser):
    args = parser.parse_args(["encode", "ac4-atmos", "x.mkv"])
    assert isinstance(args, argparse.Namespace)
    with patch("deezy.cli.utils.FindDependencies") as finder:
        finder.return_value.get_dependencies.return_value.truehdd = "truehdd"
        handle_dependencies(args, None)
    assert finder.return_value.get_dependencies.call_args.kwargs == {
        "require_truehdd": True
    }


@pytest.mark.parametrize("probed", [{"channels": 8}, {"channels": 2}])
def test_channel_based_audio_is_refused_with_a_pointer_to_ac4(parser, tmp_path, probed):
    with pytest.raises(InvalidAtmosInputError, match="'ac4'"):
        plan(payload_for(parser), track(**probed), tmp_path)


def test_truehd_atmos_goes_through_truehdd(parser, tmp_path):
    payload = payload_for(parser, "--thd-warp-mode", "normal")
    job = plan(payload, track(thd_atmos=True), tmp_path)
    truehdd, dee = job.steps
    assert isinstance(truehdd, TruehddStep)
    assert truehdd.warp_mode is WarpMode.NORMAL
    assert isinstance(dee, DeeStep)
    assert value(dee.argv, "-i") == str(truehdd.output)


@pytest.mark.parametrize(
    ("probed", "source"),
    [({"damf_atmos": True}, "in.atmos"), ({"adm_atmos_wav": True}, "in.wav")],
)
def test_a_master_goes_to_dee_as_it_is(parser, tmp_path, probed, source):
    job = plan(payload_for(parser, source=source), track(**probed), tmp_path)
    (dee,) = job.steps
    assert isinstance(dee, DeeStep)
    assert value(dee.argv, "-i") == source


def test_a_warp_mode_for_a_master_warns(parser, tmp_path):
    payload = payload_for(parser, "--thd-warp-mode", "normal", source="in.atmos")
    with patch("deezy.pipeline.plan.logger") as log:
        plan(payload, track(damf_atmos=True), tmp_path)
    (warning,) = [call.args[0] for call in log.warning.call_args_list]
    assert "TrueHD Atmos only" in warning
