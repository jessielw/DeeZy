"""
How FFmpeg's PCM reaches DEE.

Only a WAV file in the job's temp directory for now. Named pipes and stdin
would slot in here: FFmpeg's output target on one side, DEE's input on the other.
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class WavFile:
    path: Path

    def ffmpeg_output(self) -> list[str]:
        """FFmpeg's output options and target. RF64 lifts WAV's 4 GB limit."""
        return ["-rf64", "always", str(self.path)]

    @property
    def dee_input(self) -> Path:
        return self.path
