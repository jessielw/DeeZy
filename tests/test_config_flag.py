"""`--config X` reads X only: the auto-discovered config is never loaded."""

import argparse
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import pytest

import deezy.cli.utils as utils
from deezy.config.manager import ConfigManager, get_config_manager

OLD_SECTION = "[default_bitrates.atmos]\nstreaming = 768\n"
RENAME_WARNING = "Config section [default_bitrates.atmos] is ignored"


@pytest.fixture(autouse=True)
def fresh_manager():
    ConfigManager.reset_instance()
    yield
    ConfigManager.reset_instance()


@pytest.fixture
def cwd_config(tmp_path, monkeypatch):
    """A cwd deezy-conf.toml with a 1.x section, which logs a warning if read."""
    (tmp_path / "deezy-conf.toml").write_text(OLD_SECTION, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _warnings(log) -> list[str]:
    return [call.args[0] for call in log.warning.call_args_list]


def test_an_explicit_config_replaces_auto_discovery(cwd_config):
    mine = cwd_config / "mine.toml"
    mine.write_text("[default_bitrates.ddp]\nstereo = 256\n", encoding="utf-8")

    with patch("deezy.config.manager.logger") as log:
        manager = get_config_manager(str(mine))

    assert manager.config_path == mine
    assert manager.config["default_bitrates"] == {"ddp": {"stereo": 256}}
    assert _warnings(log) == []


def test_without_one_the_cwd_config_is_still_found(cwd_config):
    with patch("deezy.config.manager.logger") as log:
        manager = get_config_manager()

    assert manager.config_path == cwd_config / "deezy-conf.toml"
    assert [w for w in _warnings(log) if w.startswith(RENAME_WARNING)]


def test_preset_injection_and_configuration_read_the_config_once(
    cwd_config, monkeypatch
):
    mine = cwd_config / "mine.toml"
    mine.write_text(
        OLD_SECTION + '\n[presets]\nfast = "encode ddp --bitrate 640"\n',
        encoding="utf-8",
    )
    argv = ["deezy", "--config", str(mine), "encode", "preset", "--name", "fast"]
    monkeypatch.setattr(sys, "argv", argv)

    with patch("deezy.config.manager.logger") as log:
        utils.handle_preset_injection()
        manager = utils.handle_configuration(
            argparse.Namespace(sub_command="encode", config=str(mine))
        )

    assert sys.argv[3:] == ["encode", "ddp", "--bitrate", "640"]
    assert manager is not None and manager.config_path == mine
    # mine.toml's own old section warns, once; the cwd config is never read
    (warning,) = _warnings(log)
    assert warning.startswith(RENAME_WARNING)


def test_the_cli_logs_nothing_about_a_config_it_does_not_use(cwd_config):
    empty = cwd_config / "empty.toml"
    empty.write_text("", encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]))

    run = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "deezy", "--config", str(empty), "bitrates", "thd"],
        cwd=cwd_config,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert run.returncode == 0, run.stderr
    assert RENAME_WARNING not in run.stdout + run.stderr
    assert "thd: lossless, no data rate" in run.stdout
