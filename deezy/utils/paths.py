"""Helpers for handing paths to DEE.

DEE is not long-path aware on Windows: ``dee.exe`` ships without a
``longPathAware`` manifest, so it is capped at ``MAX_PATH`` no matter what the
system-wide ``LongPathsEnabled`` setting says. Past that it reports a perfectly
good file as ``Cannot open file`` (for the job JSON) or ``does not exist`` (for
inputs named inside it), so anything longer has to be handed over as an
extended-length path instead.
"""

import hashlib
import os
from pathlib import Path

from deezy.utils.utils import clean_string

# Windows MAX_PATH, less the terminating null. POSIX has no comparable limit
# (PATH_MAX is 4096), so nothing there ever needs the extended-length form.
MAX_DEE_PATH = 259 if os.name == "nt" else 4095

_ARTIFACT_PREFIX_LEN = 24
_ARTIFACT_DIGEST_LEN = 16

# Longest name we give a temp artifact: an `artifact_stem` plus the longest
# suffix appended to one. Used to budget how deep a temp directory may be.
MAX_ARTIFACT_NAME = (
    _ARTIFACT_PREFIX_LEN + 1 + _ARTIFACT_DIGEST_LEN + len("_metadata.json")
)

_EXTENDED_PREFIX = "\\\\?\\"
_UNC_PREFIX = "\\\\"


def long_path_str(path: Path | str, limit: int = MAX_DEE_PATH) -> str:
    """
    Render `path` for a consumer that cannot open a long one, escaping to an
    extended-length path when it is too long.

    That consumer is usually DEE, but it is also us: Python honours long paths
    only where the host enables them, so the final move to a long destination
    needs the same escape.

    The escape is applied only when it is both needed and usable. It requires
    Windows and a fully qualified path, and it changes how DEE echoes the path
    back in its logs, so paths that already fit are passed through untouched.
    """
    text = str(path)
    if len(text) <= limit or not _can_use_extended_path(text):
        return text

    # extended-length paths bypass normalization, so they must be normalized here
    resolved = os.path.abspath(text)
    if resolved.startswith(_UNC_PREFIX):
        return f"{_EXTENDED_PREFIX}UNC{resolved[1:]}"
    return f"{_EXTENDED_PREFIX}{resolved}"


def artifact_stem(output: Path) -> str:
    """
    Build a short, deterministic stem for the temp artifacts belonging to `output`.

    Temp artifacts are internal, so they do not need to carry the full output
    name, and they cannot afford to. Callers may hand us a very long `--output`
    (a GUI writing a partial file such as
    ``.<release name> [Audio 1] [8ch] [Eac3].<32 hex>.part.ec3`` is 145
    characters of stem by itself), which copied onto every temp file used to
    push a job past MAX_PATH before DEE ever saw it.

    The digest is taken over the whole stem so two outputs that share a
    truncated prefix still get their own artifacts, and it is stable across
    runs so `--reuse-temp-files` keeps working.
    """
    digest = hashlib.sha1(
        output.stem.encode("utf-8"), usedforsecurity=False
    ).hexdigest()[:_ARTIFACT_DIGEST_LEN]
    return f"{clean_string(output.stem)[:_ARTIFACT_PREFIX_LEN]}_{digest}"


def _can_use_extended_path(text: str) -> bool:
    """Extended-length paths are a Windows feature and need a qualified path."""
    if os.name != "nt" or text.startswith(_EXTENDED_PREFIX):
        return False
    return Path(text).is_absolute()
