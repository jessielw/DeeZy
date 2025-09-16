from dataclasses import dataclass

from deezy.enums.dd import DolbyDigitalChannels
from deezy.payloads.shared import StereoMixPayload


@dataclass(slots=True)
class DDPayload(StereoMixPayload):
    channels: DolbyDigitalChannels
