from pathlib import Path
from typing import Any

from deezy.utils.utils import get_working_dir


# default configuration structure
DEFAULT_CONFIG: dict[str, Any] = {
    # dependencies (auto-detected if empty)
    "dependencies": {
        "ffmpeg": "",
        "dee": "",
        "truehd": "",
    },
    # global settings applied to all formats
    "global_defaults": {
        "keep_temp": False,
        "temp_dir": "",
        "track_index": 0,
        "drc_line_mode": "film_light",
        "drc_rf_mode": "film_light",
        "custom_dialnorm": 0,
        "metering_mode": "1770_3",
        "dialogue_intelligence": True,
        "speech_threshold": 15,
        "stereo_down_mix": "loro",
        "lt_rt_center": "-3",
        "lt_rt_surround": "-3",
        "lo_ro_center": "-3",
        "lo_ro_surround": "-3",
    },
    # default bitrates for each codec/channel combination
    # users can customize these values
    "default_bitrates": {
        "dd": {
            "mono": 192,  # DD 1.0
            "stereo": 224,  # DD 2.0
            "surround": 448,  # DD 5.1
        },
        "ddp": {
            "mono": 64,  # DDP 1.0
            "stereo": 128,  # DDP 2.0
            "surround": 192,  # DDP 5.1
            "surroundex": 384,  # DDP 7.1
        },
        "ddp_bluray": {
            "surroundex": 384,  # DDP Bluray 7.1
        },
        "atmos": {
            "streaming": 448,  # Atmos Streaming
            "bluray": 448,  # Atmos Bluray
        },
    },
    # format-specific settings (override global_defaults)
    "format_defaults": {
        "dd": {
            "channels": "auto",
            "lfe_lowpass_filter": True,
            "surround_3db_attenuation": True,
            "surround_90_degree_phase_shift": True,
        },
        "ddp": {
            "channels": "auto",
            "lfe_lowpass_filter": True,
            "surround_3db_attenuation": True,
            "surround_90_degree_phase_shift": True,
        },
        "ddp_bluray": {
            "channels": "surroundex",
            "lfe_lowpass_filter": True,
            "surround_3db_attenuation": True,
            "surround_90_degree_phase_shift": True,
        },
        "atmos": {
            "atmos_mode": "streaming",
            "thd_warp_mode": "normal",
            "no_bed_conform": True,
        },
    },
    # user-defined presets
    "presets": {
        # example presets (will be added by default)
        "streaming_ddp": {
            "format": "ddp",
            "channels": "surround",
            "bitrate": 448,
            "atmos_mode": "streaming",
        },
        "bluray_atmos": {
            "format": "atmos",
            "atmos_mode": "bluray",
            "bitrate": 768,
        },
        "quick_stereo": {
            "format": "ddp",
            "channels": "stereo",
            "bitrate": 192,
        },
    },
}


def get_config_locations() -> list[Path]:
    """Get potential configuration file locations in priority order.

    Returns:
        List of Path objects for potential config locations:
        1. Portable config beside executable (deezy-conf.toml)
    """
    locations = []
    exe_dir = get_working_dir()
    portable_config = exe_dir / "deezy-conf.toml"
    locations.append(portable_config)

    return locations


def get_default_config_path() -> Path:
    """Get the default path for creating new config files.

    Returns:
        Path where new config files should be created.
    """
    locations = get_config_locations()
    return locations[0]
