from dataclasses import dataclass

from deezy.enums.atmos import AtmosMode, WarpMode
from deezy.payloads.shared import BaseArgsPayload


@dataclass(slots=True)
class AtmosPayload(BaseArgsPayload):
    atmos_mode: AtmosMode
    thd_warp_mode: WarpMode
    no_bed_conform: bool
