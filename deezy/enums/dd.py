from enum import Enum

from typing_extensions import override

from deezy.payloads.shared import ChannelBitrates


class DolbyDigitalChannels(Enum):
    AUTO = 0
    MONO = 1
    STEREO = 2
    SURROUND = 6

    @override
    def __str__(self):
        if self is DolbyDigitalChannels.AUTO:
            return "Auto"
        elif self is DolbyDigitalChannels.MONO:
            return "1.0"
        elif self is DolbyDigitalChannels.STEREO:
            return "2.0"
        else:
            return "5.1"

    def to_dee_cmd(self) -> str:
        if self is DolbyDigitalChannels.AUTO:
            return "off"
        elif self is DolbyDigitalChannels.MONO:
            return "mono"
        elif self is DolbyDigitalChannels.STEREO:
            return "stereo"
        else:
            return "5.1"

    def get_bitrate_obj(self) -> ChannelBitrates:
        if self is DolbyDigitalChannels.MONO:
            return ChannelBitrates(
                default=192,
                choices=(
                    96,
                    112,
                    128,
                    160,
                    192,
                    224,
                    256,
                    320,
                    384,
                    448,
                    512,
                    576,
                    640,
                ),
            )
        elif self is DolbyDigitalChannels.STEREO:
            return ChannelBitrates(
                default=224,
                choices=(
                    96,
                    112,
                    128,
                    160,
                    192,
                    224,
                    256,
                    320,
                    384,
                    448,
                    512,
                    576,
                    640,
                ),
            )
        # 5.1
        else:
            return ChannelBitrates(
                default=448, choices=(224, 256, 320, 384, 448, 512, 576, 640)
            )

    @staticmethod
    def get_values_list():
        return [x.value for x in DolbyDigitalChannels if x != DolbyDigitalChannels.AUTO]
