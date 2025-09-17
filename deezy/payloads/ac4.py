from dataclasses import dataclass

from deezy.enums.ac4 import Ac4EncodingProfile
from deezy.enums.atmos import WarpMode
from deezy.enums.shared import DeeDRC
from deezy.payloads.shared import LoudnessPayload


@dataclass(slots=True)
class Ac4Payload(LoudnessPayload):
    thd_warp_mode: WarpMode
    bed_conform: bool
    ims_legacy_presentation: bool
    encoding_profile: Ac4EncodingProfile
    ddp_drc: DeeDRC
    flat_panel_drc: DeeDRC
    home_theatre_drc: DeeDRC
    portable_headphones_drc: DeeDRC
    portable_speakers_drc: DeeDRC
