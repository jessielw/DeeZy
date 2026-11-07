from dataclasses import dataclass

from deezy.enums.atmos import AtmosMode, WarpMode
from deezy.enums.shared import LoudnessPreset
from deezy.payloads.shared import DownmixOnlyPayload


@dataclass(slots=True)
class AtmosPayload(DownmixOnlyPayload):
    atmos_mode: AtmosMode
    thd_warp_mode: WarpMode
    bed_conform: bool
    # split DEE encoders only
    loudness_preset: LoudnessPreset = LoudnessPreset.MANUAL
