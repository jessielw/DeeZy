import argparse
from pathlib import Path
from typing import Any

import oslex2
import tomlkit

from deezy.config.defaults import CONF_DEFAULT, get_default_config_path
from deezy.enums.dd import DolbyDigitalChannels
from deezy.enums.ddp import DolbyDigitalPlusChannels
from deezy.enums.ddp_bluray import DolbyDigitalPlusBlurayChannels
from deezy.utils.exit import EXIT_FAIL, exit_application
from deezy.utils.logger import logger


def set_config_default(
    args: argparse.Namespace, arg_name: str, config_value: Any, fallback_value: Any
) -> None:
    """Helper function to set config defaults with proper precedence.

    Args:
        args: The argparse namespace
        arg_name: Name of the argument
        config_value: Value from config file (or None if not set)
        fallback_value: Hardcoded fallback value
    """
    if not hasattr(args, arg_name):
        if config_value is not None:
            setattr(args, arg_name, config_value)
            logger.debug(f"Applied config default: {arg_name} = {config_value}")
        else:
            setattr(args, arg_name, fallback_value)
            logger.debug(f"Applied fallback default: {arg_name} = {fallback_value}")
    else:
        # CLI set this argument, keep CLI value
        current_value = getattr(args, arg_name)
        logger.debug(f"Using CLI value: {arg_name} = {current_value}")


