from dataclasses import dataclass

from deezy.enums.dd import DolbyDigitalChannels
from deezy.payloads.shared import BaseArgsPayload


@dataclass(slots=True)
class DDPayload(BaseArgsPayload):
    channels: DolbyDigitalChannels
