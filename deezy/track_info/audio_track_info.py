from dataclasses import dataclass
from pathlib import Path

from pymediainfo import Track


@dataclass(slots=True)
class AudioTrackInfo:
    mi_track: Track
    auto_name: Path | None = None
    fps: float | None = None
    audio_only: bool = False
    recommended_free_space: int | None = None
    duration: float | None = None
    sample_rate: int | None = None
    bit_depth: int | None = None
    channels: int | None = None
    thd_atmos: bool = False
