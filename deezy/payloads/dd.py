from dataclasses import dataclass

from deezy.enums.dd import DolbyDigitalChannels
from deezy.enums.shared import StereoDownmix
from deezy.payloads.shared import BaseArgsPayload


@dataclass(slots=True)
class DDPayload(BaseArgsPayload):
    channels: DolbyDigitalChannels
    lfe_lowpass_filter: bool
    surround_90_degree_phase_shift: bool
    surround_3db_attenuation: bool
    loro_center_mix_level: str
    loro_surround_mix_level: str
    ltrt_center_mix_level: str
    ltrt_surround_mix_level: str
    preferred_downmix_mode: StereoDownmix
