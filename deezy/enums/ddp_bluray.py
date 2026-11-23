from enum import Enum

from typing_extensions import override

from deezy.dee.spec import get_format
from deezy.payloads.shared import ChannelBitrates


class DolbyDigitalPlusBlurayChannels(Enum):
    SURROUNDEX = 8

    @override
    def __str__(self) -> str:
        return "7.1"

    def to_dee_cmd(self) -> str:
        return "off"

    def get_bitrate_obj(self) -> ChannelBitrates:
        return get_format("ddp-bluray").rates(str(self), mode="bluray")

    @staticmethod
    def get_values_list() -> list[int]:
        return [DolbyDigitalPlusBlurayChannels.SURROUNDEX.value]
