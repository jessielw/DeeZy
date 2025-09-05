"""Default configuration values for DeeZy."""

from pathlib import Path
from typing import Any

from deezy.enums.dd import DolbyDigitalChannels
from deezy.enums.ddp import DolbyDigitalPlusChannels
from deezy.enums.shared import DeeDRC, ProgressMode, StereoDownmix


# default configuration structure
DEFAULT_CONFIG: dict[str, Any] = {
    "dependencies": {
        "ffmpeg": "",  # Auto-detect
        "dee": "",  # Auto-detect
        "truehd": "",  # Auto-detect (optional)
    },
    "defaults": {
        "global": {
            "progress_mode": ProgressMode.STANDARD.name,
            "keep_temp": False,
            "temp_dir": "",  # Use system temp
            "track_index": 0,
        },
        "dd": {
            "channels": DolbyDigitalChannels.AUTO.name,
            "bitrate": 448,
            "drc": DeeDRC.FILM_LIGHT.name,
            "stereo_down_mix": StereoDownmix.STANDARD.name,
        },
        "ddp": {
            "channels": DolbyDigitalPlusChannels.AUTO.name,
            "bitrate": 640,
            "drc": DeeDRC.FILM_LIGHT.name,
            "stereo_down_mix": StereoDownmix.STANDARD.name,
            "normalize": False,
            "atmos": False,
            "no_bed_conform": False,
        },
    },
    "presets": {
        # User-defined presets will be added here
    },
}


def get_config_locations() -> list[Path]:
    """Get potential configuration file locations in priority order.

    Returns:
        List of Path objects for potential config locations:
        1. Portable config beside executable
        2. User config directory
        3. System config directory (future)
    """
    import os
    import sys

    locations = []

    # 1. Portable config beside executable
    if getattr(sys, "frozen", False):
        # Running as compiled executable
        exe_dir = Path(sys.executable).parent
    else:
        # Running as script - use current working directory
        exe_dir = Path.cwd()

    portable_config = exe_dir / "deezy-config.toml"
    locations.append(portable_config)

    # 2. User config directory
    if os.name == "nt":  # Windows
        appdata = os.environ.get("APPDATA")
        if appdata:
            user_config = Path(appdata) / "DeeZy" / "config.toml"
            locations.append(user_config)
    else:  # Linux/macOS
        home = Path.home()
        user_config = home / ".config" / "deezy" / "config.toml"
        locations.append(user_config)

    return locations


def get_default_config_path() -> Path:
    """Get the default path for creating new config files.

    Returns:
        Path where new config files should be created.
    """
    locations = get_config_locations()

    # For new configs, prefer user directory over portable
    # unless we're in a portable environment
    if len(locations) > 1:
        return locations[1]  # User config directory
    else:
        return locations[0]  # Fallback to portable
