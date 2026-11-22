"""
Golden command lines: what each format and mode plans, compared argument by
argument with tests/golden/commands.json.

The planner is pure, so nothing is probed or run. Paths are placeholders,
written with forward slashes and without the executable suffix, so the file
holds on every platform. After an intended change, regenerate the file with
DEEZY_UPDATE_GOLDEN=1 and review its diff.
"""

from collections.abc import Iterator
import json
import logging
import os
from pathlib import Path
from typing import cast

from pymediainfo import Track
import pytest
import tomlkit

from deezy.audio_processors import ffmpeg
from deezy.audio_processors.truehdd import truehd_extract_command, truehdd_command
import deezy.cli as cli
from deezy.cli.payload_factory import PayloadBuilder
from deezy.cli.utils import apply_config_defaults_to_args, apply_default_bitrate
from deezy.config.defaults import CONF_DEFAULT
from deezy.config.manager import ConfigManager
from deezy.dee.shim import DeeShim
from deezy.dee.tools import get_executable_extension
from deezy.pipeline.plan import (
    DeeStep,
    FfmpegStep,
    PipeStep,
    PlanContext,
    plan_job,
    plan_measure,
)
from deezy.track_info.audio_track_info import AudioTrackInfo
from deezy.utils.logger import logger

GOLDEN = Path(__file__).parent / "golden" / "commands.json"

FFMPEG = Path("/tools/ffmpeg")
TRUEHDD = Path("/tools/truehdd")
SHIM = Path("/tools/dee_shim")
DEE = Path("/tools/dee")
TEMP = Path("/temp/job")
OUT = Path("/out")
MKV = Path("/media/in.mkv")
WAV = Path("/media/in.wav")
# a DAMF master: the header, which names its audio and metadata
DAMF = Path("/media/in.atmos")
DELAYED = Path("/media/Movie DELAY -10.5ms.mkv")


def info(ch, rate=48000, fps=23.976, thd=False, adm=False, damf=False, rel=0) -> dict:
    return {
        "channels": ch,
        "delay_relative_to_video": rel,
        "fps": fps,
        "recommended_free_space": 1,
        "duration": 60000.0,
        "sample_rate": rate,
        "bit_depth": 24,
        "thd_atmos": thd,
        "adm_atmos_wav": adm,
        "damf_atmos": damf,
    }


