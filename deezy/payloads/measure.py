from dataclasses import dataclass
from pathlib import Path

from deezy.enums.atmos import WarpMode
from deezy.enums.shared import LoudnessPreset
from deezy.payloads.shared import LoudnessPayload


@dataclass(slots=True)
class MeasurePayload(LoudnessPayload):
    """A loudness measurement. ``file_output`` is where the manifest is saved."""

    loudness_preset: LoudnessPreset = LoudnessPreset.MANUAL
    # the warp mode truehdd gives a TrueHD Atmos stream that has none
    thd_warp_mode: WarpMode | None = None
    # saves each input's manifest here, under the input's name
    output_dir: Path | None = None
