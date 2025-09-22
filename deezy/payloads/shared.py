from dataclasses import dataclass, field
from pathlib import Path

from deezy.enums.shared import DeeDRC, MeteringMode, StereoDownmix
from deezy.track_info.track_index import TrackIndex


@dataclass(slots=True)
class CorePayload:
    """Core fields needed by all encoding formats."""

    no_progress_bars: bool
    ffmpeg_path: Path
    truehdd_path: Path | None
    dee_path: Path
    file_input: Path
    track_index: TrackIndex
    bitrate: int | None
    temp_dir: Path | None
    delay: str | None
    parse_elementary_delay: bool
    keep_temp: bool
    reuse_temp_files: bool
    file_output: Path | None
    batch_output_dir: Path | None
    worker_id: str | None
    overwrite: bool
    # These fields are intentionally not part of the generated __init__ (init=False)
    # to avoid dataclass field-ordering issues when subclasses declare non-default
    # fields. This keeps the payload constructors backwards-compatible on
    # Python 3.9 while still exposing `output_template`/`output_preview` as
    # attributes that can be set by the PayloadBuilder or callers.
    output_template: str = field(default="", init=False)
    output_preview: bool = field(default=False, init=False)


@dataclass(slots=True)
class LoudnessPayload(CorePayload):
    """Core + loudness/metering fields."""

    metering_mode: MeteringMode
    dialogue_intelligence: bool
    speech_threshold: int


@dataclass(slots=True)
class DolbyPayload(LoudnessPayload):
    """Core + loudness + Dolby-specific fields (DD/DDP/Atmos)."""

    drc_line_mode: DeeDRC
    drc_rf_mode: DeeDRC
    custom_dialnorm: str


@dataclass(slots=True)
class StereoMixPayload(DolbyPayload):
    """Dolby + stereo downmix fields (DD/DDP only)."""

    stereo_mix: StereoDownmix
    lfe_lowpass_filter: bool
    surround_90_degree_phase_shift: bool
    surround_3db_attenuation: bool
    loro_center_mix_level: str
    loro_surround_mix_level: str
    ltrt_center_mix_level: str
    ltrt_surround_mix_level: str
    preferred_downmix_mode: StereoDownmix


@dataclass(slots=True)
class DownmixOnlyPayload(DolbyPayload):
    """Dolby + downmix metadata only (Atmos)."""

    loro_center_mix_level: str
    loro_surround_mix_level: str
    ltrt_center_mix_level: str
    ltrt_surround_mix_level: str
    preferred_downmix_mode: StereoDownmix


@dataclass(frozen=True, slots=True)
class ChannelBitrates:
    default: int
    choices: tuple[int, ...]

    def get_closest_bitrate(self, target: int) -> int:
        """
        Find the closest allowed bitrate to the target, preferring the next higher or equal,
        else the closest lower if no higher exists.
        """
        higher_or_equal = [b for b in self.choices if b >= target]
        if higher_or_equal:
            return min(higher_or_equal)
        else:
            # all choices are lower than target, pick the highest available
            return max(self.choices)

    def is_valid_bitrate(self, bitrate: int) -> bool:
        """Check if a bitrate is in the allowed choices."""
        return bitrate in self.choices
