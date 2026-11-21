from dataclasses import dataclass

from deezy.enums.atmos import WarpMode
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


@dataclass(slots=True)
class TrueHDAtmosPayload(LoudnessPayload):
    # the Atmos presentation and every downmix of it get it
    drc: DeeDRC = DeeDRC.FILM_LIGHT
    # 0 measures the dialnorm; any other value is written as it is (skip)
    custom_dialnorm: int = 0
    loudness_preset: LoudnessPreset = LoudnessPreset.MANUAL
    # for a TrueHD Atmos source, the warp mode truehdd writes when it has none
    thd_warp_mode: WarpMode | None = None
    # DEE's legacy_authoring=1, for older disc-authoring tools; the stream then
    # carries no warp mode
    legacy_authoring: bool = False
