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


class TestSplitDee:
    """Newer DEE releases are a folder of per-codec encoders, not one `dee`."""

    @pytest.fixture
    def split_tools(self, tmp_path, monkeypatch):
        finder = FindDependencies()
        monkeypatch.setattr("deezy.utils.dependencies.shutil.which", lambda _n: None)
        # keep a Dolby Media Encoder install on this machine out of the result
        monkeypatch.delenv("ProgramFiles", raising=False)

        def make(folder: Path) -> Path:
            folder.mkdir(parents=True, exist_ok=True)
            (folder / f"dee_ddp_encoder{finder.os_exe}").touch()
            return folder

        return finder, tmp_path, make

    def base_with_tools(self, base: Path, *, with_dee: bool = False) -> None:
        exe = FindDependencies().os_exe
        for name in ("ffmpeg", "truehdd"):
            tool = base / "apps" / name / f"{name}{exe}"
            tool.parent.mkdir(parents=True)
            tool.touch()
        if with_dee:
            (base / "apps" / "dee").mkdir(parents=True)
            (base / "apps" / "dee" / f"dee{exe}").touch()

    def test_detected_beside_program(self, split_tools):
        finder, base, make = split_tools
        self.base_with_tools(base)
        folder = make(base / "apps" / "dee")

        assert finder.get_dependencies(base).dee == folder

    def test_single_dee_wins_over_split_encoders(self, split_tools):
        finder, base, make = split_tools
        self.base_with_tools(base, with_dee=True)
        make(base / "apps" / "dee")

        assert finder.get_dependencies(base).dee.is_file()

    def test_detected_on_path(self, split_tools, monkeypatch):
        finder, base, make = split_tools
        self.base_with_tools(base)
        folder = make(base / "elsewhere")
        marker = folder / f"dee_ddp_encoder{finder.os_exe}"
        monkeypatch.setattr(
            "deezy.utils.dependencies.shutil.which",
            lambda n: str(marker) if "dee_ddp_encoder" in n else None,
        )

        assert finder.get_dependencies(base).dee == folder

    def test_detected_from_dolby_media_encoder_install(
        self, split_tools, monkeypatch, tmp_path
    ):
        finder, base, make = split_tools
        self.base_with_tools(base)
        program_files = tmp_path / "pf"
        folder = make(
            program_files
            / "Dolby Media Encoder/resources/app.asar.unpacked/resources/dee"
        )
        monkeypatch.setenv("ProgramFiles", str(program_files))

        assert finder.get_dependencies(base).dee == folder

    def test_override_may_name_a_split_folder(self, split_tools, tmp_path):
        finder, base, make = split_tools
        self.base_with_tools(base, with_dee=True)
        folder = make(tmp_path / "custom")

        assert finder.get_dependencies(base, user_dee=str(folder)).dee == folder

    def test_override_folder_without_encoders_is_reported(self, split_tools, tmp_path):
        finder, base, _ = split_tools
        self.base_with_tools(base, with_dee=True)
        empty = tmp_path / "empty"
        empty.mkdir()

        with pytest.raises(DependencyNotFoundError, match="dee_ddp_encoder"):
            finder.get_dependencies(base, user_dee=str(empty))

    def test_folder_override_is_not_accepted_for_other_tools(
        self, split_tools, tmp_path
    ):
        finder, base, make = split_tools
        self.base_with_tools(base, with_dee=True)
        folder = make(tmp_path / "custom")

        with pytest.raises(DependencyNotFoundError):
            finder.get_dependencies(base, user_ffmpeg=str(folder))
