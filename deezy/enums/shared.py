import logging
from dataclasses import dataclass
from enum import Enum

from typing_extensions import override

from deezy.enums import CaseInsensitiveEnum


class LogLevel(CaseInsensitiveEnum):
    CRITICAL = "critical"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    DEBUG = "debug"

    def to_logging_level(self) -> int:
        """Must be called before being sent to init_logger method."""
        return getattr(logging, self.name)


class StereoDownmix(CaseInsensitiveEnum):
    NOT_INDICATED = "auto"
    LORO = "loro"
    LTRT = "ltrt"
    DPLII = "dpl2"

    def to_dee_cmd(self) -> str:
        if self is StereoDownmix.NOT_INDICATED:
            return "not_indicated"
        elif self is StereoDownmix.DPLII:
            return "ltrt-pl2"
        else:
            return self.value


class DeeDelayModes(CaseInsensitiveEnum):
    NEGATIVE = "start"
    POSITIVE = "prepend_silence_duration"


@dataclass(slots=True)
class DeeDelay:
    MODE: DeeDelayModes
    DELAY: str  # DEE specific delay i.e. '0:00:00.005333'

    def is_delay(self) -> bool:
        """
        If delay is anything other than the default Dolby compensation value return True.
        This indicates that we're setting the delay to 0 for the container.
        """
        return self.DELAY != "0:00:00.005333"


class DeeFPS(Enum):
    FPS_NOT_INDICATED = 0
    FPS_23_976 = 23.976
    FPS_24 = 24
    FPS_25 = 25
    FPS_29_97 = 29.97
    FPS_30 = 30
    FPS_48 = 48
    FPS_50 = 50
    FPS_59_94 = 59.94
    FPS_60 = 60

    def to_dee_cmd(self) -> str:
        if self is DeeFPS.FPS_NOT_INDICATED:
            return "not_indicated"
        elif self is DeeFPS.FPS_23_976:
            return "23.976"
        elif self is DeeFPS.FPS_24:
            return "24"
        elif self is DeeFPS.FPS_25:
            return "25"
        elif self is DeeFPS.FPS_29_97:
            return "29.97"
        elif self is DeeFPS.FPS_30:
            return "30"
        elif self is DeeFPS.FPS_48:
            return "48"
        elif self is DeeFPS.FPS_50:
            return "50"
        elif self is DeeFPS.FPS_59_94:
            return "59.94"
        elif self is DeeFPS.FPS_60:
            return "60"
        return "not_indicated"


class DeeDRC(CaseInsensitiveEnum):
    FILM_STANDARD = "film_standard"
    FILM_LIGHT = "film_light"
    MUSIC_STANDARD = "music_standard"
    MUSIC_LIGHT = "music_light"
    SPEECH = "speech"
    NONE = "none"  # ac4 is the only codec that supports this

    @override
    def __str__(self):
        return self.value

    def to_dee_cmd(self) -> str:
        return str(self)


class MeteringMode(CaseInsensitiveEnum):
    MODE_1770_1 = "1770_1"
    MODE_1770_2 = "1770_2"
    MODE_1770_3 = "1770_3"
    MODE_1770_4 = "1770_4"
    MODE_LEQA = "leqa"

    @override
    def __str__(self) -> str:
        return self.value.replace("_", "-")

    def to_dee_cmd(self) -> str:
        if self is MeteringMode.MODE_1770_1:
            return "1770-1"
        elif self is MeteringMode.MODE_1770_2:
            return "1770-2"
        elif self is MeteringMode.MODE_1770_3:
            return "1770-3"
        elif self is MeteringMode.MODE_1770_4:
            return "1770-4"
        else:
            return "LeqA"


class DDEncodingMode(CaseInsensitiveEnum):
    DD = "dd"
    DDP = "ddp"
    DDP71 = "ddp71"
    BLURAY = "bluray"

    def get_encoder_mode(self) -> str:
        return self.value

    def get_output_mode(self) -> str:
        if self is DDEncodingMode.DD:
            return "ac3"
        else:
            return "ec3"


class TrackType(CaseInsensitiveEnum):
    AUDIO = "a"
    STREAM = "s"

    @override
    def __str__(self) -> str:
        return self.value
