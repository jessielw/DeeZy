from enum import Enum

from typing_extensions import override

from deezy.dee.spec import get_format
from deezy.payloads.shared import ChannelBitrates


class DolbyDigitalPlusChannels(Enum):
    AUTO = 0
    MONO = 1
    STEREO = 2
    SURROUND = 6
    SURROUNDEX = 8

    @override
    def __str__(self) -> str:
        if self is DolbyDigitalPlusChannels.AUTO:
            return "Auto"
        elif self is DolbyDigitalPlusChannels.MONO:
            return "1.0"
        elif self is DolbyDigitalPlusChannels.STEREO:
            return "2.0"
        elif self is DolbyDigitalPlusChannels.SURROUND:
            return "5.1"
        # surroundex
        else:
            return "7.1"

    def to_dee_cmd(self) -> str:
        if self is DolbyDigitalPlusChannels.AUTO:
            return "off"
        elif self is DolbyDigitalPlusChannels.MONO:
            return "mono"
        elif self is DolbyDigitalPlusChannels.STEREO:
            return "stereo"
        elif self is DolbyDigitalPlusChannels.SURROUND:
            return "5.1"
        # surroundex
        else:
            return "off"

    def get_bitrate_obj(self) -> ChannelBitrates:
        # AUTO has no rates of its own and gets 7.1's
        layout = "7.1" if self is DolbyDigitalPlusChannels.AUTO else str(self)
        return get_format("ddp").rates(layout)

    @staticmethod
    def get_values_list() -> list[int]:
        return [
            x.value
            for x in DolbyDigitalPlusChannels
            if x != DolbyDigitalPlusChannels.AUTO
        ]
