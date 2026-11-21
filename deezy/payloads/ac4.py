from dataclasses import dataclass

from deezy.enums.ac4 import Ac4ChannelBasedChannels, Ac4EncodingProfile
from deezy.enums.atmos import WarpMode
from deezy.enums.shared import DeeDRC, LoudnessPreset, StereoDownmix
from deezy.payloads.shared import LoudnessPayload


@dataclass(slots=True)
class Ac4Payload(LoudnessPayload):
    thd_warp_mode: WarpMode | None
    ims_legacy_presentation: bool
    encoding_profile: Ac4EncodingProfile
    ddp_drc: DeeDRC
    flat_panel_drc: DeeDRC
    home_theatre_drc: DeeDRC
    portable_headphones_drc: DeeDRC
    portable_speakers_drc: DeeDRC
    # split DEE encoders only
    loudness_preset: LoudnessPreset = LoudnessPreset.MANUAL


@dataclass(slots=True)
class Ac4AtmosPayload(LoudnessPayload):
    """AC-4 with Dolby Atmos (the `ac4-atmos` format)."""

    # for a TrueHD Atmos source, the warp mode truehdd writes when it has none
    thd_warp_mode: WarpMode | None = None
    flat_panel_drc: DeeDRC = DeeDRC.FILM_LIGHT
    home_theatre_drc: DeeDRC = DeeDRC.FILM_LIGHT
    portable_headphones_drc: DeeDRC = DeeDRC.FILM_LIGHT
    portable_speakers_drc: DeeDRC = DeeDRC.FILM_LIGHT
    # the encoder only measures (measure_only); it has no skip mode and can't
    # correct the loudness
    loudness_preset: LoudnessPreset = LoudnessPreset.MANUAL


@dataclass(slots=True)
class Ac4ChannelPayload(LoudnessPayload):
    """Channel-based AC-4 (the `ac4` format)."""

    channels: Ac4ChannelBasedChannels
    flat_panel_drc: DeeDRC
    home_theatre_drc: DeeDRC
    portable_headphones_drc: DeeDRC
    portable_speakers_drc: DeeDRC
    preferred_downmix_mode: StereoDownmix
    loro_center_mix_level: str
    loro_surround_mix_level: str
    ltrt_center_mix_level: str
    ltrt_surround_mix_level: str
    # None only measures (measure_only); AC-4 has no skip mode
    loudness_target: int | None = None
    peak_limit: float | None = None
    loudness_preset: LoudnessPreset = LoudnessPreset.MANUAL
