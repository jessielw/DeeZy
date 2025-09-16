from enum import Enum

from typing_extensions import override

from deezy.enums import CaseInsensitiveEnum
from deezy.payloads.shared import ChannelBitrates


class Ac4EncodingProfile(CaseInsensitiveEnum):
    IMS = "ims"
    IMS_MUSIC = "ims_music"

    @override
    def __str__(self) -> str:
        return self.value

    def to_dee_cmd(self) -> str:
        return str(self)


class Ac4Channels(Enum):
    IMMERSIVE_STEREO = 2

    @override
    def __str__(self):
        return str(self.value)

    def get_bitrate_obj(self) -> ChannelBitrates:
        return ChannelBitrates(
            default=256,
            choices=(64, 72, 112, 144, 256, 320),
        )

    @staticmethod
    def get_values_list():
        return [Ac4Channels.IMMERSIVE_STEREO]
