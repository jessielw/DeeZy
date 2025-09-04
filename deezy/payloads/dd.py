from dataclasses import dataclass

from deezy.enums.dd import DolbyDigitalChannels
from deezy.enums.shared import DeeDRC
from deezy.payloads.shared import BaseArgsPayload


@dataclass(slots=True)
class DDPayload(BaseArgsPayload):
    channels: DolbyDigitalChannels = DolbyDigitalChannels.AUTO
    drc: DeeDRC = DeeDRC.MUSIC_LIGHT
