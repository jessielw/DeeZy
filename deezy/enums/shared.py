from dataclasses import dataclass
from enum import Enum


class ProgressMode(Enum):
    STANDARD = 0
    DEBUG = 1
    SILENT = 2


class StereoDownmix(Enum):
    STANDARD = 0
    DPLII = 1


class DeeDelayModes(Enum):
    NEGATIVE = "start"
    POSITIVE = "prepend_silence_duration"


@dataclass(slots=True)
class DeeDelay:
    MODE: DeeDelayModes
    DELAY: str


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

    def __str__(self):
        if self == DeeFPS.FPS_NOT_INDICATED:
            return "not_indicated"
        elif self == DeeFPS.FPS_23_976:
            return "23.976"
        elif self == DeeFPS.FPS_24:
            return "24"
        elif self == DeeFPS.FPS_25:
            return "25"
        elif self == DeeFPS.FPS_29_97:
            return "29.97"
        elif self == DeeFPS.FPS_30:
            return "30"
        elif self == DeeFPS.FPS_48:
            return "48"
        elif self == DeeFPS.FPS_50:
            return "50"
        elif self == DeeFPS.FPS_59_94:
            return "59.94"
        elif self == DeeFPS.FPS_60:
            return "60"
        raise ValueError("Failed to determine FPS")


class DeeDRC(Enum):
    FILM_STANDARD = 0
    FILM_LIGHT = 1
    MUSIC_STANDARD = 2
    MUSIC_LIGHT = 3
    SPEECH = 4

    def __str__(self):
        if self == DeeDRC.FILM_STANDARD:
            return "film_standard"
        elif self == DeeDRC.FILM_LIGHT:
            return "film_light"
        elif self == DeeDRC.MUSIC_STANDARD:
            return "music_standard"
        elif self == DeeDRC.MUSIC_LIGHT:
            return "music_light"
        elif self == DeeDRC.SPEECH:
            return "speech"
        raise ValueError("Failed to determine DRC")