# (id, arguments after 'encode', probed track, input)
SCENARIOS = [
    # --- dd
    ("dd_auto_6", ["dd"], info(6), MKV),
    ("dd_auto_8", ["dd"], info(8), MKV),
    ("dd_auto_2", ["dd"], info(2), MKV),
    ("dd_auto_1", ["dd"], info(1), MKV),
    ("dd_auto_3", ["dd"], info(3), MKV),
    ("dd_auto_5", ["dd"], info(5), MKV),
    ("dd_upmix50", ["dd", "--channels", "6", "--upmix-50-to-51"], info(5), MKV),
    ("dd_upmix50_auto", ["dd", "--upmix-50-to-51"], info(5), MKV),
    ("dd_stereo_from6", ["dd", "--channels", "2"], info(6), MKV),
    ("dd_stereo_from8", ["dd", "--channels", "2"], info(8), MKV),
    ("dd_dpl2", ["dd", "--channels", "2", "--stereo-down-mix", "dpl2"], info(6), MKV),
    ("dd_dpl2_auto2", ["dd", "--stereo-down-mix", "dpl2"], info(2), MKV),
    ("dd_dpl2_auto6", ["dd", "--stereo-down-mix", "dpl2"], info(6), MKV),
    (
        "dd_dpl2_51",
        ["dd", "--channels", "6", "--stereo-down-mix", "dpl2"],
        info(6),
        MKV,
    ),
    (
        "dd_dpl2_mono",
        ["dd", "--channels", "1", "--stereo-down-mix", "dpl2"],
        info(6),
        MKV,
    ),
    ("dd_ltrt", ["dd", "--channels", "2", "--stereo-down-mix", "ltrt"], info(6), MKV),
    ("dd_mono_from2", ["dd", "--channels", "1"], info(2), MKV),
    ("dd_441", ["dd"], info(6, rate=44100), MKV),
    ("dd_norate", ["dd"], info(6, rate=None), MKV),
    ("dd_delay_pos", ["dd", "--delay=100ms"], info(6), MKV),
    ("dd_delay_neg", ["dd", "--delay=-1.5s"], info(6), MKV),
    ("dd_delay_frames", ["dd", "--delay=-1@23.976"], info(6), MKV),
    ("dd_filename_delay", ["dd"], info(6), DELAYED),
    ("dd_dialnorm", ["dd", "--custom-dialnorm", "-27"], info(6), MKV),
    (
        "dd_target",
        ["dd", "--loudness-target", "-24", "--peak-limit", "-2"],
        info(6),
        MKV,
    ),
    (
        "dd_target_dialnorm",
        ["dd", "--loudness-target", "-24", "--custom-dialnorm", "-27"],
        info(6),
        MKV,
    ),
    ("dd_peak_only", ["dd", "--peak-limit", "-2"], info(6), MKV),
    ("dd_preset", ["dd", "--loudness-preset", "ebu_r128"], info(6), MKV),
    (
        "dd_drc",
        ["dd", "--drc-line-mode", "none", "--drc-rf-mode", "music_light"],
        info(6),
        MKV,
    ),
    (
        "dd_flags",
        [
            "dd",
            "--no-surround-3db",
            "--no-surround-90-deg-phase-shift",
            "--no-low-pass-filter",
            "--no-dialogue-intelligence",
            "--speech-threshold",
            "30",
        ],
        info(6),
        MKV,
    ),
    (
        "dd_mix",
        [
            "dd",
            "--lo-ro-center",
            "-6",
            "--lo-ro-surround",
            "-4.5",
            "--lt-rt-center",
            "0",
            "--lt-rt-surround=-inf",
        ],
        info(6),
        MKV,
    ),
    ("dd_metering", ["dd", "--metering-mode", "1770_1"], info(6), MKV),
    ("dd_bitrate_invalid", ["dd", "--bitrate", "500"], info(6), MKV),
    ("dd_bitrate_ok", ["dd", "--bitrate", "640"], info(6), MKV),
    ("dd_upmix_refused", ["dd", "--channels", "6"], info(2), MKV),
    ("dd_fps_none", ["dd"], info(6, fps=None), MKV),
    ("dd_fps_25", ["dd"], info(6, fps=25.0), MKV),
    ("dd_fps_odd", ["dd"], info(6, fps=12.0), MKV),
    ("dd_rel_delay", ["dd"], info(6, rel=-40), MKV),
    ("dd_output", ["dd", "--output", str(OUT / "x.ac3")], info(6), MKV),
    ("dd_output_bad", ["dd", "--output", str(OUT / "x.ec3")], info(6), MKV),
    ("dd_template", ["dd", "--output-template", "{title} {channels}"], info(6), MKV),
    (
        "dd_preview",
        ["dd", "--output-template", "{title}", "--output-preview"],
        info(6),
        MKV,
    ),
    ("dd_batch_dir", ["dd", "--batch-output-dir", str(OUT / "batch")], info(6), MKV),
    ("dd_track", ["dd", "--track-index", "2"], info(6), MKV),
    ("dd_stream_track", ["dd", "--track-index", "s:3"], info(6), MKV),
    # --- ddp
    ("ddp_auto_6", ["ddp"], info(6), MKV),
    ("ddp_auto_2", ["ddp"], info(2), MKV),
    ("ddp_auto_1", ["ddp"], info(1), MKV),
    ("ddp_auto_5", ["ddp"], info(5), MKV),
    ("ddp_auto_8", ["ddp"], info(8), MKV),
    ("ddp_8", ["ddp", "--channels", "8"], info(8), MKV),
    ("ddp_6_from8", ["ddp", "--channels", "6"], info(8), MKV),
    ("ddp_2_from6", ["ddp", "--channels", "2"], info(6), MKV),
    ("ddp_2_from8", ["ddp", "--channels", "2"], info(8), MKV),
    ("ddp_1_from6", ["ddp", "--channels", "1"], info(6), MKV),
    ("ddp_upmix50", ["ddp", "--channels", "6", "--upmix-50-to-51"], info(5), MKV),
    (
        "ddp_upmix50_441",
        ["ddp", "--channels", "6", "--upmix-50-to-51"],
        info(5, rate=44100),
        MKV,
    ),
    ("ddp_dpl2", ["ddp", "--channels", "2", "--stereo-down-mix", "dpl2"], info(6), MKV),
    ("ddp_user_data", ["ddp", "--user-data", "5"], info(6), MKV),
    ("ddp_target", ["ddp", "--loudness-target", "-20"], info(6), MKV),
    ("ddp_dialnorm", ["ddp", "--custom-dialnorm", "-31"], info(6), MKV),
    (
        "ddp_secondary_2",
        ["ddp", "--bluray-secondary", "--channels", "2", "--bitrate", "256"],
        info(2),
        MKV,
    ),
    ("ddp_secondary_6", ["ddp", "--bluray-secondary", "--channels", "6"], info(6), MKV),
    (
        "ddp_secondary_6_200",
        ["ddp", "--bluray-secondary", "--channels", "6", "--bitrate", "200"],
        info(6),
        MKV,
    ),
    ("ddp_secondary_auto", ["ddp", "--bluray-secondary"], info(6), MKV),
    (
        "ddp_secondary_2_default",
        ["ddp", "--bluray-secondary", "--channels", "2"],
        info(2),
        MKV,
    ),
    (
        "ddp_secondary_2_96",
        ["ddp", "--bluray-secondary", "--channels", "2", "--bitrate", "96"],
        info(2),
        MKV,
    ),
    (
        "ddp_secondary_6_128",
        ["ddp", "--bluray-secondary", "--channels", "6", "--bitrate", "128"],
        info(6),
        MKV,
    ),
    ("ddp_secondary_auto_8", ["ddp", "--bluray-secondary"], info(8), MKV),
    ("ddp_secondary_1", ["ddp", "--bluray-secondary", "--channels", "1"], info(1), MKV),
    (
        "ddp_secondary_user_data",
        ["ddp", "--bluray-secondary", "--channels", "2", "--user-data", "3"],
        info(2),
        MKV,
    ),
    ("ddp_bitrate_invalid", ["ddp", "--bitrate", "190"], info(6), MKV),
    ("ddp_delay", ["ddp", "--delay=1@24"], info(6), MKV),
    ("ddp_441", ["ddp"], info(2, rate=44100), MKV),
    ("ddp_output_eac3", ["ddp", "--output", str(OUT / "x.eac3")], info(6), MKV),
    ("ddp_output_bad", ["ddp", "--output", str(OUT / "x.ac3")], info(6), MKV),
    # --- ddp-bluray
    ("bluray_8", ["ddp-bluray"], info(8), MKV),
    ("bluray_8_441", ["ddp-bluray"], info(8, rate=44100), MKV),
    ("bluray_8_1664", ["ddp-bluray", "--bitrate", "1664"], info(8), MKV),
    ("bluray_8_bad_rate", ["ddp-bluray", "--bitrate", "1100"], info(8), MKV),
    ("bluray_6", ["ddp-bluray"], info(6), MKV),
    ("bluray_delay", ["ddp-bluray", "--delay=-20ms"], info(8), MKV),
    ("bluray_dialnorm", ["ddp-bluray", "--custom-dialnorm", "-20"], info(8), MKV),
    # --- ddp-atmos
    ("atmos_thd", ["ddp-atmos"], info(8, thd=True), MKV),
    (
        "atmos_thd_warp",
        ["ddp-atmos", "--thd-warp-mode", "prologiciix"],
        info(8, thd=True),
        MKV,
    ),
    ("atmos_thd_1024", ["ddp-atmos", "--bitrate", "1024"], info(8, thd=True), MKV),
    ("atmos_thd_512", ["ddp-atmos", "--bitrate", "512"], info(8, thd=True), MKV),
    ("atmos_adm", ["ddp-atmos"], info(8, adm=True), WAV),
    ("atmos_bluray", ["ddp-atmos", "--atmos-mode", "bluray"], info(8, thd=True), MKV),
    ("atmos_plain", ["ddp-atmos"], info(6), MKV),
    ("atmos_upmix", ["ddp-atmos"], info(2, thd=True), MKV),
    (
        "atmos_dialnorm",
        ["ddp-atmos", "--custom-dialnorm", "-20", "--delay=50ms"],
        info(8, thd=True),
        MKV,
    ),
    (
        "atmos_drc",
        ["ddp-atmos", "--drc-line-mode", "none", "--stereo-down-mix", "ltrt"],
        info(8, thd=True),
        MKV,
    ),
    (
        "atmos_preset",
        ["ddp-atmos", "--loudness-preset", "atsc_a85"],
        info(8, thd=True),
        MKV,
    ),
    # --- ac4-ims
    ("ac4_thd", ["ac4-ims"], info(8, thd=True), MKV),
    ("ac4_thd_warp", ["ac4-ims", "--thd-warp-mode", "loro"], info(8, thd=True), MKV),
    ("ac4_adm", ["ac4-ims"], info(8, adm=True), WAV),
    ("ac4_6", ["ac4-ims"], info(6), MKV),
    ("ac4_8", ["ac4-ims"], info(8), MKV),
    ("ac4_7", ["ac4-ims"], info(7), MKV),
    ("ac4_2", ["ac4-ims"], info(2), MKV),
    ("ac4_music", ["ac4-ims", "--encoding-profile", "ims_music"], info(6), MKV),
    (
        "ac4_drc",
        ["ac4-ims", "--ddp-drc", "none", "--flat-panel-drc", "speech"],
        info(6),
        MKV,
    ),
    ("ac4_441", ["ac4-ims"], info(6, rate=44100), MKV),
    ("ac4_8_441", ["ac4-ims"], info(8, rate=44100), MKV),
    ("ac4_bitrate", ["ac4-ims", "--bitrate", "100"], info(6), MKV),
    ("ac4_delay", ["ac4-ims", "--delay=-5ms"], info(6), MKV),
    ("ac4_output_bad", ["ac4-ims", "--output", str(OUT / "x.ec3")], info(6), MKV),
    # --- ac4 (channel-based; ids ac4ch_, since ac4_ is ac4-ims's)
    ("ac4ch_auto_6", ["ac4"], info(6), MKV),
    ("ac4ch_auto_8", ["ac4"], info(8), MKV),
    ("ac4ch_auto_2", ["ac4"], info(2), MKV),
    ("ac4ch_auto_1", ["ac4"], info(1), MKV),
    ("ac4ch_auto_3", ["ac4"], info(3), MKV),
    ("ac4ch_auto_7", ["ac4"], info(7), MKV),
    ("ac4ch_stereo_from6", ["ac4", "--channels", "2"], info(6), MKV),
    ("ac4ch_stereo_from8", ["ac4", "--channels", "2"], info(8), MKV),
    ("ac4ch_stereo_from1", ["ac4", "--channels", "2"], info(1), MKV),
    ("ac4ch_51_from2", ["ac4", "--channels", "6"], info(2), MKV),
    ("ac4ch_51_from1", ["ac4", "--channels", "6"], info(1), MKV),
    ("ac4ch_441", ["ac4"], info(6, rate=44100), MKV),
    ("ac4ch_bitrate", ["ac4", "--bitrate", "100"], info(6), MKV),
    ("ac4ch_bitrate_48", ["ac4", "--bitrate", "48"], info(2), MKV),
    ("ac4ch_delay_pos", ["ac4", "--delay=100ms"], info(6), MKV),
    ("ac4ch_delay_neg", ["ac4", "--delay=-20ms"], info(2), MKV),
    ("ac4ch_target", ["ac4", "--loudness-target", "-20"], info(6), MKV),
    ("ac4ch_target_m9", ["ac4", "--loudness-target", "-9"], info(6), MKV),
    ("ac4ch_peak_only", ["ac4", "--peak-limit", "-1"], info(6), MKV),
    ("ac4ch_preset", ["ac4", "--loudness-preset", "ebu_r128"], info(6), MKV),
    (
        "ac4ch_drc",
        ["ac4", "--flat-panel-drc", "speech", "--portable-speakers-drc", "music_light"],
        info(6),
        MKV,
    ),
    ("ac4ch_drc_none", ["ac4", "--home-theatre-drc", "none"], info(6), MKV),
    ("ac4ch_cmix_inf", ["ac4", "--lo-ro-center=-inf"], info(6), MKV),
    ("ac4ch_smix_inf", ["ac4", "--lt-rt-surround=-inf"], info(6), MKV),
    ("ac4ch_dpl2", ["ac4", "--stereo-down-mix", "dpl2"], info(6), MKV),
    ("ac4ch_dmx_auto", ["ac4", "--stereo-down-mix", "auto"], info(6), MKV),
    ("ac4ch_output_bad", ["ac4", "--output", str(OUT / "x.ec3")], info(6), MKV),
    # --- aac (always 2.0 out; delay per rate, +32 unless DEE gets 2.0)
    ("aac_2", ["aac"], info(2), MKV),
    ("aac_1", ["aac"], info(1), MKV),
    ("aac_6", ["aac"], info(6), MKV),
    ("aac_8", ["aac"], info(8), MKV),
    ("aac_3", ["aac"], info(3), MKV),
    ("aac_7", ["aac"], info(7), MKV),
    ("aac_441", ["aac"], info(6, rate=44100), MKV),
    ("aac_heaac", ["aac", "--aac-profile", "heaac"], info(2), MKV),
    ("aac_heaacv2", ["aac", "--aac-profile", "heaacv2"], info(6), MKV),
    ("aac_lc_64", ["aac", "--bitrate", "64"], info(2), MKV),
    ("aac_lc_80", ["aac", "--bitrate", "80"], info(2), MKV),
    ("aac_lc_low", ["aac", "--bitrate", "20"], info(2), MKV),
    (
        "aac_heaac_100",
        ["aac", "--aac-profile", "heaac", "--bitrate", "100"],
        info(2),
        MKV,
    ),
    (
        "aac_heaacv2_high",
        ["aac", "--aac-profile", "heaacv2", "--bitrate", "96"],
        info(2),
        MKV,
    ),
    ("aac_delay_pos", ["aac", "--delay=100ms"], info(6), MKV),
    ("aac_delay_neg", ["aac", "--delay=-50ms"], info(2), MKV),
    ("aac_filename_delay", ["aac"], info(2), DELAYED),
    (
        "aac_target",
        ["aac", "--loudness-target", "-23", "--peak-limit", "-1"],
        info(6),
        MKV,
    ),
    ("aac_preset", ["aac", "--loudness-preset", "ebu_r128"], info(6), MKV),
    (
        "aac_target_preset",
        ["aac", "--loudness-target", "-23", "--loudness-preset", "ebu_r128"],
        info(6),
        MKV,
    ),
    ("aac_peak_only", ["aac", "--peak-limit", "-1"], info(6), MKV),
    ("aac_output_bad", ["aac", "--output", str(OUT / "x.m4a")], info(2), MKV),
    ("aac_output", ["aac", "--output", str(OUT / "x.aac")], info(2), MKV),
    # --- --pipe where DeeZy doesn't pipe (anything but Windows)
    ("nopipe_auto", ["ddp", "--pipe", "auto"], info(6), MKV),
    ("nopipe_always", ["ddp", "--pipe", "always"], info(6), MKV),
]

