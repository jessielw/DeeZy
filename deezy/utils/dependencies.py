import platform
import shutil
from dataclasses import dataclass
from pathlib import Path

from deezy.exceptions import DependencyNotFoundError


def get_executable_extension() -> str:
    return ".exe" if platform.system() == "Windows" else ""


@dataclass(slots=True)
class Dependencies:
    ffmpeg: Path
    truehdd: Path | None
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

        # user overrides
        if user_ffmpeg and user_ffmpeg.strip():
            ffmpeg = Path(user_ffmpeg)
        if user_truehdd and user_truehdd.strip():
            truehdd = Path(user_truehdd)
        if user_dee and user_dee.strip():
            dee = Path(user_dee)

        # ensure all are Path or None
        ffmpeg = Path(ffmpeg) if ffmpeg else None
        truehdd = Path(truehdd) if truehdd else None
        dee = Path(dee) if dee else None

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

    def _locate_beside_program(self, base_wd: Path) -> tuple[Path | None, ...]:
        def check(path: Path) -> Path | None:
            return path if path.is_file() else None

        ffmpeg = check(base_wd / f"apps/ffmpeg/ffmpeg{self.os_exe}")
        truehdd = check(base_wd / f"apps/truehdd/truehdd{self.os_exe}")
        dee = check(base_wd / f"apps/dee/dee{self.os_exe}")
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
        return ffmpeg, truehdd, dee
