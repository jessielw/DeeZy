"""Completed TrueHD Atmos decodes kept in the input track's temp directory."""

import hashlib
import json
from pathlib import Path
import uuid

from deezy.enums.atmos import WarpMode
from deezy.track_info.track_index import TrackIndex


def damf_files(atmos: Path) -> tuple[Path, Path, Path]:
    return atmos, Path(f"{atmos}.audio"), Path(f"{atmos}.metadata")


def _sizes(directory: Path) -> list[int]:
    return [path.stat().st_size for path in damf_files(directory / "atmos_meta.atmos")]


def complete_decode(directory: Path) -> bool:
    try:
        expected = json.loads((directory / "complete.json").read_text(encoding="utf-8"))
        sizes = _sizes(directory)
        return all(sizes) and sizes == expected
    except (OSError, ValueError):
        return False


def mark_decode_complete(directory: Path) -> None:
    sizes = _sizes(directory)
    if not all(sizes):
        raise OSError("truehdd produced an empty DAMF component")
    marker = directory / "complete.tmp"
    marker.write_text(json.dumps(sizes), encoding="utf-8")
    marker.replace(directory / "complete.json")


def decode_directory(
    temp_dir: Path,
    source: Path,
    track: TrackIndex,
    warp: WarpMode | None,
    ffmpeg: Path,
    truehdd: Path,
    *,
    reuse: bool,
) -> Path:
    # Include file identities in the key so replacing the input or either
    # decoder at the same path invalidates older masters.
    identity: list[object] = [str(track), warp.value if warp else None]
    for path in (source, ffmpeg, truehdd):
        stat = path.stat()
        identity.append((str(path.resolve()), stat.st_size, stat.st_mtime_ns))
    digest = hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:16]
    prefix = f"d-{digest}-"
    if reuse:
        for directory in temp_dir.glob(f"{prefix}*"):
            if complete_decode(directory):
                return directory
    # Concurrent misses write private masters. A later job can use either
    # once its completion marker has been published.
    return temp_dir / f"{prefix}{uuid.uuid4().hex[:10]}"
