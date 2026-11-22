"""`deezy tools`: the tools DeeZy finds, where they are and their versions."""

import argparse

import pytest

import deezy.cli as cli
from deezy.cli import tools_report
from deezy.cli.tools_report import tool_lines, tool_rows
from deezy.dee.tools import get_executable_extension

EXE = get_executable_extension()
VERSIONS = {
    "ffmpeg": "7.1",
    "truehdd": "0.6.3",
    "dee": "6.7.0+8e353f99",
    "dee_shim": "0.2.1+gc1141a0",
}


@pytest.fixture
def versions() -> dict[str, str]:
    """What each tool reports; a test may change it."""
    return dict(VERSIONS)


@pytest.fixture
def base(tmp_path, monkeypatch, versions):
    """A DeeZy folder with every tool in apps/, and nothing on PATH."""
    for name in ("ffmpeg", "truehdd", "dee_shim"):
        tool = tmp_path / "apps" / name / f"{name}{EXE}"
        tool.parent.mkdir(parents=True)
        tool.touch()
    dee_dir = tmp_path / "apps" / "dee"
    dee_dir.mkdir(parents=True)
    (dee_dir / f"dee_ddp_encoder{EXE}").touch()
    (dee_dir / "license.lic").touch()
    monkeypatch.setattr("deezy.dee.tools.shutil.which", lambda _n: None)
    monkeypatch.setattr("deezy.dee.shim.shutil.which", lambda _n: None)
    monkeypatch.delenv("ProgramFiles", raising=False)
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.setattr(tools_report, "ffmpeg_version", lambda _p: versions["ffmpeg"])
    monkeypatch.setattr(tools_report, "truehdd_version", lambda _p: versions["truehdd"])
    monkeypatch.setattr(tools_report, "dee_version", lambda _p: versions["dee"])
    monkeypatch.setattr(tools_report, "shim_version", lambda _p: versions["dee_shim"])
    return tmp_path


def by_name(rows):
    return {row.name: row for row in rows}


def test_every_tool_is_listed_with_its_version_and_path(base):
    rows = tool_rows(base)
    assert [row.name for row in rows] == ["ffmpeg", "truehdd", "DEE", "dee_shim"]
    assert all(row.ok and not row.note for row in rows)
    lines = tool_lines(rows)
    assert lines[0] == "ffmpeg    7.1"
    assert lines[1] == f"          {base / 'apps' / 'ffmpeg' / f'ffmpeg{EXE}'}"
    assert "DEE       6.7.0+8e353f99" in lines
    assert "          license: license.lic beside the tools" in lines
    assert "dee_shim  0.2.1+gc1141a0" in lines


def test_a_dee_deezy_cant_use_is_said_and_fails(base, versions):
    versions["dee"] = "5.2.1"
    dee = by_name(tool_rows(base))["DEE"]
    assert (dee.version, dee.note, dee.ok) == ("5.2.1", "DeeZy needs DEE 6.7", False)
    assert "DEE       5.2.1: DeeZy needs DEE 6.7" in tool_lines([dee])


def test_a_path_given_that_doesnt_exist_fails(base, tmp_path):
    missing = str(tmp_path / "nowhere" / "ffmpeg")
    rows = by_name(tool_rows(base, ffmpeg=missing, dee_shim=missing))
    assert rows["ffmpeg"].note == f"not found at '{missing}'"
    assert not rows["ffmpeg"].ok
    assert rows["dee_shim"].note == f"not found at '{missing}'"
    assert not rows["dee_shim"].ok


def test_only_ffmpeg_and_dee_are_needed(base):
    for name in ("ffmpeg", "truehdd", "dee_shim"):
        (base / "apps" / name / f"{name}{EXE}").unlink()
    (base / "apps" / "dee" / f"dee_ddp_encoder{EXE}").unlink()
    rows = by_name(tool_rows(base))
    assert {name: row.ok for name, row in rows.items()} == {
        "ffmpeg": False,
        "truehdd": True,
        "DEE": False,
        "dee_shim": True,
    }
    assert rows["truehdd"].note == "not found (TrueHD Atmos sources need it)"
    assert rows["dee_shim"].note.startswith("not found (DD+ 7.1 and 7.0")


def test_an_old_dee_shim_is_skipped_unless_it_was_given(base, versions):
    versions["dee_shim"] = "0.1.0"
    found = by_name(tool_rows(base))["dee_shim"]
    assert found.note == "DeeZy needs 0.2.1 or newer, so it isn't used"
    assert found.ok
    given = str(base / "apps" / "dee_shim" / f"dee_shim{EXE}")
    assert not by_name(tool_rows(base, dee_shim=given))["dee_shim"].ok


def test_a_turned_off_dee_shim_says_so(base):
    shim = by_name(tool_rows(base, no_shim=True))["dee_shim"]
    assert (shim.path, shim.note, shim.ok) == (
        None,
        "turned off (--no-shim or no_shim)",
        True,
    )


def test_a_license_elsewhere_or_none_is_said(base):
    dee_dir = base / "apps" / "dee"
    (dee_dir / "license.lic").unlink()
    assert by_name(tool_rows(base))["DEE"].extra == (
        "license: none found; DEE looks for license.lic beside the tools",
    )
    (dee_dir / "dme_license.lic").touch()
    assert by_name(tool_rows(base))["DEE"].extra == (
        f"license: {dee_dir / 'dme_license.lic'}",
    )


def test_the_command_exits_1_when_an_encode_couldnt_run(
    base, versions, monkeypatch, capsys
):
    monkeypatch.setattr(cli, "WORKING_DIRECTORY", base)
    args = argparse.Namespace(
        ffmpeg=None, truehdd=None, dee=None, dee_shim=None, no_shim=False
    )
    cli.execute_tools_command(args, None)
    assert capsys.readouterr().out.startswith("ffmpeg    7.1\n")
    versions["dee"] = "5.2.1"
    with pytest.raises(SystemExit) as exc:
        cli.execute_tools_command(args, None)
    assert exc.value.code == 1


def test_the_command_parses(base):
    main = cli.create_main_parser()
    sub = main.add_subparsers(dest="sub_command")
    groups = cli.create_common_argument_groups()
    cli.create_encode_parsers(sub, groups)
    cli.create_other_parsers(sub, groups)
    args = main.parse_args(["tools", "--no-shim", "--dee", "x"])
    assert (args.sub_command, args.no_shim, args.dee) == ("tools", True, "x")
