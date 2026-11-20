from pathlib import Path

from deezy.audio_encoders.dee.backends.base import DeeBackend, DeeJobFiles
from deezy.audio_encoders.dee.backends.split import SplitDeeBackend

__all__ = [
    "DeeBackend",
    "DeeJobFiles",
    "SplitDeeBackend",
    "get_dee_backend",
]


def get_dee_backend(dee_path: Path) -> DeeBackend:
    """The backend for a folder of DEE 6.7 command-line tools."""
    return SplitDeeBackend(Path(dee_path))
