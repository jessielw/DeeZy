from pathlib import Path

from deezy.audio_encoders.dee.backends.base import DeeBackend, DeeJobFiles
from deezy.audio_encoders.dee.backends.legacy import LegacyDeeBackend
from deezy.audio_encoders.dee.backends.split import SplitDeeBackend

__all__ = [
    "DeeBackend",
    "DeeJobFiles",
    "LegacyDeeBackend",
    "SplitDeeBackend",
    "get_dee_backend",
]


def get_dee_backend(dee_path: Path) -> DeeBackend:
    """
    Pick the backend for a located DEE.

    A folder is a set of split encoders, anything else is the single ``dee``
    executable.
    """
    dee_path = Path(dee_path)
    if dee_path.is_dir():
        return SplitDeeBackend(dee_path)
    return LegacyDeeBackend(dee_path)
