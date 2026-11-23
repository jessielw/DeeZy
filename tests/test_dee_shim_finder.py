"""Finding dee_shim, checking its version, and reading its failures."""

from pathlib import Path

import pytest

import deezy.dee.shim as shim
from deezy.dee.shim import (
    DeeShim,
    clean_env,
    find_shim,
    is_shim_command,
    parse_version,
    resolve_shim,
    shim_failure,
)
from deezy.dee.tools import get_executable_extension
from deezy.exceptions import DependencyNotFoundError

EXE = get_executable_extension()


def touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    return path


@pytest.fixture
def no_path(monkeypatch):
    monkeypatch.setattr(shim.shutil, "which", lambda _name: None)


def reports(monkeypatch, version: str | None):
    """Make every dee_shim report `version` to -V; returns the paths asked."""
    asked: list[Path] = []

    def fake(path):
        asked.append(path)
        return version

    monkeypatch.setattr(shim, "shim_version", fake)
    return asked


@pytest.mark.parametrize(
    ("text", "version"),
    [
        ("dee_shim v0.2.1+gc1141a0", (0, 2, 1)),
        ("dee_shim-ddpjoc_encoder v0.2.1+gc1141a0\n", (0, 2, 1)),
        ("dee_shim v1.10.0", (1, 10, 0)),
        ("0.2.1+gc1141a0", (0, 2, 1)),
        ("dee_shim version two", None),
        ("", None),
    ],
)
def test_parse_version(text, version):
    assert parse_version(text) == version


def test_clean_env_drops_what_dee_shim_reads():
    env = {
        "PATH": "x",
        "DSHIM_LOG": "1",
        "DEE_SHIM_PROFILE": "1",
        "RUST_LOG": "debug",
        "rust_log": "debug",
        "DEE_DIR": "kept",
    }
    assert clean_env(env) == {"PATH": "x", "DEE_DIR": "kept"}


def test_found_beside_the_dee_tools_first(tmp_path, no_path):
    dee = tmp_path / "dee"
    beside_dee = touch(dee / f"dee_shim{EXE}")
    touch(tmp_path / "base" / "apps" / "dee_shim" / f"dee_shim{EXE}")
    assert find_shim(tmp_path / "base", dee) == beside_dee


def test_found_in_apps_then_on_path(tmp_path, monkeypatch):
    in_apps = touch(tmp_path / "apps" / "dee_shim" / f"dee_shim{EXE}")
    assert find_shim(tmp_path, tmp_path / "dee") == in_apps
    in_apps.unlink()
    monkeypatch.setattr(shim.shutil, "which", lambda name: f"/bin/{name}")
    assert find_shim(tmp_path, None) == Path(f"/bin/dee_shim{EXE}")


def test_not_found(tmp_path, no_path, monkeypatch):
    reports(monkeypatch, "0.3.0")
    assert resolve_shim(tmp_path, tmp_path) is None


def test_a_found_shim_is_used(tmp_path, no_path, monkeypatch):
    path = touch(tmp_path / f"dee_shim{EXE}")
    reports(monkeypatch, "0.3.0+g2ae7f95")
    assert resolve_shim(tmp_path / "base", tmp_path) == DeeShim(path, "0.3.0+g2ae7f95")


def test_a_given_path_wins(tmp_path, no_path, monkeypatch):
    touch(tmp_path / f"dee_shim{EXE}")
    given = touch(tmp_path / "other" / "shim.exe")
    asked = reports(monkeypatch, "0.3.1")
    found = resolve_shim(tmp_path / "base", tmp_path, str(given))
    assert found == DeeShim(given, "0.3.1")
    assert asked == [given]


def test_a_missing_given_path_is_an_error(tmp_path, no_path, monkeypatch):
    reports(monkeypatch, "0.3.0")
    with pytest.raises(DependencyNotFoundError, match=r"dee_shim \('nope.exe'\)"):
        resolve_shim(tmp_path, tmp_path, "nope.exe")


@pytest.mark.parametrize("version", ["0.2.1+gc1141a0", "0.2.0", None])
def test_an_old_found_shim_is_skipped(tmp_path, no_path, monkeypatch, version):
    touch(tmp_path / f"dee_shim{EXE}")
    reports(monkeypatch, version)
    with pytest.MonkeyPatch.context() as m:
        warnings: list[str] = []
        m.setattr(shim.logger, "warning", warnings.append)
        assert resolve_shim(tmp_path / "base", tmp_path) is None
    assert len(warnings) == 1
    assert "needs 0.3.0 or newer" in warnings[0]


def test_an_old_given_shim_is_an_error(tmp_path, no_path, monkeypatch):
    given = touch(tmp_path / f"dee_shim{EXE}")
    reports(monkeypatch, "0.2.1")
    with pytest.raises(DependencyNotFoundError, match="needs dee_shim 0.3.0 or newer"):
        resolve_shim(tmp_path, tmp_path, str(given))


def test_turned_off_is_never_run(tmp_path, no_path, monkeypatch):
    touch(tmp_path / f"dee_shim{EXE}")
    asked = reports(monkeypatch, "0.3.0")
    assert resolve_shim(tmp_path, tmp_path, "nope.exe", disabled=True) is None
    assert asked == []


