"""[global_defaults] keys are the defaults of the options they name."""

import argparse
import importlib.util
from pathlib import Path
import sys
from unittest.mock import patch

import pytest
import tomlkit

import deezy.cli as cli
import deezy.cli.utils as utils
from deezy.config.defaults import CONF_DEFAULT
from deezy.config.manager import ConfigManager
from deezy.enums.shared import DeeDRC, StereoDownmix

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "cli_docs", ROOT / "scripts" / "cli_docs.py"
)
assert _spec and _spec.loader
cli_docs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cli_docs)


class _Config:
    def __init__(self, global_defaults: dict):
        self.config = {"global_defaults": global_defaults}


def _commands(parser: argparse.ArgumentParser, path=()):
    """Each command's subcommand choices, as Namespace fields."""
    subs = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
    if not subs:
        yield dict(path)
        return
    for name, sub in subs[0].choices.items():
        yield from _commands(sub, (*path, (subs[0].dest, name)))


def _parse(argv: list[str], global_defaults: dict) -> tuple[argparse.Namespace, list]:
    """argv parsed with the config applied, and the warnings it logged."""
    parser = cli_docs.build_parser()
    args = parser.parse_args(argv)
    with patch.object(utils, "logger") as log:
        if utils.apply_config_option_defaults(parser, args, _Config(global_defaults)):
            args = parser.parse_args(argv)
    return args, [call.args[0] for call in log.warning.call_args_list]


DD = ["encode", "dd", "in.wav"]


def test_a_config_value_is_the_default():
    args, warnings = _parse(
        DD,
        {
            "speech_threshold": 40,
            "drc_line_mode": "music_light",
            "stereo_down_mix": "ltrt",
            "lt_rt_center": -1.5,
            "custom_dialnorm": -20,
            "track_index": 2,
            "keep_temp": True,
        },
    )
    assert warnings == []
    assert args.speech_threshold == 40
    assert args.drc_line_mode is DeeDRC.MUSIC_LIGHT
    assert args.stereo_down_mix is StereoDownmix.LTRT
    assert args.lt_rt_center == "-1.5"
    assert args.custom_dialnorm == -20
    assert args.track_index.index == 2
    assert args.keep_temp is True


def test_the_command_line_wins():
    args, _ = _parse(
        [
            *DD[:2],
            "--speech-threshold",
            "10",
            "--drc-line-mode",
            "film_standard",
            "in.wav",
        ],
        {"speech_threshold": 40, "drc_line_mode": "music_light"},
    )
    assert args.speech_threshold == 10
    assert args.drc_line_mode is DeeDRC.FILM_STANDARD


@pytest.mark.parametrize(
    ("key", "value", "enabled"),
    [
        ("dialogue_intelligence", False, False),
        ("dialogue_intelligence", True, True),
        ("no_dialogue_intelligence", True, False),
        ("no_dialogue_intelligence", False, True),
    ],
)
def test_a_no_switch_takes_either_name(key, value, enabled):
    args, warnings = _parse(DD, {key: value})
    assert warnings == []
    # the switch's destination is True while dialogue intelligence is on
    assert args.no_dialogue_intelligence is enabled


def test_a_destination_two_switches_share_takes_the_value():
    # --surround-3db and the hidden --no-surround-3db both set surround_3db
    args, _ = _parse(DD, {"surround_3db": True})
    assert args.surround_3db is True


@pytest.mark.parametrize(
    ("key", "value", "says"),
    [
        ("speech_threshold", 400, "between 0 and 100"),
        ("drc_line_mode", "loud", "loud"),
        ("lt_rt_center", "-2", "--lt-rt-center takes"),
        ("keep_temp", "yes", "takes true or false"),
        ("speech_threshold", True, "takes a single value"),
        ("bitrate", 640, "[default_bitrates]"),
        ("dee", "C:/dee", "[dependencies]"),
        ("speech_treshold", 20, "no --speech-treshold option"),
        ("metering_mode", "1770_4", "no --metering-mode option"),
    ],
)
def test_a_key_deezy_cant_use_is_ignored_with_a_warning(key, value, says):
    plain, _ = _parse(DD, {})
    args, warnings = _parse(DD, {key: value})
    (warning,) = warnings
    assert warning.startswith(f"Config [global_defaults] {key}")
    assert says in warning
    assert vars(args) == vars(plain)


def test_another_commands_option_is_skipped_quietly():
    plain, _ = _parse(["encode", "aac", "in.wav"], {})
    args, warnings = _parse(["encode", "aac", "in.wav"], {"drc_line_mode": "speech"})
    assert warnings == []
    assert vars(args) == vars(plain)


def test_the_generated_config_changes_no_default_of_any_command():
    template = tomlkit.parse(CONF_DEFAULT).unwrap()["global_defaults"]
    parser = cli_docs.build_parser()
    for command in _commands(parser):
        plain = cli_docs.build_parser()
        configured = cli_docs.build_parser()
        args = argparse.Namespace(**command)
        with patch.object(utils, "logger") as log:
            utils.apply_config_option_defaults(configured, args, _Config(template))
        assert log.warning.call_args_list == [], command
        before = {a.dest: a.default for a in utils._all_actions(plain)}
        after = {a.dest: a.default for a in utils._all_actions(configured)}
        assert after == before, command


def test_every_generated_key_does_something():
    template = tomlkit.parse(CONF_DEFAULT).unwrap()["global_defaults"]
    actions = utils._all_actions(cli_docs.build_parser())
    unused = [
        key
        for key in template
        if key not in utils.OWN_CONFIG_KEYS
        and utils._config_option(key, actions) is None
    ]
    assert unused == []


def test_cli_parser_applies_the_config_and_a_preset_still_wins(tmp_path, monkeypatch):
    config = tmp_path / "c.toml"
    config.write_text(
        "[global_defaults]\nspeech_threshold = 40\ndrc_line_mode = 'music_light'\n"
        "lt_rt_center = -1.5\nkeep_temp = true\ndialogue_intelligence = false\n"
        '[presets]\nquiet = "encode dd --speech-threshold 5"\n',
        encoding="utf-8",
    )
    seen = []
    monkeypatch.setattr(cli, "handle_dependencies", lambda *a: None)
    monkeypatch.setattr(cli, "handle_file_inputs", lambda *a: [])
    monkeypatch.setattr(cli, "execute_command", lambda args, *a: seen.append(args))
    ConfigManager.reset_instance()
    try:
        for argv in (
            ["encode", "dd", "in.wav"],
            ["encode", "preset", "--name", "quiet", "in.wav"],
        ):
            monkeypatch.setattr(sys, "argv", ["deezy", "--config", str(config), *argv])
            cli.cli_parser()
    finally:
        ConfigManager.reset_instance()

    plain, preset = seen
    assert (plain.speech_threshold, plain.drc_line_mode) == (40, DeeDRC.MUSIC_LIGHT)
    assert (preset.speech_threshold, preset.drc_line_mode) == (5, DeeDRC.MUSIC_LIGHT)
    # TOML's numbers and booleans, as the config manager reads them
    assert (plain.lt_rt_center, plain.keep_temp) == ("-1.5", True)
    assert plain.no_dialogue_intelligence is False
