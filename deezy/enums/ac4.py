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


class Ac4ChannelBasedChannels(Enum):
    """The layouts channel-based AC-4 (dee_ac4_encoder) encodes."""

    AUTO = 0
    STEREO = 2
    SURROUND = 6

    @override
    def __str__(self) -> str:
        if self is Ac4ChannelBasedChannels.AUTO:
            return "Auto"
        if self is Ac4ChannelBasedChannels.STEREO:
            return "2.0"
        return "5.1"

    def to_dee_cmd(self) -> str:
        """dee_ac4_encoder's -c value."""
        if self is Ac4ChannelBasedChannels.STEREO:
            return "stereo"
        if self is Ac4ChannelBasedChannels.SURROUND:
            return "5.1"
        return "auto"

    def get_bitrate_obj(self) -> ChannelBitrates:
        # AUTO has no rates of its own and gets 5.1's
        layout = "5.1" if self is Ac4ChannelBasedChannels.AUTO else str(self)
        return get_format("ac4").rates(layout)

    @staticmethod
    def get_values_list() -> list[int]:
        return [
            x.value
            for x in Ac4ChannelBasedChannels
            if x is not Ac4ChannelBasedChannels.AUTO
        ]