# --- thd (channel-based TrueHD: lossless, WAV only, 48 or 96 kHz)
THD_SCENARIOS = [
    ("thd_auto_2", ["thd"], info(2), MKV),
    ("thd_auto_6", ["thd"], info(6), MKV),
    ("thd_auto_8", ["thd"], info(8), MKV),
    ("thd_auto_1", ["thd"], info(1), MKV),
    ("thd_auto_3", ["thd"], info(3), MKV),
    ("thd_auto_5", ["thd"], info(5), MKV),
    ("thd_auto_7", ["thd"], info(7), MKV),
    ("thd_auto_10", ["thd"], info(10), MKV),
    ("thd_51_from8", ["thd", "--channels", "6"], info(8), MKV),
    ("thd_20_from6", ["thd", "--channels", "2"], info(6), MKV),
    ("thd_20_from8", ["thd", "--channels", "2"], info(8), MKV),
    ("thd_51_from5", ["thd", "--channels", "6"], info(5), MKV),
    ("thd_20_from1", ["thd", "--channels", "2"], info(1), MKV),
    ("thd_51_from2", ["thd", "--channels", "6"], info(2), MKV),
    ("thd_71_from6", ["thd", "--channels", "8"], info(6), MKV),
    ("thd_96k", ["thd"], info(8, rate=96000), MKV),
    ("thd_441", ["thd"], info(2, rate=44100), MKV),
    ("thd_882", ["thd"], info(6, rate=88200), MKV),
    ("thd_192k", ["thd"], info(2, rate=192000), MKV),
    ("thd_drc_8", ["thd", "--drc", "speech"], info(8), MKV),
    ("thd_drc_6", ["thd", "--drc", "music_light"], info(6), MKV),
    ("thd_drc_2", ["thd", "--drc", "film_standard"], info(2), MKV),
    ("thd_dialnorm", ["thd", "--custom-dialnorm", "-27"], info(6), MKV),
    ("thd_preset", ["thd", "--loudness-preset", "ebu_r128"], info(6), MKV),
    ("thd_manual", ["thd", "--no-dialogue-intelligence"], info(6), MKV),
    ("thd_delay_pos", ["thd", "--delay=100ms"], info(6), MKV),
    ("thd_delay_neg", ["thd", "--delay=-20ms"], info(8), MKV),
    ("thd_delay_96k", ["thd", "--delay=-20ms"], info(2, rate=96000), MKV),
    ("thd_fps", ["thd"], info(6, fps=25), MKV),
    ("thd_output_mlp", ["thd", "--output", str(OUT / "x.mlp")], info(6), MKV),
    ("thd_output_bad", ["thd", "--output", str(OUT / "x.ac3")], info(6), MKV),
    ("thd_reuse", ["thd", "--reuse-temp-files"], info(6), MKV),
    ("thd_from_atmos", ["thd"], info(8, thd=True), MKV),
]
SCENARIOS += THD_SCENARIOS

