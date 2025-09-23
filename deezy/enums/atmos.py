from typing_extensions import override

from deezy.enums import CaseInsensitiveEnum
from deezy.payloads.shared import ChannelBitrates


class AtmosMode(CaseInsensitiveEnum):
    STREAMING = "streaming"
    BLURAY = "bluray"

    @override
    def __str__(self) -> str:
        return self.name

    def get_bitrate_obj(self) -> ChannelBitrates:
        if self is AtmosMode.STREAMING:
            return ChannelBitrates(
                default=448,
                choices=(
                    384,
                    448,
                    512,
                    576,
                    640,
                    768,
                    1024,
                ),
            )
        # BLURAY
        else:
            return ChannelBitrates(
                default=1280,
                choices=(1152, 1280, 1408, 1512, 1536, 1664),
            )

    def get_channels(self) -> int:
        if self is AtmosMode.STREAMING:
            return 6
        else:
            return 8

    def get_str_channels(self) -> str:
        if self is AtmosMode.STREAMING:
            return "5.1"
        else:
            return "7.1"


class WarpMode(CaseInsensitiveEnum):
    NORMAL = "normal"
    WARPING = "warping"
    DPLII = "prologiciix"
    LORO = "loro"

    def to_truehdd_cmd(self) -> str:
        return self.value
