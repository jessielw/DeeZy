from dataclasses import dataclass
from pathlib import Path

from deezy.enums.shared import ProgressMode, StereoDownmix


@dataclass(slots=True)
class BaseArgsPayload:
    ffmpeg_path: Path
    truehdd_path: Path
    dee_path: Path
    file_input: Path | None = None
    track_index: int | None = None
    bitrate: int | None = None
    delay: str | None = None
    temp_dir: Path | None = None
    keep_temp: bool = False
    file_output: Path | None = None
    progress_mode: ProgressMode = ProgressMode.STANDARD
    stereo_mix: StereoDownmix = StereoDownmix.STANDARD
