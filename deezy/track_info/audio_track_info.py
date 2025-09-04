from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class AudioTrackInfo:
    auto_name: Path | None = None
    fps: float | None = None
    audio_only: bool = False
    recommended_free_space: int | None = None
    duration: float | None = None
    sample_rate: int | None = None
    bit_depth: int | None = None
    channels: int | None = None