# --- thd-atmos (TrueHD Atmos: 16 elements, legacy authoring off by default)
THD_ATMOS_SCENARIOS = [
    ("thd_atmos_thd", ["thd-atmos"], info(8, thd=True), MKV),
    (
        "thd_atmos_thd_warp",
        ["thd-atmos", "--thd-warp-mode", "prologiciix"],
        info(8, thd=True),
        MKV,
    ),
    ("thd_atmos_legacy", ["thd-atmos", "--legacy-authoring"], info(8, thd=True), MKV),
    (
        "thd_atmos_legacy_warp",
        ["thd-atmos", "--legacy-authoring", "--thd-warp-mode", "normal"],
        info(8, thd=True),
        MKV,
    ),
    ("thd_atmos_damf", ["thd-atmos"], info(16, fps=None, damf=True), DAMF),
    (
        "thd_atmos_damf_warp",
        ["thd-atmos", "--thd-warp-mode", "normal"],
        info(16, damf=True),
        DAMF,
    ),
    ("thd_atmos_damf_few", ["thd-atmos"], info(4, damf=True), DAMF),
    ("thd_atmos_adm", ["thd-atmos"], info(16, adm=True), WAV),
    ("thd_atmos_drc", ["thd-atmos", "--drc", "music_light"], info(8, thd=True), MKV),
    (
        "thd_atmos_dialnorm",
        ["thd-atmos", "--custom-dialnorm", "-27"],
        info(16, damf=True),
        DAMF,
    ),
    (
        "thd_atmos_preset",
        ["thd-atmos", "--loudness-preset", "ebu_r128"],
        info(8, thd=True),
        MKV,
    ),
    (
        "thd_atmos_manual",
        ["thd-atmos", "--no-dialogue-intelligence", "--speech-threshold", "30"],
        info(16, damf=True),
        DAMF,
    ),
    ("thd_atmos_delay_pos", ["thd-atmos", "--delay=100ms"], info(16, damf=True), DAMF),
    ("thd_atmos_delay_neg", ["thd-atmos", "--delay=-20ms"], info(8, thd=True), MKV),
    ("thd_atmos_filename_delay", ["thd-atmos"], info(8, thd=True), DELAYED),
    ("thd_atmos_fps", ["thd-atmos"], info(8, fps=25, thd=True), MKV),
    (
        "thd_atmos_output_mlp",
        ["thd-atmos", "--output", str(OUT / "x.mlp")],
        info(16, damf=True),
        DAMF,
    ),
    (
        "thd_atmos_output_bad",
        ["thd-atmos", "--output", str(OUT / "x.ec3")],
        info(16, damf=True),
        DAMF,
    ),
    ("thd_atmos_reuse", ["thd-atmos", "--reuse-temp-files"], info(8, thd=True), MKV),
    ("thd_atmos_channel_based", ["thd-atmos"], info(8), MKV),
    ("thd_atmos_wav", ["thd-atmos"], info(6), WAV),
]
SCENARIOS += THD_ATMOS_SCENARIOS

