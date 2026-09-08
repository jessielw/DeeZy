from pathlib import Path
import sys

import pytest

from deezy.exceptions import DependencyNotFoundError
from deezy.utils.dependencies import FindDependencies


@pytest.fixture
def fake_tools(tmp_path, monkeypatch):
    """A base dir holding all three tools where the finder expects them."""
    finder = FindDependencies()
    made = {}
    for name in ("ffmpeg", "truehdd", "dee"):
        tool = tmp_path / "apps" / name / f"{name}{finder.os_exe}"
        tool.parent.mkdir(parents=True)
        tool.touch()
        made[name] = tool
    # keep anything already installed on PATH out of the result
    monkeypatch.setattr("deezy.utils.dependencies.shutil.which", lambda _n: None)
    return finder, tmp_path, made


def test_detects_tools_beside_program(fake_tools):
    finder, base, made = fake_tools
    deps = finder.get_dependencies(base)
    assert (deps.ffmpeg, deps.truehdd, deps.dee) == (
        made["ffmpeg"],
        made["truehdd"],
        made["dee"],
    )


def test_override_replaces_detected_path(fake_tools, tmp_path):
    finder, base, _ = fake_tools
    custom = tmp_path / "custom-ffmpeg"
    custom.touch()

    deps = finder.get_dependencies(base, user_ffmpeg=str(custom))
    assert deps.ffmpeg == custom


def test_missing_override_is_reported(fake_tools, tmp_path):
    """A bad --ffmpeg/--dee path fails up front, not mid-encode."""
    finder, base, _ = fake_tools
    missing = tmp_path / "not-here" / "ffmpeg"

    with pytest.raises(DependencyNotFoundError) as exc:
        finder.get_dependencies(base, user_ffmpeg=str(missing))

    assert "ffmpeg" in str(exc.value)


def test_blank_override_falls_back_to_detection(fake_tools):
    finder, base, made = fake_tools
    deps = finder.get_dependencies(base, user_dee="   ")
    assert deps.dee == made["dee"]


def test_override_may_name_a_tool_on_path(fake_tools, tmp_path, monkeypatch):
    finder, base, _ = fake_tools
    resolved = tmp_path / "elsewhere" / "dee"
    resolved.parent.mkdir()
    resolved.touch()
    monkeypatch.setattr(
        "deezy.utils.dependencies.shutil.which",
        lambda n: str(resolved) if Path(n).name == "dee" else None,
    )

    deps = finder.get_dependencies(base, user_dee="dee")
    assert deps.dee == resolved


def test_truehdd_optional_when_not_required(fake_tools):
    finder, base, made = fake_tools
    made["truehdd"].unlink()

    deps = finder.get_dependencies(base, require_truehdd=False)
    assert deps.truehdd is None

    with pytest.raises(DependencyNotFoundError):
        finder.get_dependencies(base, require_truehdd=True)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows executable suffix")
def test_windows_executable_extension():
    assert FindDependencies().os_exe == ".exe"
