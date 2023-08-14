from enum import Enum


class DolbyDigitalChannels(Enum):
    AUTO = 0
    MONO = 1
    STEREO = 2
    SURROUND = 6

    @staticmethod
    def get_values_list():
        return [x.value for x in DolbyDigitalChannels if x != DolbyDigitalChannels.AUTO]

    def __str__(self):
        if self == DolbyDigitalChannels.AUTO:
            return "Auto"
        elif self == DolbyDigitalChannels.MONO:
            return "1.0"
        elif self == DolbyDigitalChannels.STEREO:
            return "2.0"
        elif self == DolbyDigitalChannels.SURROUND:
            return "5.1"