# --- ac4-atmos (dee_ac4ajoc_encoder --level 3; measure_only; manifest offset)
AC4_ATMOS_SCENARIOS = [
    ("ac4_atmos_thd", ["ac4-atmos"], info(8, thd=True), MKV),
    (
        "ac4_atmos_thd_warp",
        ["ac4-atmos", "--thd-warp-mode", "prologiciix"],
        info(8, thd=True),
        MKV,
    ),
    ("ac4_atmos_damf", ["ac4-atmos"], info(16, fps=None, damf=True), DAMF),
    (
        "ac4_atmos_damf_warp",
        ["ac4-atmos", "--thd-warp-mode", "normal"],
        info(16, damf=True),
        DAMF,
    ),
    ("ac4_atmos_damf_few", ["ac4-atmos"], info(4, damf=True), DAMF),
    ("ac4_atmos_adm", ["ac4-atmos"], info(16, adm=True), WAV),
    ("ac4_atmos_768", ["ac4-atmos", "--bitrate", "768"], info(8, thd=True), MKV),
    # not a level 3 rate: the next one up
    ("ac4_atmos_bitrate", ["ac4-atmos", "--bitrate", "400"], info(8, thd=True), MKV),
    (
        "ac4_atmos_drc",
        [
            "ac4-atmos",
            *("--flat-panel-drc", "speech", "--home-theatre-drc", "none"),
            *("--portable-headphones-drc", "music_light"),
            *("--portable-speakers-drc", "film_standard"),
        ],
        info(16, damf=True),
        DAMF,
    ),
    (
        "ac4_atmos_preset",
        ["ac4-atmos", "--loudness-preset", "ebu_r128"],
        info(8, thd=True),
        MKV,
    ),
    (
        "ac4_atmos_manual",
        ["ac4-atmos", "--no-dialogue-intelligence", "--speech-threshold", "30"],
        info(16, damf=True),
        DAMF,
    ),
    ("ac4_atmos_delay_pos", ["ac4-atmos", "--delay=100ms"], info(16, damf=True), DAMF),
    ("ac4_atmos_delay_neg", ["ac4-atmos", "--delay=-20ms"], info(8, thd=True), MKV),
    ("ac4_atmos_filename_delay", ["ac4-atmos"], info(8, thd=True), DELAYED),
    ("ac4_atmos_fps", ["ac4-atmos"], info(8, fps=25, thd=True), MKV),
    (
        "ac4_atmos_output",
        ["ac4-atmos", "--output", str(OUT / "x.ac4")],
        info(16, damf=True),
        DAMF,
    ),
    (
        "ac4_atmos_output_bad",
        ["ac4-atmos", "--output", str(OUT / "x.ec3")],
        info(16, damf=True),
        DAMF,
    ),
    ("ac4_atmos_reuse", ["ac4-atmos", "--reuse-temp-files"], info(8, thd=True), MKV),
    ("ac4_atmos_channel_based", ["ac4-atmos"], info(8), MKV),
    ("ac4_atmos_wav", ["ac4-atmos"], info(6), WAV),
]
SCENARIOS += AC4_ATMOS_SCENARIOS

# --- Atmos masters (DAMF and ADM BWF go to DEE as they are)
MASTER_SCENARIOS = [
    # a probed DAMF has a channel per bed channel and object, and no video
    ("atmos_damf", ["ddp-atmos"], info(16, fps=None, damf=True), DAMF),
    ("atmos_damf_delay", ["ddp-atmos", "--delay=-20ms"], info(16, damf=True), DAMF),
    ("atmos_damf_pos", ["ddp-atmos", "--delay=100ms"], info(16, damf=True), DAMF),
    ("atmos_damf_768", ["ddp-atmos", "--bitrate", "768"], info(16, damf=True), DAMF),
    (
        "atmos_damf_warp",
        ["ddp-atmos", "--thd-warp-mode", "normal"],
        info(16, damf=True),
        DAMF,
    ),
    # objects aren't channels: a master of few elements still renders to 5.1
    ("atmos_damf_few", ["ddp-atmos"], info(4, damf=True), DAMF),
    ("atmos_adm_few", ["ddp-atmos"], info(4, adm=True), WAV),
    (
        "atmos_damf_bluray",
        ["ddp-atmos", "--atmos-mode", "bluray"],
        info(16, damf=True),
        DAMF,
    ),
    ("ac4_damf", ["ac4-ims"], info(16, damf=True), DAMF),
    ("ac4_damf_few", ["ac4-ims"], info(4, damf=True), DAMF),
    ("ac4_damf_delay", ["ac4-ims", "--delay=-20ms"], info(16, damf=True), DAMF),
    # channel-based formats refuse a master
    ("dd_damf", ["dd"], info(16, damf=True), DAMF),
    ("ddp_damf", ["ddp"], info(16, damf=True), DAMF),
    ("ddp_adm", ["ddp"], info(16, adm=True), WAV),
    ("ac4ch_damf", ["ac4"], info(16, damf=True), DAMF),
    ("aac_damf", ["aac"], info(16, damf=True), DAMF),
    ("thd_damf", ["thd"], info(16, damf=True), DAMF),
    ("thd_adm", ["thd"], info(16, adm=True), WAV),
]
SCENARIOS += MASTER_SCENARIOS

