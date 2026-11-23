from enum import Enum

from typing_extensions import override


class TrueHDChannels(Enum):
    """The layouts channel-based TrueHD (dee_dthd_encoder) encodes."""

    AUTO = 0
    STEREO = 2
    SURROUND = 6
    SURROUNDEX = 8

    @override
    def __str__(self) -> str:
        return {0: "Auto", 2: "2.0", 6: "5.1", 8: "7.1"}[self.value]

    def to_dee_cmd(self) -> str:
        """dee_dthd_encoder's --presentation name."""
        if self is TrueHDChannels.AUTO:
            raise ValueError("AUTO has no TrueHD presentation")
        return f"{self.value}ch"

    @staticmethod
    def get_values_list() -> list[int]:
        return [x.value for x in TrueHDChannels if x is not TrueHDChannels.AUTO]
