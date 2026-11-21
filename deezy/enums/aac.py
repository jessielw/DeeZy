from typing_extensions import override

from deezy.dee.spec import get_format
from deezy.enums import CaseInsensitiveEnum
from deezy.payloads.shared import ChannelBitrates


class AacProfile(CaseInsensitiveEnum):
    """The AAC profiles dee_aac_encoder encodes; the value is its -e mode."""

    AAC_LC = "aaclc"
    HE_AAC = "heaac"
    HE_AAC_V2 = "heaacv2"

    @override
    def __str__(self) -> str:
        return self.value

    def to_dee_cmd(self) -> str:
        return self.value

    def get_bitrate_obj(self) -> ChannelBitrates:
        # the output is always 2.0, so each profile has one layout
        return get_format("aac").rates("2.0", mode=self.value)
