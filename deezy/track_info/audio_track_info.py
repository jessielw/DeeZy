from dataclasses import dataclass

from pymediainfo import Track


@dataclass(slots=True)
class AudioTrackInfo:
    mi_track: Track
    channels: int
    delay_relative_to_video: int
    fps: float | None = None
    audio_only: bool = False
    recommended_free_space: int | None = None
    duration: float | None = None
    sample_rate: int | None = None
    bit_depth: int | None = None
    thd_atmos: bool = False
    adm_atmos_wav: bool = False