# --- dd and ddp from a master: DEE renders it (5.1 +256 samples, 2.0/1.0 +288)
D16 = info(16, damf=True)
RENDER_SCENARIOS = [
    ("dd_damf_stereo", ["dd", "--channels", "2"], D16, DAMF),
    ("dd_damf_mono", ["dd", "--channels", "1"], D16, DAMF),
    ("dd_damf_few", ["dd"], info(4, damf=True), DAMF),
    ("dd_damf_640", ["dd", "--bitrate", "640"], D16, DAMF),
    ("dd_damf_delay_neg", ["dd", "--delay=-20ms"], D16, DAMF),
    ("dd_damf_stereo_delay", ["dd", "--channels", "2", "--delay=100ms"], D16, DAMF),
    ("dd_damf_dpl2_51", ["dd", "--stereo-down-mix", "dpl2"], D16, DAMF),
    (
        "dd_damf_dpl2_stereo",
        ["dd", "--channels", "2", "--stereo-down-mix", "dpl2"],
        D16,
        DAMF,
    ),
    ("dd_damf_ltrt_51", ["dd", "--stereo-down-mix", "ltrt"], D16, DAMF),
    ("dd_adm_target", ["dd", "--loudness-target", "-24"], info(16, adm=True), WAV),
    ("ddp_damf_stereo", ["ddp", "--channels", "2"], D16, DAMF),
    ("ddp_damf_mono", ["ddp", "--channels", "1"], D16, DAMF),
    ("ddp_damf_51", ["ddp", "--channels", "6"], D16, DAMF),
    ("ddp_damf_71", ["ddp", "--channels", "8"], D16, DAMF),
    ("ddp_damf_delay_pos", ["ddp", "--delay=100ms"], D16, DAMF),
    ("ddp_damf_dialnorm", ["ddp", "--custom-dialnorm", "-27"], D16, DAMF),
    ("ddp_damf_preset", ["ddp", "--loudness-preset", "ebu_r128"], D16, DAMF),
    ("ddp_damf_dpl2_51", ["ddp", "--stereo-down-mix", "dpl2"], D16, DAMF),
    (
        "ddp_damf_ltrt_stereo",
        ["ddp", "--channels", "2", "--stereo-down-mix", "ltrt"],
        D16,
        DAMF,
    ),
    ("ddp_damf_secondary", ["ddp", "--bluray-secondary"], D16, DAMF),
    (
        "ddp_damf_secondary_stereo",
        ["ddp", "--bluray-secondary", "--channels", "2", "--bitrate", "100"],
        D16,
        DAMF,
    ),
    (
        "ddp_damf_secondary_mono",
        ["ddp", "--bluray-secondary", "--channels", "1"],
        D16,
        DAMF,
    ),
    ("ddp_damf_user_data", ["ddp", "--user-data", "7"], D16, DAMF),
    ("ddp_damf_pipe_always", ["ddp", "--pipe", "always"], D16, DAMF),
    ("ddp_damf_output_bad", ["ddp", "--output", str(OUT / "x.ac3")], D16, DAMF),
    ("bluray_damf", ["ddp-bluray"], D16, DAMF),
    # a TrueHD Atmos stream is no master: FFmpeg decodes its 7.1 presentation
    ("dd_thd_atmos", ["dd"], info(8, thd=True), MKV),
    ("ddp_thd_atmos", ["ddp"], info(8, thd=True), MKV),
]
SCENARIOS += RENDER_SCENARIOS

# --- measure (arguments start with 'measure', which replaces 'encode')
MEASURE_SCENARIOS = [
    ("measure_6", ["measure"], info(6), MKV),
    ("measure_2", ["measure"], info(2), MKV),
    ("measure_1", ["measure"], info(1), MKV),
    ("measure_3", ["measure"], info(3), MKV),
    ("measure_5", ["measure"], info(5), MKV),
    ("measure_7", ["measure"], info(7), MKV),
    ("measure_8", ["measure"], info(8), MKV),
    ("measure_441", ["measure"], info(2, rate=44100), MKV),
    ("measure_96k_5", ["measure"], info(5, rate=96000), MKV),
    ("measure_thd", ["measure"], info(8, thd=True), MKV),
    (
        "measure_thd_warp",
        ["measure", "--thd-warp-mode", "normal"],
        info(8, thd=True),
        MKV,
    ),
    ("measure_adm", ["measure"], info(8, adm=True), WAV),
    ("measure_damf", ["measure"], info(16, damf=True), DAMF),
    ("measure_preset", ["measure", "--loudness-preset", "ebu_r128"], info(6), MKV),
    (
        "measure_manual",
        ["measure", "--no-dialogue-intelligence", "--speech-threshold", "30"],
        info(6),
        MKV,
    ),
    ("measure_output", ["measure", "--output", str(OUT / "loud.json")], info(6), MKV),
    ("measure_output_dir", ["measure", "--output-dir", str(OUT)], info(6), MKV),
    (
        "measure_output_dir_track",
        ["measure", "--output-dir", str(OUT), "--track-index", "2"],
        info(6),
        MKV,
    ),
    (
        "measure_output_dir_stream",
        ["measure", "--output-dir", str(OUT), "--track-index", "s:3"],
        info(2),
        MKV,
    ),
]
SCENARIOS += MEASURE_SCENARIOS

