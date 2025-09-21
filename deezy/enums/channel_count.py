from deezy.enums import CaseInsensitiveEnum


class ChannelCount(CaseInsensitiveEnum):
    CH_1 = 1
    CH_2 = 2
    CH_3 = 3
    CH_4 = 4
    CH_5 = 5
    CH_6 = 6
    CH_7 = 7
    CH_8 = 8

    def to_config(self) -> str:
        return self.name.lower()
