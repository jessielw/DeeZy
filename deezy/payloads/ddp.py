from dataclasses import dataclass

from deezy.enums.ddp import DolbyDigitalPlusChannels
from deezy.enums.ddp_bluray import DolbyDigitalPlusBlurayChannels
from deezy.enums.shared import LoudnessPreset
from deezy.payloads.shared import StereoMixPayload


@dataclass(slots=True)
class DDPPayload(StereoMixPayload):
    channels: DolbyDigitalPlusChannels | DolbyDigitalPlusBlurayChannels
    # split DEE encoders only
    loudness_target: int | None = None
    peak_limit: float | None = None
    loudness_preset: LoudnessPreset = LoudnessPreset.MANUAL
    # optional user data ID (-1 = none)
    user_data: int = -1
    # Blu-ray secondary audio mode (2.0/5.1 at 192/256 kbps)
    bluray_secondary: bool = False
