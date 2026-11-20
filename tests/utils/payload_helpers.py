from pathlib import Path

from deezy.enums.shared import DeeDRC, MeteringMode, StereoDownmix
from deezy.payloads.shared import CorePayload
from deezy.track_info.track_index import TrackIndex


def generate_dummy_core_payload() -> CorePayload:
    """Generates a dummy core payload to appease tests."""
    return type(
        "TestPayload",
        (),
        {
            k: getattr(CorePayload, k).default
            if hasattr(getattr(CorePayload, k), "default")
            else None
            for k in CorePayload.__annotations__
        },
    )()  # type: ignore[assignment]


def make_core_fields(tmp_path: Path, keep_temp: bool) -> dict:
    # fields common to all Core/Loudness payloads
    return {
        "no_progress_bars": True,
        "ffmpeg_path": Path("/usr/bin/ffmpeg"),
        "truehdd_path": None,
        "dee_path": Path("/opt/dee"),
        "file_input": tmp_path / "in.wav",
        "track_index": TrackIndex.audio(0),
        "bitrate": 640,
        "temp_dir": None,
        "delay": None,
        "keep_temp": keep_temp,
        "reuse_temp_files": False,
        "file_output": None,
        "batch_output_dir": None,
        "worker_id": None,
        "overwrite": True,
        # template fields
        "output_template": "",
        "output_preview": False,
        # Loudness fields
        "metering_mode": MeteringMode.MODE_1770_3,
        "dialogue_intelligence": True,
        "speech_threshold": 15,
    }


def make_dolby_fields() -> dict:
    # additional fields required by Dolby-based payloads (DD/DDP)
    return {
        "drc_line_mode": DeeDRC.FILM_LIGHT,
        "drc_rf_mode": DeeDRC.FILM_LIGHT,
        "custom_dialnorm": "0",
        # StereoMix fields
        "stereo_mix": StereoDownmix.NOT_INDICATED,
        "lfe_lowpass_filter": True,
        "surround_90_degree_phase_shift": True,
        "surround_3db_attenuation": True,
        "loro_center_mix_level": "-3",
        "loro_surround_mix_level": "-3",
        "ltrt_center_mix_level": "-3",
        "ltrt_surround_mix_level": "-3",
        "preferred_downmix_mode": StereoDownmix.NOT_INDICATED,
        "upmix_50_to_51": False,
    }
