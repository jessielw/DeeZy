from dataclasses import dataclass

from deezy.enums.shared import DeeDRC, LoudnessPreset
from deezy.enums.thd import TrueHDChannels
from deezy.payloads.shared import LoudnessPayload


@dataclass(slots=True)
class TrueHDPayload(LoudnessPayload):
    channels: TrueHDChannels = TrueHDChannels.AUTO
    # every presentation in the stream gets it
    drc: DeeDRC = DeeDRC.FILM_LIGHT
    # 0 measures the dialnorm; any other value is written as it is (skip)
    custom_dialnorm: int = 0
    loudness_preset: LoudnessPreset = LoudnessPreset.MANUAL
