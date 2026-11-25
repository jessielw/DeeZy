from pathlib import Path

import pytest

from deezy.enums.atmos import WarpMode
from deezy.pipeline.decode_cache import (
    damf_files,
    decode_directory,
    mark_decode_complete,
)
from deezy.track_info.track_index import TrackIndex


def test_reuse_requires_a_complete_matching_decode(tmp_path: Path):
    source, ffmpeg, truehdd = (
        tmp_path / name for name in ("movie", "ffmpeg", "truehdd")
    )
    for file in (source, ffmpeg, truehdd):
        file.write_bytes(b"original")

    audio = TrackIndex.audio(0)

    def choose(track=audio, warp=None, reuse=True):
        return decode_directory(
            tmp_path, source, track, warp, ffmpeg, truehdd, reuse=reuse
        )

    kept = choose(reuse=False)
    kept.mkdir()
    parts = damf_files(kept / "atmos_meta.atmos")
    for part in parts:
        part.write_bytes(b"data")
    assert choose() != kept  # another job is still decoding
    mark_decode_complete(kept)
    assert choose() == kept
    assert choose(reuse=False) != kept
    assert choose(track=TrackIndex.stream(0)) != kept
    assert choose(warp=WarpMode.NORMAL) != kept
    parts[1].write_bytes(b"d")
    assert choose() != kept
    parts[1].write_bytes(b"data")
    parts[2].unlink()
    assert choose() != kept
    with pytest.raises(FileNotFoundError):
        mark_decode_complete(kept)
    parts[2].write_bytes(b"data")
    truehdd.write_bytes(b"updated tool")
    assert choose() != kept
    kept = choose()
    kept.mkdir()
    for part in damf_files(kept / "atmos_meta.atmos"):
        part.write_bytes(b"data")
    mark_decode_complete(kept)
    assert choose() == kept
    source.write_bytes(b"replaced input")
    assert choose() != kept
