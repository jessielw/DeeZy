import argparse
import sys
from pathlib import Path
from typing import Any, cast

import pytest

import deezy.cli.utils as utils


class DummyConfigManager:
    def __init__(self, deps=None, bitrate_map=None):
        self.config = {"dependencies": deps or {}}
        self._bitrate_map = bitrate_map or {}

    def get_default_bitrate(self, fmt, channels_or_mode):
        return self._bitrate_map.get((fmt, channels_or_mode))

    def load_config(self):
        self.loaded = True

    def inject_preset_args(self, name):
        self.injected = name


def test_apply_default_bitrate_atmos_and_channels():
    args = argparse.Namespace(format_command="atmos", bitrate=None, atmos_mode=None)

    class Mode:
        value = "STREAMING"

    args.atmos_mode = Mode()
    cfg = DummyConfigManager(bitrate_map={("atmos", "STREAMING"): 512})

    utils.apply_default_bitrate(args, cast(Any, cfg))
    assert args.bitrate == 512


def test_apply_default_bitrate_dd_channels():
    args = argparse.Namespace(format_command="dd", bitrate=None, channels="2.0")
    cfg = DummyConfigManager(bitrate_map={("dd", "2.0"): 192})

    utils.apply_default_bitrate(args, cast(Any, cfg))
    assert args.bitrate == 192


def test_handle_preset_injection_calls_inject(monkeypatch):
    saved_argv = sys.argv[:]  # preserve
    sys.argv = ["prog", "encode", "preset", "--name", "mypreset"]

    called = {}

    def fake_get_config_manager():
        called["created"] = True
        return DummyConfigManager()

    monkeypatch.setattr(utils, "get_config_manager", fake_get_config_manager)

    # call should not raise
    utils.handle_preset_injection()

    # restore argv
    sys.argv = saved_argv


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
    monkeypatch.setattr(utils, "get_config_manager", lambda: sentinel)
    args = argparse.Namespace(sub_command="encode")
    assert utils.handle_configuration(args) is sentinel


def test_handle_dependencies_normal(monkeypatch, tmp_path):
    args = argparse.Namespace(
        sub_command="encode",
        format_command="atmos",
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
