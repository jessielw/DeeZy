from typing_extensions import override

from deezy.enums import CaseInsensitiveEnum


class CodecFormat(CaseInsensitiveEnum):
    """Enum for codec format command strings used in config lookups and CLI."""

    DD = "dd"
    DDP = "ddp"
    DDP_BLURAY = "ddp-bluray"
    ATMOS = "atmos"
    AC4 = "ac4"

    @override
    def __str__(self) -> str:
        return self.value
