from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
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
    damf_atmos: bool = False

    @property
    def atmos_master(self) -> bool:
        """An Atmos master DEE reads as it is: a DAMF or an ADM BWF."""
        return self.adm_atmos_wav or self.damf_atmos

    @property
    def atmos(self) -> bool:
        """Atmos DEE encodes as Atmos: TrueHD Atmos (via truehdd) or a master."""
        return self.thd_atmos or self.atmos_master
