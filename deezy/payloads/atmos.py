from dataclasses import dataclass

from deezy.enums.atmos import AtmosMode, WarpMode
from deezy.enums.shared import LoudnessPreset
from deezy.payloads.shared import DownmixOnlyPayload


@dataclass(slots=True)
class AtmosPayload(DownmixOnlyPayload):
    atmos_mode: AtmosMode
    thd_warp_mode: WarpMode | None
    # split DEE encoders only
    loudness_preset: LoudnessPreset = LoudnessPreset.MANUAL
    # DEE's DD+ Atmos encoder always shifts the surrounds; dee_shim can turn it off
    surround_90_degree_phase_shift: bool = True
    # dee_shim codes the master's object metadata as authored (--oamd-as-is
    # on) rather than letting DEE smooth it again
    oamd_as_is: bool = True
