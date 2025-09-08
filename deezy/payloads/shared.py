from dataclasses import dataclass
from pathlib import Path

from deezy.enums.shared import DeeDRC, MeteringMode, StereoDownmix


@dataclass(slots=True)
class BaseArgsPayload:
    no_progress_bars: bool
    ffmpeg_path: Path
    truehdd_path: Path | None
    dee_path: Path
    file_input: Path
    track_index: int
    bitrate: int | None
    temp_dir: Path | None
    delay: str | None
    keep_temp: bool
    file_output: Path | None
    stereo_mix: StereoDownmix
    metering_mode: MeteringMode
    drc_line_mode: DeeDRC
    drc_rf_mode: DeeDRC
    dialogue_intelligence: bool
    speech_threshold: int
    custom_dialnorm: str  # str[int] (-1 - -31) but "0" disables it


@dataclass(frozen=True, slots=True)
class ChannelBitrates:
    default: int
    choices: tuple[int, ...]

    def get_closest_bitrate(self, target: int) -> int:
        """
        Find the closest allowed bitrate to the target and select the highest if
        there are two matches.
        """
        return min(self.choices, key=lambda x: (abs(x - target), -x))

    def is_valid_bitrate(self, bitrate: int) -> bool:
        """Check if a bitrate is in the allowed choices."""
        return bitrate in self.choices