def test_argv_puts_the_shim_options_before_deees():
    tool = str(Path("dee") / f"dee_ddpjoc_encoder{EXE}")
    argv = DeeShim(Path("dee_shim"), "0.3.0").argv(
        (tool, "--progress", "-i", "in.atmos"), "--layout", "7.1"
    )
    assert argv == (
        "dee_shim", "ddpjoc_encoder", "--layout", "7.1", "--binary", tool,
        "--", "--progress", "-i", "in.atmos",
    )  # fmt: skip
    assert is_shim_command(argv)
    assert not is_shim_command((tool, "--progress", "-i", "in.atmos"))


@pytest.mark.parametrize(
    ("code", "lines", "message"),
    [
        (
            2,
            ["error: --bitrate 123 is not accepted in mode ddp. Valid: 384", ""],
            "dee_shim refused the job: --bitrate 123 is not accepted in mode ddp.",
        ),
        (
            2,
            [
                "dee_shim ERROR: optional capability preflight: no optional shim "
                "profile for dee_ddp_encoder (Windows, identity 64181F37-08BD5000)"
            ],
            "dee_shim doesn't support this DEE build (optional capability "
            "preflight: no optional shim profile for dee_ddp_encoder",
        ),
        (3, [], "dee_shim doesn't support this DEE build. Use a dee_shim"),
        (1, ["error: not the shim's"], None),
        (2, ["[2026-11-21 20:14:27.368] ERROR: DEE's own"], None),
    ],
)
def test_shim_failure(code, lines, message):
    found = shim_failure(code, lines)
    if message is None:
        assert found is None
    else:
        assert found is not None
        assert found.startswith(message)


@pytest.fixture
def parser():
    import deezy.cli as cli

    main = cli.create_main_parser()
    sub = main.add_subparsers(dest="sub_command")
    groups = cli.create_common_argument_groups()
    cli.create_encode_parsers(sub, groups)
    cli.create_other_parsers(sub, groups)
    return main


class FakeConfig:
    def __init__(self, global_defaults=None, dependencies=None):
        self.config = {
            "global_defaults": global_defaults or {},
            "dependencies": dependencies or {},
        }


def asked_for(monkeypatch, parser, argv, config=None):
    """What `handle_dependencies` asks `resolve_shim` for: (path, disabled)."""
    from deezy.cli import utils

    calls = []
    monkeypatch.setattr(
        utils,
        "resolve_shim",
        lambda _base, _dee, user, disabled: calls.append((user, disabled)),
    )
    utils._dee_shim(parser.parse_args(argv), config, Path("dee"))
    return calls


@pytest.mark.parametrize("fmt", ["ddp", "ddp-atmos", "thd", "thd-atmos", "ac4"])
def test_every_encode_takes_the_shim_options(parser, fmt):
    args = parser.parse_args(["encode", fmt, "--dee-shim", "s.exe", "--no-shim", "in"])
    assert (args.dee_shim, args.no_shim) == ("s.exe", True)


def test_measure_takes_the_shim_options(monkeypatch, parser):
    args = parser.parse_args(["measure", "--dee-shim", "s.exe", "--no-shim", "in"])
    assert (args.dee_shim, args.no_shim) == ("s.exe", True)
    calls = asked_for(monkeypatch, parser, ["measure", "--dee-shim", "s.exe", "in"])
    assert calls == [("s.exe", False)]


def test_the_cli_path_wins_over_the_config(monkeypatch, parser):
    config = FakeConfig(dependencies={"dee_shim": "config.exe"})
    calls = asked_for(
        monkeypatch, parser, ["encode", "ddp", "--dee-shim", "cli.exe", "in"], config
    )
    assert calls == [("cli.exe", False)]
    calls = asked_for(monkeypatch, parser, ["encode", "ddp", "in"], config)
    assert calls == [("config.exe", False)]


def test_no_shim_from_the_cli_or_the_config(monkeypatch, parser):
    calls = asked_for(monkeypatch, parser, ["encode", "ddp", "--no-shim", "in"])
    assert calls == [(None, True)]
    config = FakeConfig(global_defaults={"no_shim": True})
    calls = asked_for(monkeypatch, parser, ["encode", "ddp", "in"], config)
    assert calls == [(None, True)]


def test_shim_binary():
    tool = str(Path("dee") / f"dee_dthd_encoder{EXE}")
    argv = DeeShim(Path("dee_shim"), "0.3.0").argv((tool, "--binary", "x"))
    assert shim.shim_binary(argv) == Path(tool)
    assert shim.shim_binary((tool, "--progress", "1")) is None


def test_a_missing_dee_tool_is_named_before_the_shim_runs(tmp_path):
    from deezy.pipeline.plan import DeeStep
    from deezy.pipeline.run import run_dee

    dee_shim = touch(tmp_path / f"dee_shim{EXE}")
    tool = str(tmp_path / "dee" / f"dee_dthd_encoder{EXE}")
    argv = DeeShim(dee_shim, "0.3.0").argv((tool, "--loglevel", "info"))
    step = DeeStep(argv, tmp_path / "out.thd")
    with pytest.raises(DependencyNotFoundError, match="dee_dthd_encoder.* is not in"):
        run_dee(step, no_progress_bars=True)
