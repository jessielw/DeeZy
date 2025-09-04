from dataclasses import dataclass
from pathlib import Path

from deezy.enums.shared import ProgressMode, StereoDownmix


@dataclass(slots=True)
class BaseArgsPayload:
    ffmpeg_path: Path
    truehdd_path: Path
    dee_path: Path
    file_input: Path
    track_index: int
    bitrate: int
    temp_dir: Path | None = None
    delay: str | None = None
    keep_temp: bool = False
    file_output: Path | None = None
    progress_mode: ProgressMode = ProgressMode.STANDARD
    stereo_mix: StereoDownmix = StereoDownmix.STANDARD
