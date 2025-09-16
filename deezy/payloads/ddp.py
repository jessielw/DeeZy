from dataclasses import dataclass

from deezy.enums.ddp import DolbyDigitalPlusChannels
from deezy.enums.ddp_bluray import DolbyDigitalPlusBlurayChannels
from deezy.payloads.shared import StereoMixPayload


@dataclass(slots=True)
class DDPPayload(StereoMixPayload):
    channels: DolbyDigitalPlusChannels | DolbyDigitalPlusBlurayChannels
