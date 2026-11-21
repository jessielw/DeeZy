"""
A Dolby Atmos Master Format (DAMF) master: a `.atmos` header naming its
`.atmos.metadata` and `.atmos.audio` files. DEE reads the header and both
files; DeeZy reads the header and the audio's CAF header, to probe the master
without a YAML parser or MediaInfo, which misreads the CAF's length.
"""

from dataclasses import dataclass
from pathlib import Path
import re
import struct

from deezy.exceptions import InvalidAtmosInputError

DAMF_SUFFIX = ".atmos"
_PART_SUFFIXES = (".audio", ".metadata")
_LPCM = b"lpcm"


@dataclass(frozen=True, slots=True)
class Damf:
    header: Path
    audio: Path
    metadata: Path
    # every bed channel and object, one audio channel each
    channels: int
    sample_rate: int
    bit_depth: int
    frames: int

    @property
    def duration_ms(self) -> float:
        return self.frames * 1000 / self.sample_rate

    @property
    def size(self) -> int:
        return self.audio.stat().st_size + self.metadata.stat().st_size


def is_damf(path: Path) -> bool:
    return path.suffix.lower() == DAMF_SUFFIX


def damf_header_of(path: Path) -> Path | None:
    """The header of the master ``path`` is the audio or metadata file of."""
    if path.suffix.lower() in _PART_SUFFIXES and is_damf(path.with_suffix("")):
        return path.with_suffix("")
    return None


def _header_value(text: str, key: str) -> str | None:
    found = re.search(rf"^[ \t-]*{key}:[ \t]*(.+?)[ \t]*$", text, re.MULTILINE)
    return found.group(1).strip("'\"") if found else None


def read_damf(header: Path) -> Damf:
    """Read a DAMF master's header and its audio's CAF header."""
    try:
        text = header.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise InvalidAtmosInputError(
            f"Cannot read the DAMF header {header}: {e}"
        ) from None
    names = {key: _header_value(text, key) for key in ("audio", "metadata")}
    missing = [key for key, name in names.items() if not name]
    if missing or "presentations:" not in text:
        raise InvalidAtmosInputError(
            f"{header.name} is not a DAMF header: it names no "
            f"{' or '.join(missing) or 'presentation'}."
        )
    audio, metadata = (
        header.parent / names["audio"],
        header.parent / names["metadata"],
    )
    for part in (audio, metadata):
        if not part.is_file():
            raise InvalidAtmosInputError(
                f"The DAMF master {header.name} names {part.name}, which is missing."
            )
    return Damf(header, audio, metadata, *_read_caf(audio))


def _read_caf(path: Path) -> tuple[int, int, int, int]:
    """(channels, sample rate, bit depth, frames) of a linear PCM CAF file."""
    size = path.stat().st_size
    with path.open("rb") as f:
        if f.read(8)[:4] != b"caff":
            raise InvalidAtmosInputError(f"{path.name} is not a CAF file.")
        desc = None
        while chunk := f.read(12):
            if len(chunk) < 12:
                break
            kind, length = chunk[:4], struct.unpack(">q", chunk[4:])[0]
            if kind == b"desc":
                desc = struct.unpack(">d4sIIIII", f.read(32))
                f.seek(length - 32, 1)
            elif kind == b"data":
                if desc is None:
                    break
                rate, fmt, _flags, packet, frames_per, channels, bits = desc
                if fmt != _LPCM or not packet or frames_per != 1:
                    raise InvalidAtmosInputError(
                        f"{path.name} holds {fmt.decode(errors='replace')} audio, "
                        "not linear PCM."
                    )
                # -1 runs to the end of the file; the data starts with a
                # 4-byte edit count
                data = size - f.tell() if length < 0 else length
                return channels, int(rate), bits, (data - 4) // packet
            else:
                f.seek(length, 1)
    raise InvalidAtmosInputError(f"{path.name} has no CAF audio description or data.")
