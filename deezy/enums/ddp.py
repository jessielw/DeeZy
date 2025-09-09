from enum import Enum

from typing_extensions import override

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
        if self is DolbyDigitalPlusChannels.MONO:
            return ChannelBitrates(
                default=64,
                choices=(
                    32,
                    40,
                    48,
                    56,
                    64,
                    72,
                    80,
                    88,
                    96,
                    104,
                    112,
                    120,
                    128,
                    144,
                    160,
                    176,
                    192,
                    200,
                    208,
                    216,
                    224,
                    232,
                    240,
                    248,
                    256,
                    272,
                    288,
                    304,
                    320,
                    336,
                    352,
                    368,
                    384,
                    400,
                    448,
                    512,
                    576,
                    640,
                    704,
                    768,
                    832,
                    896,
                    960,
                    1008,
                    1024,
                ),
            )
        elif self is DolbyDigitalPlusChannels.STEREO:
            return ChannelBitrates(
                default=128,
                choices=(
                    96,
                    104,
                    112,
                    120,
                    128,
                    144,
                    160,
                    176,
                    192,
                    200,
                    208,
                    216,
                    224,
                    232,
                    240,
                    248,
                    256,
                    272,
                    288,
                    304,
                    320,
                    336,
                    352,
                    368,
                    384,
                    400,
                    448,
                    512,
                    576,
                    640,
                    704,
                    768,
                    832,
                    896,
                    960,
                    1008,
                    1024,
                ),
            )
        elif self is DolbyDigitalPlusChannels.SURROUND:
            return ChannelBitrates(
                default=192,
                choices=(
                    192,
                    200,
                    208,
                    216,
                    224,
                    232,
                    240,
                    248,
                    256,
                    272,
                    288,
                    304,
                    320,
                    336,
                    352,
                    368,
                    384,
                    400,
                    448,
                    512,
                    576,
                    640,
                    704,
                    768,
                    832,
                    896,
                    960,
                    1008,
                    1024,
                ),
            )
        # surroundex
        else:
            return ChannelBitrates(
                default=384,
                choices=(
                    384,
                    448,
                    504,
                    576,
                    640,
                    704,
                    768,
                    832,
                    896,
                    960,
                    1008,
                    1024,
                ),
            )

    @staticmethod
    def get_values_list() -> list[int]:
        return [
            x.value
            for x in DolbyDigitalPlusChannels
            if x != DolbyDigitalPlusChannels.AUTO
        ]
