from dataclasses import dataclass

from deezy.enums.dd import DolbyDigitalChannels
from deezy.enums.shared import LoudnessPreset
from deezy.payloads.shared import StereoMixPayload


@dataclass(slots=True)
class DDPayload(StereoMixPayload):
    channels: DolbyDigitalChannels
    # split DEE encoders only: loudness correction target (None = measure only)
    loudness_target: int | None = None
    peak_limit: float | None = None
    loudness_preset: LoudnessPreset = LoudnessPreset.MANUAL
