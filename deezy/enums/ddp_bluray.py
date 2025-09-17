from enum import Enum

from typing_extensions import override

from deezy.payloads.shared import ChannelBitrates


class DolbyDigitalPlusBlurayChannels(Enum):
    SURROUNDEX = 8

    @override
    def __str__(self) -> str:
        return "7.1"

    def to_dee_cmd(self) -> str:
        return "off"

    def get_bitrate_obj(self) -> ChannelBitrates:
        return ChannelBitrates(
            default=1280,
            choices=(768, 1024, 1280, 1536, 1664),
        )

    @staticmethod
    def get_values_list() -> list[int]:
        return [DolbyDigitalPlusBlurayChannels.SURROUNDEX.value]
