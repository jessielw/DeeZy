from dataclasses import dataclass

from deezy.enums.ddp import DolbyDigitalPlusChannels
from deezy.enums.shared import DeeDRC
from deezy.payloads.shared import BaseArgsPayload


@dataclass(slots=True)
class DDPPayload(BaseArgsPayload):
    channels: DolbyDigitalPlusChannels = DolbyDigitalPlusChannels.AUTO
    normalize: bool = False
    drc: DeeDRC = DeeDRC.MUSIC_LIGHT
    atmos: bool = False
    no_bed_conform: bool = False
