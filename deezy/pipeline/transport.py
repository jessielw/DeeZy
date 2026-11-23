"""
How FFmpeg's PCM reaches DEE.

`WavFile` is a WAV in the job's temp directory: FFmpeg writes it, then DEE
reads it. `NamedPipe` streams the PCM instead: DEE opens a Windows named pipe,
FFmpeg writes raw samples into it, and the two run at once, so no WAV is
written. Each gives FFmpeg's codec and output target, and DEE's input format
and input.
"""

from dataclasses import dataclass
import math
from pathlib import Path

from deezy.audio_processors.pipe import PIPE_ROOT

# FFmpeg resamples to DEE's only rate before either transport
SAMPLE_RATE = 48000
# bytes per sample of the pipe's 24-bit PCM
PIPE_SAMPLE_BYTES = 3


def expected_samples(duration_ms: float | None) -> int | None:
    """
    The samples per channel DEE is told a pipe will carry, so it can show its
    progress: the source's length (MediaInfo's, in milliseconds) plus 1% and a
    second, or None when unknown.

    Told too few, DEE silently stops at the count, which the runner catches;
    told too many, it encodes the same and only finishes its progress late.
    """
    if not duration_ms or duration_ms <= 0:
        return None
    return math.ceil(duration_ms / 1000 * SAMPLE_RATE * 1.01) + SAMPLE_RATE


@dataclass(frozen=True, slots=True)
class WavFile:
    path: Path

    @property
    def ffmpeg_codec(self) -> str:
        """32-bit integer, which holds any 24-bit source sample exactly."""
        return "pcm_s32le"

    def ffmpeg_output(self) -> list[str]:
        """FFmpeg's output options and target. RF64 lifts WAV's 4 GB limit."""
        return ["-rf64", "always", str(self.path)]

    @property
    def dee_input_format(self) -> str:
        return "wav"

    @property
    def dee_input(self) -> Path:
        return self.path


@dataclass(frozen=True, slots=True)
class NamedPipe:
    """
    A Windows named pipe that DEE reads raw PCM from.

    DEE creates the pipe, so it starts first; FFmpeg then opens the pipe as its
    output file. DEE's raw input has no 32-bit integer format, so the samples
    are 24-bit integers, which hold any 24-bit source exactly. Not float:
    FFmpeg scales a downmix down to avoid clipping only when it writes
    integers, so a float pipe would carry its -ac and DPL II downmixes louder
    than the temp WAV does (2.4x and 3.1x from 5.1). ``channels`` is what
    FFmpeg writes, which raw PCM doesn't record, so DEE is told.
    """

    # unique to the job: DeeZy's process ID and the job's temp directory
    name: str
    channels: int
    # see `expected_samples`; without it DEE shows only coarse progress
    sample_count: int | None = None

    @property
    def path(self) -> str:
        return PIPE_ROOT + self.name

    @property
    def ffmpeg_codec(self) -> str:
        return "pcm_s24le"

    def ffmpeg_output(self) -> list[str]:
        return ["-f", "s24le", self.path]

    @property
    def frame_bytes(self) -> int:
        """The bytes of one sample in every channel."""
        return PIPE_SAMPLE_BYTES * self.channels

    @property
    def dee_input_format(self) -> str:
        fmt = f"pcm_s24le:sample_rate={SAMPLE_RATE}:channels={self.channels}"
        if self.sample_count is not None:
            fmt += f":sample_count={self.sample_count}"
        return fmt + ":streaming=1"

    @property
    def dee_input(self) -> str:
        return "named_pipe://" + self.path


Transport = WavFile | NamedPipe
