from dataclasses import dataclass
import os
from pathlib import Path
import platform
import shutil

from deezy.exceptions import DependencyNotFoundError

# Newer DEE releases ship one encoder executable per codec instead of a single
# `dee`. This one is always present in such a folder, so it identifies it.
SPLIT_DEE_MARKER_TOOL = "dee_ddp_encoder"

# Where the Dolby Media Encoder app unpacks the split DEE tools (Windows).
_DME_RELATIVE_DIR = Path(
    "Dolby Media Encoder/resources/app.asar.unpacked/resources/dee"
)


def get_executable_extension() -> str:
    return ".exe" if platform.system() == "Windows" else ""


def split_dee_tool(directory: Path, name: str) -> Path:
    """Path of one split DEE executable (e.g. `dee_ddp_encoder`) inside `directory`."""
    return directory / f"{name}{get_executable_extension()}"


def is_split_dee_dir(path: Path) -> bool:
    """True when `path` is a folder holding the split DEE encoder executables."""
    return path.is_dir() and split_dee_tool(path, SPLIT_DEE_MARKER_TOOL).is_file()


@dataclass(slots=True)
class Dependencies:
    ffmpeg: Path
    truehdd: Path | None
    # either the single `dee` executable, or a folder of split DEE encoders
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
        dee = self._resolve_override("dee", user_dee, dee, bad, allow_split_dir=True)
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
            missing.append("dee")
        if missing:
            raise DependencyNotFoundError(
                f"Failed to detect required dependencies: {', '.join(missing)}."
            )
        return Dependencies(ffmpeg=ffmpeg, truehdd=truehdd, dee=dee)  # pyright: ignore[reportArgumentType]

    @staticmethod
    def _resolve_override(
        name: str,
        user_value: str | None,
        detected: Path | None,
        bad: list[str],
        allow_split_dir: bool = False,
    ) -> Path | None:
        """Apply a user/config supplied path for `name`, validating it exists.

        A bare command name is accepted and looked up on PATH so an override can
        name a tool the same way a shell would. With `allow_split_dir` a folder
        of split DEE encoders is accepted in place of an executable.
        """
        if not user_value or not user_value.strip():
            return Path(detected) if detected else None

        candidate = Path(user_value.strip()).expanduser()
        if candidate.is_file():
            return candidate
        if allow_split_dir and is_split_dee_dir(candidate):
            return candidate

        on_path = shutil.which(str(candidate))
        if on_path:
            return Path(on_path)

        reason = ""
        if allow_split_dir and candidate.is_dir():
            reason = f", the folder has no {SPLIT_DEE_MARKER_TOOL}{get_executable_extension()}"
        bad.append(f"{name} ('{user_value}'{reason})")
        return None

    def _locate_beside_program(self, base_wd: Path) -> tuple[Path | None, ...]:
        def check(path: Path) -> Path | None:
            return path if path.is_file() else None

        ffmpeg = check(base_wd / f"apps/ffmpeg/ffmpeg{self.os_exe}")
        truehdd = check(base_wd / f"apps/truehdd/truehdd{self.os_exe}")
        dee_dir = base_wd / "apps/dee"
        dee = check(dee_dir / f"dee{self.os_exe}")
        # a single `dee` is preferred; otherwise accept the split encoders
        if not dee and is_split_dee_dir(dee_dir):
            dee = dee_dir
        return ffmpeg, truehdd, dee

    def _locate_on_path(
        self, ffmpeg: Path | None, truehdd: Path | None, dee: Path | None
    ) -> tuple[Path | None, ...]:
        def which(name: str) -> Path | None:
            found = shutil.which(name)
            return Path(found) if found else None

        ffmpeg = ffmpeg or which(f"ffmpeg{self.os_exe}")
        truehdd = truehdd or which(f"truehdd{self.os_exe}")
        dee = dee or which(f"dee{self.os_exe}")

        # no single `dee` anywhere: fall back to split encoders on PATH, then to
        # a Dolby Media Encoder install
        if not dee:
            split = which(f"{SPLIT_DEE_MARKER_TOOL}{self.os_exe}")
            if split:
                dee = split.parent
        if not dee:
            dee = self._locate_dolby_media_encoder()
        return ffmpeg, truehdd, dee

    @staticmethod
    def _locate_dolby_media_encoder() -> Path | None:
        """The split DEE tools bundled with an installed Dolby Media Encoder."""
        program_files = os.environ.get("ProgramFiles")
        if not program_files:
            return None
        candidate = Path(program_files) / _DME_RELATIVE_DIR
        return candidate if is_split_dee_dir(candidate) else None