# planned as on Windows, where each job gets a named pipe
PIPE_NAME = "deezy-PID-JOB"
PIPE_SCENARIOS = [
    ("pipe_dd_auto_6", ["dd"], info(6), MKV),
    ("pipe_dd_stereo_from6", ["dd", "--channels", "2"], info(6), MKV),
    (
        "pipe_dd_dpl2",
        ["dd", "--channels", "2", "--stereo-down-mix", "dpl2"],
        info(6),
        MKV,
    ),
    ("pipe_dd_upmix50", ["dd", "--channels", "6", "--upmix-50-to-51"], info(5), MKV),
    ("pipe_dd_auto_3", ["dd"], info(3), MKV),
    ("pipe_ddp_auto_8", ["ddp"], info(8), MKV),
    ("pipe_ddp_1_from2", ["ddp", "--channels", "1"], info(2), MKV),
    ("pipe_ddp_441", ["ddp"], info(2, rate=44100), MKV),
    ("pipe_ddp_dialnorm", ["ddp", "--custom-dialnorm", "-31"], info(6), MKV),
    ("pipe_ddp_delay", ["ddp", "--delay=100ms"], info(6), MKV),
    ("pipe_ddp_secondary", ["ddp", "--bluray-secondary"], info(6), MKV),
    ("pipe_ddp_never", ["ddp", "--pipe", "never"], info(6), MKV),
    ("pipe_ddp_always", ["ddp", "--pipe", "always"], info(6), MKV),
    ("pipe_ddp_reuse", ["ddp", "--reuse-temp-files"], info(6), MKV),
    (
        "pipe_ddp_reuse_always",
        ["ddp", "--reuse-temp-files", "--pipe", "always"],
        info(6),
        MKV,
    ),
    ("pipe_bluray_8", ["ddp-bluray"], info(8), MKV),
    ("pipe_bluray_10", ["ddp-bluray"], info(10), MKV),
    ("pipe_ac4ch_6", ["ac4"], info(6), MKV),
    ("pipe_ac4ch_8_441", ["ac4"], info(8, rate=44100), MKV),
    ("pipe_ac4ch_1", ["ac4"], info(1), MKV),
    ("pipe_aac_6", ["aac"], info(6), MKV),
    ("pipe_aac_8_441", ["aac"], info(8, rate=44100), MKV),
    ("pipe_aac_target", ["aac", "--loudness-target", "-24"], info(2), MKV),
    ("pipe_measure_6", ["measure"], info(6), MKV),
    ("pipe_measure_5_441", ["measure"], info(5, rate=44100), MKV),
    ("pipe_measure_always", ["measure", "--pipe", "always"], info(1), MKV),
    ("pipe_measure_never", ["measure", "--pipe", "never"], info(2), MKV),
    # these keep their WAV or DAMF
    ("pipe_ac4_6", ["ac4-ims"], info(6), MKV),
    ("pipe_atmos_thd", ["ddp-atmos"], info(8, thd=True), MKV),
    ("pipe_measure_thd", ["measure"], info(8, thd=True), MKV),
    ("pipe_thd_6", ["thd"], info(6), MKV),
]
# --- dee_shim found: the DD+ Atmos and TrueHD encoders run through it, the
# others don't (the CLI hands the shim it found to the payload)
WITH_SHIM = ["--dee-shim", str(SHIM)]
SHIM_SCENARIOS = [
    ("shim_atmos_thd", ["ddp-atmos", *WITH_SHIM], info(8, thd=True), MKV),
    ("shim_atmos_damf", ["ddp-atmos", *WITH_SHIM], D16, DAMF),
    (
        "shim_atmos_delay",
        ["ddp-atmos", *WITH_SHIM, "--delay=-20ms"],
        info(16, fps=None, adm=True),
        WAV,
    ),
    (
        "shim_atmos_bluray",
        ["ddp-atmos", *WITH_SHIM, "--atmos-mode", "bluray"],
        info(8, thd=True),
        MKV,
    ),
    ("shim_thd_8", ["thd", *WITH_SHIM], info(8), MKV),
    ("shim_thd_2_delay", ["thd", *WITH_SHIM, "--delay=100ms"], info(2), MKV),
    ("shim_thd_96k", ["thd", *WITH_SHIM], info(6, rate=96000), MKV),
    ("shim_thd_atmos_thd", ["thd-atmos", *WITH_SHIM], info(8, thd=True), MKV),
    (
        "shim_thd_atmos_legacy",
        ["thd-atmos", *WITH_SHIM, "--legacy-authoring"],
        D16,
        DAMF,
    ),
    ("shim_off", ["thd", *WITH_SHIM, "--no-shim"], info(6), MKV),
    # these never run through it
    ("shim_ddp_6", ["ddp", *WITH_SHIM], info(6), MKV),
    ("shim_ddp_auto_8", ["ddp", *WITH_SHIM], info(8), MKV),
    ("shim_ddp_71", ["ddp", *WITH_SHIM, "--channels", "8"], info(8), MKV),
    ("shim_ddp_damf", ["ddp", *WITH_SHIM], D16, DAMF),
    ("shim_bluray", ["ddp-bluray", *WITH_SHIM], info(8), MKV),
    ("shim_dd", ["dd", *WITH_SHIM], info(6), MKV),
    ("shim_ac4_atmos", ["ac4-atmos", *WITH_SHIM], D16, DAMF),
    ("shim_ac4_ims", ["ac4-ims", *WITH_SHIM], info(6), MKV),
    ("shim_ac4", ["ac4", *WITH_SHIM], info(6), MKV),
    ("shim_aac", ["aac", *WITH_SHIM], info(6), MKV),
]
SCENARIOS += SHIM_SCENARIOS

ALL_SCENARIOS = [(*s, None) for s in SCENARIOS] + [
    (*s, PIPE_NAME) for s in PIPE_SCENARIOS
]

BUILDERS = {
    "dd": PayloadBuilder.build_dd_payload,
    "ddp": PayloadBuilder.build_ddp_payload,
    "ddp-bluray": PayloadBuilder.build_ddp_payload,
    "ddp-atmos": PayloadBuilder.build_atmos_payload,
    "ac4": PayloadBuilder.build_ac4_channel_payload,
    "ac4-ims": PayloadBuilder.build_ac4_payload,
    "ac4-atmos": PayloadBuilder.build_ac4_atmos_payload,
    "aac": PayloadBuilder.build_aac_payload,
    "thd": PayloadBuilder.build_thd_payload,
    "thd-atmos": PayloadBuilder.build_thd_atmos_payload,
}


