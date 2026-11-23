from pathlib import Path
import sys

import pytest

from deezy.dee import tools
from deezy.dee.tools import FindDependencies, find_license
from deezy.exceptions import DependencyNotFoundError


@pytest.fixture
def fake_tools(tmp_path, monkeypatch):
    """A base dir holding all three tools where the finder expects them."""
    finder = FindDependencies()
    made = {}
    for name in ("ffmpeg", "truehdd"):
        tool = tmp_path / "apps" / name / f"{name}{finder.os_exe}"
        tool.parent.mkdir(parents=True)
        tool.touch()
        made[name] = tool
    # DEE 6.7 is a folder of per-codec tools
    dee_dir = tmp_path / "apps" / "dee"
    dee_dir.mkdir(parents=True)
    (dee_dir / f"dee_ddp_encoder{finder.os_exe}").touch()
    made["dee"] = dee_dir
    # keep anything already installed on PATH out of the result
    monkeypatch.setattr("deezy.dee.tools.shutil.which", lambda _n: None)
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
    resolved = tmp_path / "elsewhere" / "ffmpeg"
    resolved.parent.mkdir()
    resolved.touch()
    monkeypatch.setattr(
        "deezy.dee.tools.shutil.which",
        lambda n: str(resolved) if Path(n).name == "ffmpeg" else None,
    )

    deps = finder.get_dependencies(base, user_ffmpeg="ffmpeg")
    assert deps.ffmpeg == resolved


def test_dee_override_may_name_one_of_the_tools(fake_tools, tmp_path):
    finder, base, _ = fake_tools
    folder = tmp_path / "dee67"
    folder.mkdir()
    tool = folder / f"dee_ddp_encoder{finder.os_exe}"
    tool.touch()

    assert finder.get_dependencies(base, user_dee=str(tool)).dee == folder


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
        monkeypatch.setattr("deezy.dee.tools.shutil.which", lambda _n: None)
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

    def test_single_dee_is_not_detected(self, split_tools):
        finder, base, _ = split_tools
        self.base_with_tools(base, with_dee=True)

        with pytest.raises(DependencyNotFoundError, match="dee_ddp_encoder"):
            finder.get_dependencies(base)

    def test_single_dee_override_is_rejected(self, split_tools, tmp_path):
        finder, base, make = split_tools
        self.base_with_tools(base)
        make(base / "apps" / "dee")
        single = tmp_path / "old" / f"dee{finder.os_exe}"
        single.parent.mkdir()
        single.touch()

        with pytest.raises(DependencyNotFoundError, match="no longer supported"):
            finder.get_dependencies(base, user_dee=str(single))

    def test_detected_on_path(self, split_tools, monkeypatch):
        finder, base, make = split_tools
        self.base_with_tools(base)
        folder = make(base / "elsewhere")
        marker = folder / f"dee_ddp_encoder{finder.os_exe}"
        monkeypatch.setattr(
            "deezy.dee.tools.shutil.which",
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


class TestDeeVersion:
    @pytest.mark.parametrize("version", ["6.7.0+8e353f99", "6.7.1"])
    def test_6_7_is_accepted(self, monkeypatch, tmp_path, version):
        monkeypatch.setattr("deezy.dee.tools.dee_version", lambda _d: version)
        assert FindDependencies.check_dee_version(tmp_path) == version

    @pytest.mark.parametrize("version", ["5.2.1", "6.6.0", "6.70.0", None])
    def test_anything_else_is_refused(self, monkeypatch, tmp_path, version):
        monkeypatch.setattr("deezy.dee.tools.dee_version", lambda _d: version)
        with pytest.raises(DependencyNotFoundError, match="DEE 6.7"):
            FindDependencies.check_dee_version(tmp_path)

    def test_version_is_read_from_help(self, monkeypatch, tmp_path):
        class Proc:
            stdout = "Dolby Encoding Engine version 6.7.0+8e353f99"
            stderr = ""

        monkeypatch.setattr(tools.subprocess, "run", lambda *a, **k: Proc())
        assert tools.dee_version(tmp_path) == "6.7.0+8e353f99"


class TestFindLicense:
    @pytest.fixture
    def no_appdata(self, monkeypatch):
        monkeypatch.delenv("APPDATA", raising=False)

    def test_none_when_the_tools_find_their_own(self, tmp_path, no_appdata):
        (tmp_path / "license.lic").touch()
        (tmp_path / "dme_license.lic").touch()
        assert find_license(tmp_path) is None

    def test_dolby_media_encoder_license_beside_the_tools(self, tmp_path, no_appdata):
        (tmp_path / "dme_license.lic").touch()
        assert find_license(tmp_path) == tmp_path / "dme_license.lic"

    def test_dolby_media_encoder_license_in_appdata(self, tmp_path, monkeypatch):
        appdata = tmp_path / "appdata"
        found = appdata / "Dolby Media Encoder" / "license.lic"
        found.parent.mkdir(parents=True)
        found.touch()
        monkeypatch.setenv("APPDATA", str(appdata))
        assert find_license(tmp_path / "dee") == found

    def test_none_when_nothing_is_found(self, tmp_path, no_appdata):
        assert find_license(tmp_path) is None
