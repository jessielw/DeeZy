from enum import Enum

from typing_extensions import override

from deezy.dee.spec import get_format
from deezy.enums import CaseInsensitiveEnum
from deezy.payloads.shared import ChannelBitrates


class Ac4EncodingProfile(CaseInsensitiveEnum):
    IMS = "ims"
    IMS_MUSIC = "ims_music"

    @override
    def __str__(self) -> str:
        return self.value

    def to_dee_cmd(self) -> str:
        """The `mode=` value dee_ac4ims_encoder takes."""
        return "music" if self is Ac4EncodingProfile.IMS_MUSIC else "general"


class Ac4Channels(Enum):
    IMMERSIVE_STEREO = 2

    @override
    def __str__(self):
        return str(self.value)

    def get_bitrate_obj(self) -> ChannelBitrates:
        return get_format("ac4-ims").rates("2.0")

    @staticmethod
    def get_values_list():
        return [Ac4Channels.IMMERSIVE_STEREO]
