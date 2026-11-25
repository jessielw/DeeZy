"""`deezy bitrates`: each format's modes, layouts, defaults and rates."""

import argparse
import sys

import pytest

import deezy.cli as cli
from deezy.cli.bitrates import bitrate_lines, config_key, rate_text
from deezy.config.manager import ConfigManager
from deezy.dee.spec import formats


@pytest.mark.parametrize(
    ("rates", "text"),
    [
        ([32, 40, 48], "32, 40, 48"),
        ([1512, 1536], "1512, 1536"),
        ([7, 8], "7, 8"),
        (list(range(448, 2049)), "448-2048"),
        ([16, 17, 18, 20], "16-18, 20"),
    ],
)
def test_runs_of_whole_kbps_are_written_as_ranges(rates, text):
    assert rate_text(rates) == text


def test_every_format_is_listed_by_default():
    titles = [line for line in bitrate_lines() if line and not line.startswith(" ")]
    for name in formats():
        assert any(title.split()[0].rstrip(":") == name for title in titles)


def test_a_layout_dee_alone_cannot_encode_is_marked():
    lines = bitrate_lines(["ddp"])
    (seven_one,) = [line for line in lines if line.startswith("  7.1")]
    assert seven_one.startswith("  7.1   default 384, needs dee_shim: 384, 448")
    assert not any("needs dee_shim" in line for line in lines if "5.1" in line)


def test_each_mode_names_the_option_that_picks_it():
    titles = [line for line in bitrate_lines(["ddp-atmos", "aac"]) if line[:1] != " "]
    assert titles == [
        "ddp-atmos --atmos-mode streaming (default)",
        "ddp-atmos --atmos-mode bluray",
        "ddp-atmos --atmos-mode standard",
        "",
        "aac --aac-profile aaclc (default)",
        "aac --aac-profile heaac",
        "aac --aac-profile heaacv2",
    ]
    assert "  atmos default 1152, needs dee_shim: 448-2048" in bitrate_lines(
        ["ddp-atmos"]
    )


def test_truehd_has_no_data_rate():
    assert bitrate_lines(["thd", "thd-atmos"]) == [
        "thd: lossless, no data rate",
        "",
        "thd-atmos: lossless, no data rate",
    ]


@pytest.fixture
def config():
    ConfigManager.reset_instance()
    manager = ConfigManager()
    manager.config = {
        "default_bitrates": {
            "dd": {"surround": 640, "stereo": 250},
            "ddp-bluray": {"stereo": 256},
            "ac4-atmos": {"atmos": 768},
        }
    }
    yield manager
    ConfigManager.reset_instance()


def test_a_configured_default_is_shown_with_deezys_own(config):
    lines = bitrate_lines(["dd", "ac4-atmos"], config)
    assert any(
        line.startswith("  5.1   default 640 (config; DeeZy's is 448):")
        for line in lines
    )
    assert any(
        line.startswith("  atmos default 768 (config; DeeZy's is 448):")
        for line in lines
    )
    assert any(line.startswith("  1.0   default 192:") for line in lines)


def test_a_configured_rate_dee_doesnt_take_shows_the_one_it_becomes(config):
    lines = bitrate_lines(["dd"], config)
    assert any(
        line.startswith("  2.0   default 256 (config asks 250; DeeZy's is 224):")
        for line in lines
    )


def test_blu_ray_secondary_audio_keeps_its_own_default(config):
    assert config_key("ddp-bluray", "bluray_secondary", "2.0") is None
    lines = bitrate_lines(["ddp-bluray"], config)
    title = "ddp --bluray-secondary (Blu-ray secondary audio)"
    assert "ddp-bluray" in lines
    secondary = lines[lines.index(title) + 1]
    assert secondary.startswith("  2.0   default 192:")


def test_the_command_lists_what_it_is_asked_for(capsys):
    main = cli.create_main_parser()
    sub = main.add_subparsers(dest="sub_command")
    groups = cli.create_common_argument_groups()
    cli.create_encode_parsers(sub, groups)
    cli.create_other_parsers(sub, groups)
    args = main.parse_args(["bitrates", "thd"])
    cli.execute_bitrates_command(args, None)
    assert capsys.readouterr().out == "thd: lossless, no data rate\n"


def test_an_unknown_format_is_refused():
    with pytest.raises(SystemExit):
        cli.execute_bitrates_command(argparse.Namespace(format=["nope"]), None)


@pytest.fixture
def encode_parser():
    main = cli.create_main_parser()
    sub = main.add_subparsers(dest="sub_command")
    cli.create_encode_parsers(sub, cli.create_common_argument_groups())
    return main


@pytest.mark.parametrize(
    ("fmt", "bad"),
    [
        ("ddp-atmos", "1024:"),
        ("ddp-atmos", ":512"),
        ("ddp-atmos", "512:512:32"),
        ("ddp-bluray", "448:1025"),
        ("ddp", "31:640"),
        ("ddp", "64:3.5"),
        ("aac", "512:512"),
        ("dd", "512:512"),
        ("ac4", "512:512"),
    ],
)
def test_invalid_split_arguments(encode_parser, fmt, bad):
    with pytest.raises(SystemExit):
        encode_parser.parse_args(["encode", fmt, "--bitrate", bad, "input.mkv"])


@pytest.mark.parametrize(
    ("override", "expected"),
    [
        ([], "1024:512"),
        (["--bitrate", "896:640"], "896:640"),
        (["--bitrate", "1152"], "1152"),
    ],
)
def test_split_preset_and_override(
    monkeypatch, config, encode_parser, override, expected
):
    config.config["presets"] = {
        "split": "encode ddp-atmos --atmos-mode standard --bitrate 1024:512"
    }
    monkeypatch.setattr(
        sys,
        "argv",
        ["deezy", "encode", "preset", "--name", "split", *override, "input.mkv"],
    )
    config.inject_preset_args("split")
    assert str(encode_parser.parse_args().bitrate) == expected


def test_configured_split_in_rate_listing(config):
    config.config["default_bitrates"]["ddp-atmos"] = {"standard": "1024:512"}
    lines = bitrate_lines(["ddp-atmos"], config)
    assert any("default 1024:512 (config" in line for line in lines)


@pytest.mark.parametrize(
    ("fmt", "key", "pair"),
    [
        ("ddp-atmos", "streaming", "512:512"),
        ("ddp-atmos", "bluray", "1024:512"),
        ("ddp", "surroundex", "512:"),
    ],
)
def test_invalid_configured_split_names_the_key(config, fmt, key, pair):
    config.config["default_bitrates"][fmt] = {key: pair}
    with pytest.raises(ValueError, match=key):
        bitrate_lines([fmt], config)
