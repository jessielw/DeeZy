import argparse
from pathlib import Path
import sys
from typing import Any, cast

import pytest

import deezy.cli.utils as utils


class DummyConfigManager:
    def __init__(self, deps=None, bitrate_map=None):
        self.config = {"dependencies": deps or {}}
        self._bitrate_map = bitrate_map or {}

    def get_default_bitrate(self, fmt, channels_or_mode):
        return self._bitrate_map.get((fmt, channels_or_mode))

    def load_config(self, config_path=None):
        self.loaded = True
        self.loaded_path = config_path

    def inject_preset_args(self, name):
        self.injected = name


def fake_getter(cfg):
    """A `get_config_manager` stand-in that records the path it was given."""

    def get(config_path=None):
        cfg.requested_path = config_path
        return cfg

    return get


def test_apply_default_bitrate_atmos_and_channels():
    args = argparse.Namespace(format_command="ddp-atmos", bitrate=None, atmos_mode=None)

    class Mode:
        value = "STREAMING"

    args.atmos_mode = Mode()
    cfg = DummyConfigManager(bitrate_map={("ddp-atmos", "STREAMING"): 512})

    utils.apply_default_bitrate(args, cast(Any, cfg))
    assert args.bitrate == 512


def test_apply_default_bitrate_dd_channels():
    args = argparse.Namespace(format_command="dd", bitrate=None, channels="2.0")
    cfg = DummyConfigManager(bitrate_map={("dd", "2.0"): 192})

    utils.apply_default_bitrate(args, cast(Any, cfg))
    assert args.bitrate == 192


def test_apply_default_bitrate_leaves_bluray_secondary_alone():
    """The plain DD+ stereo rate (128) must not replace secondary's 192 default."""
    args = argparse.Namespace(
        format_command="ddp", bitrate=None, channels="2.0", bluray_secondary=True
    )
    cfg = DummyConfigManager(bitrate_map={("ddp", "2.0"): 128})

    utils.apply_default_bitrate(args, cast(Any, cfg))
    assert args.bitrate is None


def test_handle_preset_injection_calls_inject(monkeypatch):
    saved_argv = sys.argv[:]  # preserve
    sys.argv = ["prog", "encode", "preset", "--name", "mypreset"]

    called = {}

    def fake_get_config_manager(config_path=None):
        called["created"] = True
        return DummyConfigManager()

    monkeypatch.setattr(utils, "get_config_manager", fake_get_config_manager)

    # call should not raise
    utils.handle_preset_injection()

    # restore argv
    sys.argv = saved_argv


def test_handle_preset_injection_uses_config_flag(monkeypatch):
    saved_argv = sys.argv[:]
    sys.argv = [
        "prog",
        "--config",
        "custom.toml",
        "encode",
        "preset",
        "--name",
        "mypreset",
    ]

    cfg = DummyConfigManager()
    monkeypatch.setattr(utils, "get_config_manager", fake_getter(cfg))

    try:
        utils.handle_preset_injection()
    finally:
        sys.argv = saved_argv

    assert cfg.requested_path == "custom.toml"
    assert cfg.injected == "mypreset"


@pytest.mark.parametrize(
    "argv, expected",
    (
        (["prog", "--config", "a.toml", "encode"], "a.toml"),
        (["prog", "--config=b.toml", "encode"], "b.toml"),
        (["prog", "encode"], None),
        (["prog", "--config"], None),
    ),
)
def test_sniff_config_arg(argv, expected):
    assert utils.sniff_config_arg(argv) == expected


def test_handle_configuration_loads_user_config(monkeypatch):
    cfg = DummyConfigManager()
    monkeypatch.setattr(utils, "get_config_manager", fake_getter(cfg))

    args = argparse.Namespace(sub_command="encode", config="mine.toml")
    assert utils.handle_configuration(args) is cfg
    assert cfg.requested_path == "mine.toml"


def test_handle_file_inputs_reports_bad_path_cleanly(monkeypatch):
    """A mistyped path exits with a message, not a traceback."""

    def raiser(_inputs):
        raise FileNotFoundError("'missing.mkv' is not a valid input path.")

    monkeypatch.setattr(utils, "parse_input_s", raiser)
    args = argparse.Namespace(sub_command="encode", input=["missing.mkv"])

    with pytest.raises(SystemExit) as exc:
        utils.handle_file_inputs(args)

    assert exc.value.code == 1


def test_setup_logging_calls_logger_manager(monkeypatch):
    class DummyLevel:
        def to_logging_level(self):
            return "SOMELEVEL"

    args = argparse.Namespace(log_level=DummyLevel())

    called = {}

    def fake_set_level(lvl):
        called["lvl"] = lvl

    monkeypatch.setattr(
        utils, "logger_manager", type("X", (), {"set_level": fake_set_level})
    )

    utils.setup_logging(args)
    assert called.get("lvl") == "SOMELEVEL"


def test_handle_configuration_returns_none_for_config_subcommand(monkeypatch):
    args = argparse.Namespace(sub_command="config")
    assert utils.handle_configuration(args) is None

    # when not config, should return value from get_config_manager
    sentinel = object()
    monkeypatch.setattr(utils, "get_config_manager", lambda config_path=None: sentinel)
    args = argparse.Namespace(sub_command="encode")
    assert utils.handle_configuration(args) is sentinel


@pytest.mark.parametrize("command", ["find", "info"])
def test_find_and_info_do_not_resolve_encoder_dependencies(monkeypatch, command):
    def unexpected_finder():
        pytest.fail(f"{command} tried to find encoder tools")

    monkeypatch.setattr(utils, "FindDependencies", unexpected_finder)
    assert (
        utils.handle_dependencies(argparse.Namespace(sub_command=command), None) is None
    )


def test_handle_dependencies_normal(monkeypatch, tmp_path):
    args = argparse.Namespace(
        sub_command="encode",
        format_command="ddp-atmos",
        ffmpeg=None,
        truehdd=None,
        dee=None,
    )
    cfg = DummyConfigManager(deps={"ffmpeg": "ff", "truehdd": "td", "dee": "dee"})

    class Tools:
        ffmpeg = "ffmpeg.exe"
        truehdd = "truehdd.exe"
        dee = "dee.exe"

    class FakeFinder:
        def get_dependencies(self, *a, **kw):
            return Tools()

        def check_dee_version(self, dee_dir):
            return "6.7.0"

    monkeypatch.setattr(utils, "FindDependencies", lambda: FakeFinder())

    res = cast(dict, utils.handle_dependencies(args, cast(Any, cfg)))
    assert res["ffmpeg_path"] == Path("ffmpeg.exe")
    assert res["truehdd_path"] == Path("truehdd.exe")
    assert res["dee_path"] == Path("dee.exe")


def test_handle_file_inputs_success_and_missing(monkeypatch):
    # success path
    args = argparse.Namespace(sub_command="encode", input=["/tmp/a.wav"])
    monkeypatch.setattr(utils, "parse_input_s", lambda li: [Path("/tmp/a.wav")])
    res = utils.handle_file_inputs(args)
    assert res == [Path("/tmp/a.wav")]

    # missing inputs should call exit_application -> we replace to raise
    args2 = argparse.Namespace(sub_command="encode")

    def fake_exit(msg, code):
        raise RuntimeError("exited")

    monkeypatch.setattr(utils, "exit_application", fake_exit)
    monkeypatch.setattr(utils, "parse_input_s", lambda li: [])

    with pytest.raises(RuntimeError):
        utils.handle_file_inputs(args2)
