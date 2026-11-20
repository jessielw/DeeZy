from typing_extensions import override

from deezy.enums import CaseInsensitiveEnum


class CodecFormat(CaseInsensitiveEnum):
    """Enum for codec format command strings used in config lookups and CLI."""

    DD = "dd"
    DDP = "ddp"
    DDP_BLURAY = "ddp-bluray"
    DDP_ATMOS = "ddp-atmos"
    AC4_IMS = "ac4-ims"

    @override
    def __str__(self) -> str:
        return self.value
