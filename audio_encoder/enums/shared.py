from enum import Enum


class ProgressMode(Enum):
    STANDARD = 0
    DEBUG = 1


class StereoDownmix(Enum):
    STANDARD = 0
    DPLII = 1
