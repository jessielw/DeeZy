from dataclasses import dataclass

from deezy.enums.aac import AacProfile
from deezy.enums.shared import LoudnessPreset
from deezy.payloads.shared import LoudnessPayload


@dataclass(slots=True)
class AacPayload(LoudnessPayload):
    aac_profile: AacProfile = AacProfile.AAC_LC
    # None leaves the loudness alone (DEE's skip); AAC has no measure-only mode
    loudness_target: int | None = None
    peak_limit: float | None = None
    loudness_preset: LoudnessPreset = LoudnessPreset.MANUAL
