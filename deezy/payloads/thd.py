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
    # dee_shim turns DEE's apodizing filter off at 96 kHz, so the stream
    # decodes sample for sample
    as_is: bool = True
    # TrueHD keeps the LFE channel, silenced
    disable_lfe: bool = False
    surround_3db_attenuation: bool = False


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
    # DEE's number_of_elements: 12, 14 or 16 (D7: DeeZy's default is 16)
    atmos_elements: int = 16
    # dee_shim codes a master that fits the elements as it is (object metadata
    # as authored, no noise shaping), so the stream decodes sample for sample
    as_is: bool = True
