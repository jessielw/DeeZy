from pathlib import Path
from typing import Any

from deezy.enums.dd import DolbyDigitalChannels
from deezy.enums.ddp import DolbyDigitalPlusChannels
from deezy.enums.shared import DeeDRC, ProgressMode, StereoDownmix


class ConfigValidationError(Exception):
    """Raised when configuration validation fails."""


class ConfigSchema:
    """Configuration schema validator for DeeZy TOML configs."""

    __slots__ = ()

    @staticmethod
    def validate_config(config: dict[str, Any]) -> dict[str, Any]:
        """Validate and normalize configuration dictionary.

        Args:
            config: Raw configuration dictionary from TOML

        Returns:
            Validated and normalized configuration

        Raises:
            ConfigValidationError: If validation fails
        """
        try:
            validated = {}

            # validate dependencies section
            if "dependencies" in config:
                validated["dependencies"] = ConfigSchema._validate_dependencies(
                    config["dependencies"]
                )

            # validate defaults section
            if "defaults" in config:
                validated["defaults"] = ConfigSchema._validate_defaults(
                    config["defaults"]
                )

            # validate presets section
            if "presets" in config:
                validated["presets"] = ConfigSchema._validate_presets(config["presets"])

            return validated

        except Exception as e:
            raise ConfigValidationError(f"Configuration validation failed: {e}")

    @staticmethod
    def _validate_dependencies(deps: dict[str, Any]) -> dict[str, str]:
        """Validate dependencies section."""
        validated = {}

        for tool in ["ffmpeg", "dee", "truehd"]:
            if tool in deps:
                path_str = str(deps[tool])
                if path_str and not Path(path_str).exists():
                    # don't fail validation for non-existent paths - they might be in PATH
                    # just warn that the specified path doesn't exist
                    pass
                validated[tool] = path_str

        return validated

    @staticmethod
    def _validate_defaults(defaults: dict[str, Any]) -> dict[str, Any]:
        """Validate defaults section."""
        validated = {}

        # validate global defaults
        if "global" in defaults:
            validated["global"] = ConfigSchema._validate_global_defaults(
                defaults["global"]
            )

        # validate DD defaults
        if "dd" in defaults:
            validated["dd"] = ConfigSchema._validate_dd_defaults(defaults["dd"])

        # validate DDP defaults
        if "ddp" in defaults:
            validated["ddp"] = ConfigSchema._validate_ddp_defaults(defaults["ddp"])

        return validated

    @staticmethod
    def _validate_global_defaults(global_cfg: dict[str, Any]) -> dict[str, Any]:
        """Validate global defaults."""
        validated = {}

        if "progress_mode" in global_cfg:
            mode = global_cfg["progress_mode"]
            if isinstance(mode, str):
                try:
                    ProgressMode[mode.upper()]
                    validated["progress_mode"] = mode.upper()
                except KeyError:
                    raise ConfigValidationError(f"Invalid progress_mode: {mode}")
            else:
                validated["progress_mode"] = str(mode)

        if "keep_temp" in global_cfg:
            validated["keep_temp"] = bool(global_cfg["keep_temp"])

        if "temp_dir" in global_cfg:
            validated["temp_dir"] = str(global_cfg["temp_dir"])

        if "track_index" in global_cfg:
            track_idx = global_cfg["track_index"]
            if isinstance(track_idx, int) and track_idx >= 0:
                validated["track_index"] = track_idx
            else:
                raise ConfigValidationError(f"Invalid track_index: {track_idx}")

        return validated

    @staticmethod
    def _validate_dd_defaults(dd_cfg: dict[str, Any]) -> dict[str, Any]:
        """Validate Dolby Digital defaults."""
        validated = {}

        if "channels" in dd_cfg:
            channels = dd_cfg["channels"]
            if isinstance(channels, str):
                try:
                    DolbyDigitalChannels[channels.upper()]
                    validated["channels"] = channels.upper()
                except KeyError:
                    raise ConfigValidationError(f"Invalid DD channels: {channels}")

        if "bitrate" in dd_cfg:
            bitrate = dd_cfg["bitrate"]
            if isinstance(bitrate, int) and 32 <= bitrate <= 640:
                validated["bitrate"] = bitrate
            else:
                raise ConfigValidationError(f"Invalid DD bitrate: {bitrate}")

        if "drc" in dd_cfg:
            drc = dd_cfg["drc"]
            if isinstance(drc, str):
                try:
                    DeeDRC[drc.upper()]
                    validated["drc"] = drc.upper()
                except KeyError:
                    raise ConfigValidationError(f"Invalid DRC: {drc}")

        if "stereo_down_mix" in dd_cfg:
            mix = dd_cfg["stereo_down_mix"]
            if isinstance(mix, str):
                try:
                    StereoDownmix[mix.upper()]
                    validated["stereo_down_mix"] = mix.upper()
                except KeyError:
                    raise ConfigValidationError(f"Invalid stereo downmix: {mix}")

        return validated

    @staticmethod
    def _validate_ddp_defaults(ddp_cfg: dict[str, Any]) -> dict[str, Any]:
        """Validate Dolby Digital Plus defaults."""
        validated = {}

        if "channels" in ddp_cfg:
            channels = ddp_cfg["channels"]
            if isinstance(channels, str):
                try:
                    DolbyDigitalPlusChannels[channels.upper()]
                    validated["channels"] = channels.upper()
                except KeyError:
                    raise ConfigValidationError(f"Invalid DDP channels: {channels}")

        if "bitrate" in ddp_cfg:
            bitrate = ddp_cfg["bitrate"]
            if isinstance(bitrate, int) and 32 <= bitrate <= 1664:
                validated["bitrate"] = bitrate
            else:
                raise ConfigValidationError(f"Invalid DDP bitrate: {bitrate}")

        if "drc" in ddp_cfg:
            drc = ddp_cfg["drc"]
            if isinstance(drc, str):
                try:
                    DeeDRC[drc.upper()]
                    validated["drc"] = drc.upper()
                except KeyError:
                    raise ConfigValidationError(f"Invalid DRC: {drc}")

        if "stereo_down_mix" in ddp_cfg:
            mix = ddp_cfg["stereo_down_mix"]
            if isinstance(mix, str):
                try:
                    StereoDownmix[mix.upper()]
                    validated["stereo_down_mix"] = mix.upper()
                except KeyError:
                    raise ConfigValidationError(f"Invalid stereo downmix: {mix}")

        for bool_option in ["normalize", "atmos", "no_bed_conform"]:
            if bool_option in ddp_cfg:
                validated[bool_option] = bool(ddp_cfg[bool_option])

        return validated

    @staticmethod
    def _validate_presets(presets: dict[str, Any]) -> dict[str, Any]:
        """Validate presets section."""
        validated = {}

        for preset_name, preset_config in presets.items():
            if not isinstance(preset_config, dict):
                raise ConfigValidationError(
                    f"Preset '{preset_name}' must be a dictionary"
                )

            # basic validation - presets can contain any valid encoding options
            validated[preset_name] = dict(preset_config)

        return validated