class FakeNamer:
    """Names outputs from what it was given, instead of from the source's tags."""

    def __init__(self, file_input: Path):
        self.file_input = file_input

    def generate_output_filename(
        self,
        delay_was_stripped,
        delay_relative_to_video,
        suffix,
        output_channels,
        worker_id,
    ) -> Path:
        name = (
            f"{self.file_input.stem} [{output_channels}] s{int(delay_was_stripped)} "
            f"r{delay_relative_to_video} w{worker_id}{suffix}"
        )
        return OUT / name

    def render_output_template(
        self,
        template,
        suffix,
        output_channels,
        delay_was_stripped,
        delay_relative_to_video,
        worker_id=None,
    ) -> Path:
        return (
            OUT / f"T {template} [{output_channels}] s{int(delay_was_stripped)}{suffix}"
        )


def norm(value) -> str:
    text = str(value).replace("\\", "/")
    suffix = get_executable_extension()
    if suffix and text.startswith(str(DEE).replace("\\", "/")):
        text = text.removesuffix(suffix)
    return text


def norm_argv(argv) -> list[str]:
    return [norm(arg) for arg in argv]


@pytest.fixture(scope="module")
def parser():
    main = cli.create_main_parser()
    sub = main.add_subparsers(dest="sub_command")
    groups = cli.create_common_argument_groups()
    cli.create_encode_parsers(sub, groups)
    cli.create_other_parsers(sub, groups)
    return main


@pytest.fixture
def config() -> Iterator[ConfigManager]:
    # the shipped default config, never the developer's own
    ConfigManager.reset_instance()
    manager = ConfigManager()
    manager.config = tomlkit.parse(CONF_DEFAULT).unwrap()
    yield manager
    ConfigManager.reset_instance()


@pytest.fixture
def info_level() -> Iterator[None]:
    # the log level decides the verbosity options in the command lines
    level = logger.level
    logger.setLevel(logging.INFO)
    yield
    logger.setLevel(level)


def dee_entry(step: DeeStep) -> dict:
    entry: dict = {"dee": norm_argv(step.argv)}
    if step.custom_dialnorm:
        entry["custom_dialnorm"] = step.custom_dialnorm
    return entry


def planned(parser, config, args, probed, source, pipe_name=None) -> dict:
    """The scenario's plan as the golden file records it."""
    measuring = args[0] == "measure"
    command = [] if measuring else ["encode"]
    ns = parser.parse_args(["--no-progress-bars", *command, *args, str(source)])
    if measuring:
        apply_config_defaults_to_args(ns, config)
        payload = PayloadBuilder.build_measure_payload(ns, source, FFMPEG, TRUEHDD, DEE)
        planner = plan_measure
    else:
        apply_default_bitrate(ns, config)
        apply_config_defaults_to_args(ns, config)
        payload = BUILDERS[ns.format_command](ns, source, FFMPEG, TRUEHDD, DEE)
        if ns.dee_shim and not ns.no_shim:
            payload.dee_shim = DeeShim(Path(ns.dee_shim), "0.2.1+test")
        planner = plan_job
    track = AudioTrackInfo(mi_track=cast("Track", None), **probed)
    ctx = PlanContext(
        namer=FakeNamer(source), temp_dir=TEMP, config=config, pipe_name=pipe_name
    )
    try:
        plan = planner(payload, track, ctx)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {norm(e)}"}

    steps = []
    for step in plan.steps:
        if isinstance(step, FfmpegStep):
            steps.append({"ffmpeg": norm_argv(ffmpeg.with_loglevel(list(step.argv)))})
        elif isinstance(step, DeeStep):
            steps.append(dee_entry(step))
        elif isinstance(step, PipeStep):
            steps.append(
                {
                    "pipe": {
                        **dee_entry(step.dee),
                        "ffmpeg": norm_argv(
                            ffmpeg.with_loglevel(list(step.ffmpeg_argv))
                        ),
                    }
                }
            )
        else:
            extract = truehd_extract_command(
                step.ffmpeg, step.file_input, step.track_index
            )
            decode = truehdd_command(step.truehdd, step.output_dir, step.warp_mode)
            steps.append({"truehdd": [norm_argv(extract), norm_argv(decode)]})
    return {
        "output": norm(plan.output),
        "preview": plan.preview,
        "steps": steps,
    }


def test_golden_file_lists_every_scenario():
    if os.environ.get("DEEZY_UPDATE_GOLDEN"):
        pytest.skip("regenerating the golden file")
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert sorted(golden) == sorted(sid for sid, *_ in ALL_SCENARIOS)


def test_regenerate(parser, config, info_level):
    """With DEEZY_UPDATE_GOLDEN=1, write the golden file from the current planner."""
    if not os.environ.get("DEEZY_UPDATE_GOLDEN"):
        pytest.skip(
            "set DEEZY_UPDATE_GOLDEN=1 to regenerate tests/golden/commands.json"
        )
    results = {
        sid: planned(parser, config, args, probed, source, pipe_name)
        for sid, args, probed, source, pipe_name in ALL_SCENARIOS
    }
    GOLDEN.parent.mkdir(exist_ok=True)
    GOLDEN.write_text(json.dumps(results, indent=1) + "\n", encoding="utf-8")


@pytest.mark.parametrize(
    ("args", "probed", "source", "pipe_name"),
    [
        pytest.param(args, probed, source, pipe_name, id=sid)
        for sid, args, probed, source, pipe_name in ALL_SCENARIOS
    ],
)
def test_planned_commands_match_golden(
    request, parser, config, info_level, args, probed, source, pipe_name
):
    if os.environ.get("DEEZY_UPDATE_GOLDEN"):
        pytest.skip("regenerating the golden file")
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    sid = request.node.callspec.id
    assert planned(parser, config, args, probed, source, pipe_name) == golden[sid]