class ConfigManager:
    """Configuration manager that only handles defaults and string presets."""

    _instance = None
    _initialized = False

    def __new__(cls) -> "ConfigManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        # only initialize once
        if not self._initialized:
            self.config: dict[str, Any] = {}
            self.config_path: Path | None = None
            self._initialized = True

    def load_config(self, config_path: str | Path | None = None) -> None:
        """Load configuration from TOML file."""
        if config_path is None:
            config_path = get_default_config_path()
        else:
            config_path = Path(config_path)

        if config_path and Path(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    self.config.update(tomlkit.load(f))
                self.config_path = config_path
                logger.debug(f"Loaded config from {config_path}")

                # validate config structure
                self._validate_config()
            except Exception as e:
                logger.warning(f"Failed to load config: {e}")
                self.config.clear()
        else:
            logger.debug("No config file found, using defaults")
            self.config.clear()

    def _validate_config(self) -> None:
        """Validate the loaded configuration structure."""
        # ensure required sections exist
        if "presets" not in self.config:
            self.config["presets"] = {}
        if "global_defaults" not in self.config:
            self.config["global_defaults"] = {}
        if "default_bitrates" not in self.config:
            self.config["default_bitrates"] = {}
        if "dependencies" not in self.config:
            self.config["dependencies"] = {}

    def get_preset_command(self, preset_name: str) -> str:
        """Get the CLI command string for a preset."""
        if not self.config.get("presets"):
            exit_application("No presets defined in configuration.", EXIT_FAIL)

        preset_command = self.config["presets"].get(preset_name)
        if not preset_command:
            available = ", ".join(self.config["presets"].keys()) or "None"
            exit_application(
                f"Preset '{preset_name}' not found. Available: {available}", EXIT_FAIL
            )

        return preset_command

    def parse_preset_command(self, preset_name: str) -> list[str]:
        """Parse preset command string into arguments list."""
        preset_command = self.get_preset_command(preset_name)
        return oslex2.split(preset_command)

    def apply_defaults_to_args(self, args: argparse.Namespace) -> None:
        """Apply configuration defaults to arguments."""
        # apply global defaults
        self._apply_global_defaults(args)

        # apply format-specific defaults if we have a format
        if hasattr(args, "format_command") and args.format_command:
            self._apply_format_defaults(args, args.format_command)

        # apply default bitrates if not specified
        self._apply_default_bitrate(args)

    def _apply_global_defaults(self, args: argparse.Namespace) -> None:
        """Apply global defaults from config, with proper precedence: CLI > Config > Fallback defaults.

        Uses argparse.SUPPRESS to detect if arguments were set by CLI or not.
        If an argument doesn't exist on args, it wasn't provided by CLI.

        To add a new configurable argument:
        1. In CLI definition: set default=argparse.SUPPRESS
        2. Add entry to fallback_defaults dict below
        3. That's it! The precedence system handles the rest automatically.
        """
        global_defaults = self.config.get("global_defaults", {})

        # final fallback defaults (used when no CLI arg and no config value)
        fallback_defaults = {
            # basic options
            "keep_temp": False,
            "temp_dir": None,
            "track_index": 0,
            "delay": None,
            "bitrate": None,
            # audio processing
            "drc_line_mode": "film_light",
            "drc_rf_mode": "film_light",
            "custom_dialnorm": 0,
            # metering_mode: handled per-format (DD/DDP=1770-3, Atmos=1770-4)
            "dialogue_intelligence": True,
            "speech_threshold": 15,
            # downmix settings
            "stereo_down_mix": "loro",
            "lt_rt_center": "-3",
            "lt_rt_surround": "-3",
            "lo_ro_center": "-3",
            "lo_ro_surround": "-3",
            # format options
            "no_low_pass_filter": True,
            "no_surround_3db": True,
            "no_surround_90_deg_phase_shift": True,
            # channel defaults - format-specific, handled in _apply_format_defaults
            # "channels": handled per-format since each has different enums/defaults
            # atmos options
            "atmos_mode": "streaming",
            "thd_warp_mode": "normal",
            "no_bed_conform": False,
        }

        # apply defaults with clean precedence logic
        for arg_name, fallback_value in fallback_defaults.items():
            if not hasattr(args, arg_name):
                # check if we have a config default
                if arg_name in global_defaults:
                    setattr(args, arg_name, global_defaults[arg_name])
                    logger.debug(
                        f"Applied config default: {arg_name} = {global_defaults[arg_name]}"
                    )
                else:
                    # fall back to hardcoded default
                    setattr(args, arg_name, fallback_value)
                    logger.debug(
                        f"Applied fallback default: {arg_name} = {fallback_value}"
                    )
            else:
                # argument exists - user provided it via CLI, keep CLI value
                current_value = getattr(args, arg_name)
                logger.debug(f"Using CLI value: {arg_name} = {current_value}")

    def _apply_format_defaults(
        self, args: argparse.Namespace, format_type: str
    ) -> None:
        """Apply format-specific defaults."""
        format_defaults = self.config.get("format_defaults", {}).get(format_type, {})

        # apply config-based format defaults
        for key, value in format_defaults.items():
            arg_name = key.replace("-", "_")
            if hasattr(args, arg_name) and getattr(args, arg_name) is None:
                setattr(args, arg_name, value)

        # apply format-specific channel defaults if not set by CLI or config
        if not hasattr(args, "channels"):
            if format_type == "dd":
                setattr(args, "channels", DolbyDigitalChannels.AUTO)
                logger.debug("Applied DD channel default: AUTO")
            elif format_type == "ddp":
                setattr(args, "channels", DolbyDigitalPlusChannels.AUTO)
                logger.debug("Applied DDP channel default: AUTO")
            elif format_type == "ddp-bluray":
                setattr(args, "channels", DolbyDigitalPlusBlurayChannels.SURROUNDEX)
                logger.debug("Applied DDP-BluRay channel default: SURROUNDEX")
            # atmos doesn't use channels argument

        # apply format-specific metering defaults if not set by CLI or config
        if not hasattr(args, "metering_mode"):
            from deezy.enums.shared import MeteringMode

            # atmos
            if format_type == "atmos":
                setattr(args, "metering_mode", MeteringMode.MODE_1770_4)
                logger.debug("Applied Atmos metering default: 1770-4")
            # DD/DDP default to 1770-3
            else:
                setattr(args, "metering_mode", MeteringMode.MODE_1770_3)
                logger.debug(f"Applied {format_type.upper()} metering default: 1770-3")

    def _apply_default_bitrate(self, args: argparse.Namespace) -> None:
        """Apply default bitrate if not specified and format/channels are available."""
        if (
            hasattr(args, "bitrate")
            and args.bitrate is None
            and hasattr(args, "format_command")
            and args.format_command
            and hasattr(args, "channels")
            and args.channels
        ):
            # convert channels enum to string if needed
            if hasattr(args.channels, "name"):
                # this is an enum, get the name part (e.g., STEREO -> stereo)
                channels_str = args.channels.name.lower()
            else:
                # this is already a string
                channels_str = str(args.channels).lower()

            default_bitrate = self.get_default_bitrate(
                args.format_command, channels_str
            )

            if default_bitrate:
                args.bitrate = default_bitrate
                logger.debug(
                    f"Applied default bitrate {default_bitrate} for {args.format_command}/{channels_str}"
                )

    def get_default_bitrate(self, format_type: str, channel_config: str) -> int | None:
        """Get default bitrate for format/channel combination."""
        bitrates = self.config.get("default_bitrates", {}).get(format_type, {})
        return bitrates.get(channel_config)

    def list_presets(self) -> list[str]:
        """List available presets."""
        return list(self.config.get("presets", {}).keys())

    def generate_config(
        self, output_path: Path | None = None, overwrite: bool = False
    ) -> Path:
        """Generate a config file using the defaults template."""
        if output_path is None:
            output_path = Path(get_default_config_path())

        if output_path.exists() and not overwrite:
            raise FileExistsError(f"Config file already exists: {output_path}")

        output_path.parent.mkdir(parents=True, exist_ok=True)

        # write the default config template directly
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(CONF_DEFAULT)

        logger.info(f"Generated config file: {output_path}")
        return output_path

    def get_dependencies_paths(self) -> dict[str, str]:
        """Get configured dependency paths."""
        return self.config.get("dependencies", {})

    def has_valid_config(self) -> bool:
        """Check if a valid config file is loaded."""
        return bool(self.config_path and self.config_path.exists())

    def get_preset_info(self, preset_name: str) -> dict[str, str]:
        """Get information about a preset."""
        if preset_name not in self.config.get("presets", {}):
            available = ", ".join(self.config.get("presets", {}).keys()) or "None"
            raise ValueError(
                f"Preset '{preset_name}' not found. Available: {available}"
            )

        command = self.config["presets"][preset_name]
        args = oslex2.split(command)

        # parse the command to extract format and options
        info = {
            "name": preset_name,
            "command": command,
            "description": f"Preset command: {command}",
        }

        if len(args) >= 2:
            info["format"] = args[1]  # e.g. 'ddp', 'dd', 'atmos'

        return info

    def validate_preset(self, preset_name: str) -> bool:
        """Validate that a preset command is well-formed."""
        try:
            command = self.get_preset_command(preset_name)
            args = oslex2.split(command)

            # basic validation - should start with 'encode' and have a format
            if len(args) < 2:
                logger.warning(f"Preset '{preset_name}' command too short: {command}")
                return False

            if args[0] != "encode":
                logger.warning(
                    f"Preset '{preset_name}' should start with 'encode': {command}"
                )
                return False

            valid_formats = ["dd", "ddp", "ddp-bluray", "atmos"]
            if args[1] not in valid_formats:
                logger.warning(
                    f"Preset '{preset_name}' has invalid format '{args[1]}': {command}"
                )
                return False

            return True
        except Exception as e:
            logger.warning(f"Failed to validate preset '{preset_name}': {e}")
            return False

    @classmethod
    def get_instance(cls) -> "ConfigManager":
        """Get the singleton instance and ensure it's loaded."""
        instance = cls()
        # load config if not already loaded
        if not instance.config and not instance.config_path:
            instance.load_config()
        return instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton instance (useful for testing)."""
        cls._instance = None
        cls._initialized = False


def get_config_manager() -> ConfigManager:
    """Get the singleton config manager instance."""
    return ConfigManager.get_instance()
