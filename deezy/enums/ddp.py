from enum import Enum


class DolbyDigitalPlusChannels(Enum):
    AUTO = 0
    MONO = 1
    STEREO = 2
    SURROUND = 6
    SURROUNDEX = 8
    # atmos layouts
    ATMOS_5_1_2 = 512
    ATMOS_5_1_4 = 514
    ATMOS_7_1_2 = 712
    ATMOS_7_1_4 = 714

    @staticmethod
    def get_values_list() -> list[int]:
        return [
            x.value
            for x in DolbyDigitalPlusChannels
            if x != DolbyDigitalPlusChannels.AUTO
        ]

    def __str__(self):
        if self is DolbyDigitalPlusChannels.AUTO:
            return "Auto"
        elif self is DolbyDigitalPlusChannels.MONO:
            return "1.0"
        elif self is DolbyDigitalPlusChannels.STEREO:
            return "2.0"
        elif self is DolbyDigitalPlusChannels.SURROUND:
            return "5.1"
        elif self is DolbyDigitalPlusChannels.SURROUNDEX:
            return "7.1"
        elif self is DolbyDigitalPlusChannels.ATMOS_5_1_2:
            return "5.1.2"
        elif self is DolbyDigitalPlusChannels.ATMOS_5_1_4:
            return "5.1.4"
        elif self is DolbyDigitalPlusChannels.ATMOS_7_1_2:
            return "7.1.2"
        elif self is DolbyDigitalPlusChannels.ATMOS_7_1_4:
            return "7.1.4"
        else:
            return "Unknown"

    def is_atmos(self):
        """Check if this is an Atmos channel layout."""
        return self in (
            DolbyDigitalPlusChannels.ATMOS_5_1_2,
            DolbyDigitalPlusChannels.ATMOS_5_1_4,
            DolbyDigitalPlusChannels.ATMOS_7_1_2,
            DolbyDigitalPlusChannels.ATMOS_7_1_4,
        )

    def is_joc_atmos(self):
        """Check if this is a JOC Atmos layout (5.1.X only)."""
        return self in (
            DolbyDigitalPlusChannels.ATMOS_5_1_2,
            DolbyDigitalPlusChannels.ATMOS_5_1_4,
        )

    def is_bluray_atmos(self):
        """Check if this is a BluRay Atmos layout (7.1.X)."""
        return self in (
            DolbyDigitalPlusChannels.ATMOS_7_1_2,
            DolbyDigitalPlusChannels.ATMOS_7_1_4,
        )

    def get_fallback_layout(self):
        """Get the fallback non-Atmos layout for when source doesn't have Atmos."""
        if self in (
            DolbyDigitalPlusChannels.ATMOS_5_1_2,
            DolbyDigitalPlusChannels.ATMOS_5_1_4,
        ):
            return DolbyDigitalPlusChannels.SURROUND
        elif self in (
            DolbyDigitalPlusChannels.ATMOS_7_1_2,
            DolbyDigitalPlusChannels.ATMOS_7_1_4,
        ):
            return DolbyDigitalPlusChannels.SURROUNDEX
        else:
            return self

    @classmethod
    def from_string(cls, value):
        """Parse channel layout from string (e.g., '5.1.2' -> ATMOS_5_1_2)."""
        if isinstance(value, str):
            # standard layouts
            if value == "1.0":
                return cls.MONO
            elif value == "2.0":
                return cls.STEREO
            elif value == "5.1":
                return cls.SURROUND
            elif value == "7.1":
                return cls.SURROUNDEX
            # atmos layouts
            elif value == "5.1.2":
                return cls.ATMOS_5_1_2
            elif value == "5.1.4":
                return cls.ATMOS_5_1_4
            elif value == "7.1.2":
                return cls.ATMOS_7_1_2
            elif value == "7.1.4":
                return cls.ATMOS_7_1_4
        # return original value if no conversion found
        return value
