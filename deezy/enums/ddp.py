from enum import Enum


class DolbyDigitalPlusChannels(Enum):
    AUTO = 0
    MONO = 1
    STEREO = 2
    SURROUND = 6
    SURROUNDEX = 8

    @staticmethod
    def get_values_list():
        return [
            x.value
            for x in DolbyDigitalPlusChannels
            if x != DolbyDigitalPlusChannels.AUTO
        ]

    def __str__(self):
        if self == DolbyDigitalPlusChannels.AUTO:
            return "Auto"
        elif self == DolbyDigitalPlusChannels.MONO:
            return "1.0"
        elif self == DolbyDigitalPlusChannels.STEREO:
            return "2.0"
        elif self == DolbyDigitalPlusChannels.SURROUND:
            return "5.1"
        elif self == DolbyDigitalPlusChannels.SURROUNDEX:
            return "7.1"
