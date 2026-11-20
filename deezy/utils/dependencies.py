from dataclasses import dataclass
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess

from deezy.exceptions import DependencyNotFoundError

# DeeZy drives the DEE 6.7 command-line tools, one executable per codec. This
# one is always present in such a folder, so it identifies it.
SPLIT_DEE_MARKER_TOOL = "dee_ddp_encoder"
SUPPORTED_DEE_VERSION = "6.7"

# Where the Dolby Media Encoder app unpacks the DEE tools (Windows).
_DME_RELATIVE_DIR = Path(
    "Dolby Media Encoder/resources/app.asar.unpacked/resources/dee"
)
_DEE_VERSION_LINE = re.compile(r"Dolby Encoding Engine version (\S+)")


def get_executable_extension() -> str:
    return ".exe" if platform.system() == "Windows" else ""


def split_dee_tool(directory: Path, name: str) -> Path:
    """Path of one DEE executable (e.g. `dee_ddp_encoder`) inside `directory`."""
    return directory / f"{name}{get_executable_extension()}"


def is_split_dee_dir(path: Path) -> bool:
    """True when `path` is a folder holding the DEE encoder executables."""
    return path.is_dir() and split_dee_tool(path, SPLIT_DEE_MARKER_TOOL).is_file()


def dee_version(dee_dir: Path) -> str | None:
    """The version `dee_ddp_encoder --help` reports, e.g. `6.7.0+8e353f99`."""
    try:
        proc = subprocess.run(  # noqa: S603
            [str(split_dee_tool(dee_dir, SPLIT_DEE_MARKER_TOOL)), "--help"],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    found = _DEE_VERSION_LINE.search((proc.stdout or "") + (proc.stderr or ""))
    return found.group(1) if found else None


@dataclass(slots=True)
class Dependencies:
    ffmpeg: Path
    truehdd: Path | None
    # the folder of DEE 6.7 command-line tools
    dee: Path


class FindDependencies:
    __slots__ = ("os_exe",)

    def __init__(self):
        self.os_exe = get_executable_extension()

    def get_dependencies(
        self,
        base_wd: Path,
        user_ffmpeg: str | None = None,
        user_truehdd: str | None = None,
        user_dee: str | None = None,
        require_truehdd: bool = True,
    ) -> Dependencies:
        ffmpeg, truehdd, dee = self._locate_beside_program(base_wd)
        ffmpeg, truehdd, dee = self._locate_on_path(ffmpeg, truehdd, dee)

        # user overrides, reported here rather than as an opaque OSError from
        # the first subprocess launch several steps into an encode
        bad: list[str] = []
        ffmpeg = self._resolve_override("ffmpeg", user_ffmpeg, ffmpeg, bad)
        truehdd = self._resolve_override("truehdd", user_truehdd, truehdd, bad)
        dee = self._resolve_dee_override(user_dee, dee, bad)
        if bad:
            raise DependencyNotFoundError(
                f"Configured dependency path does not exist: {', '.join(bad)}."
            )

        missing = []
        if not ffmpeg:
            missing.append("ffmpeg")
        if require_truehdd and not truehdd:
            missing.append("truehdd")
        if not dee:
            missing.append(f"dee (a folder with {SPLIT_DEE_MARKER_TOOL})")
        if missing:
            raise DependencyNotFoundError(
                f"Failed to detect required dependencies: {', '.join(missing)}."
            )
        return Dependencies(ffmpeg=ffmpeg, truehdd=truehdd, dee=dee)  # pyright: ignore[reportArgumentType]

    @staticmethod
    def check_dee_version(dee_dir: Path) -> str:
        """Refuse any DEE but 6.7.x. Returns the version it reports."""
        version = dee_version(dee_dir)
        if version is None or not version.startswith(f"{SUPPORTED_DEE_VERSION}."):
            raise DependencyNotFoundError(
                f"DeeZy needs the DEE {SUPPORTED_DEE_VERSION} command-line tools, "
                f"but '{dee_dir}' reports {version or 'no version'}."
            )
        return version

    @staticmethod
    def _resolve_override(
        name: str,
        user_value: str | None,
        detected: Path | None,
        bad: list[str],
    ) -> Path | None:
        """Apply a user/config supplied path for `name`, validating it exists.

        A bare command name is accepted and looked up on PATH so an override can
        name a tool the same way a shell would.
        """
        if not user_value or not user_value.strip():
            return Path(detected) if detected else None

        candidate = Path(user_value.strip()).expanduser()
        if candidate.is_file():
            return candidate

        on_path = shutil.which(str(candidate))
        if on_path:
            return Path(on_path)

        bad.append(f"{name} ('{user_value}')")
        return None

    @staticmethod
    def _resolve_dee_override(
        user_value: str | None, detected: Path | None, bad: list[str]
    ) -> Path | None:
        """A user/config DEE: the tools' folder, or the path of one of the tools."""
        if not user_value or not user_value.strip():
            return Path(detected) if detected else None

        candidate = Path(user_value.strip()).expanduser()
        if is_split_dee_dir(candidate):
            return candidate
        if candidate.is_file() and is_split_dee_dir(candidate.parent):
            return candidate.parent
        on_path = shutil.which(str(candidate))
        if on_path and is_split_dee_dir(Path(on_path).parent):
            return Path(on_path).parent

        marker = f"{SPLIT_DEE_MARKER_TOOL}{get_executable_extension()}"
        if candidate.is_dir():
            reason = f", the folder has no {marker}"
        elif candidate.is_file() or on_path:
            reason = (
                f", not a folder with {marker}; the single 'dee' executable is "
                "no longer supported"
            )
        else:
            reason = ""
        bad.append(f"dee ('{user_value}'{reason})")
        return None

    def _locate_beside_program(self, base_wd: Path) -> tuple[Path | None, ...]:
        def check(path: Path) -> Path | None:
            return path if path.is_file() else None

        ffmpeg = check(base_wd / f"apps/ffmpeg/ffmpeg{self.os_exe}")
        truehdd = check(base_wd / f"apps/truehdd/truehdd{self.os_exe}")
        dee_dir = base_wd / "apps/dee"
        dee = dee_dir if is_split_dee_dir(dee_dir) else None
        return ffmpeg, truehdd, dee

    def _locate_on_path(
        self, ffmpeg: Path | None, truehdd: Path | None, dee: Path | None
    ) -> tuple[Path | None, ...]:
        def which(name: str) -> Path | None:
            found = shutil.which(name)
            return Path(found) if found else None

        ffmpeg = ffmpeg or which(f"ffmpeg{self.os_exe}")
        truehdd = truehdd or which(f"truehdd{self.os_exe}")

        # the DEE tools on PATH, then a Dolby Media Encoder install
        if not dee:
            marker = which(f"{SPLIT_DEE_MARKER_TOOL}{self.os_exe}")
            if marker:
                dee = marker.parent
        if not dee:
            dee = self._locate_dolby_media_encoder()
        return ffmpeg, truehdd, dee

    @staticmethod
    def _locate_dolby_media_encoder() -> Path | None:
        """The DEE tools bundled with an installed Dolby Media Encoder."""
        program_files = os.environ.get("ProgramFiles")
        if not program_files:
            return None
        candidate = Path(program_files) / _DME_RELATIVE_DIR
        return candidate if is_split_dee_dir(candidate) else None
