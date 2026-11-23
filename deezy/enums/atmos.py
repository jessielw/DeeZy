from typing_extensions import override

from deezy.dee.spec import get_format
from deezy.enums import CaseInsensitiveEnum
from deezy.payloads.shared import ChannelBitrates


class AtmosMode(CaseInsensitiveEnum):
    # a 5.1 backbone, which DEE encodes alone
    STREAMING = "streaming"
    # 7.1 backbones, through dee_shim: E-AC-3 only, or an AC-3 core for Blu-ray
    STANDARD = "standard"
    BLURAY = "bluray"

    @override
    def __str__(self) -> str:
        return self.name

    def get_bitrate_obj(self) -> ChannelBitrates:
        return get_format("ddp-atmos").rates("atmos", mode=self.value)

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
