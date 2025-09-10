import argparse
from pathlib import Path
from typing import Any

import tomlkit
from tomlkit.exceptions import TOMLKitError

from deezy.config.defaults import (
    DEFAULT_CONFIG,
    get_config_locations,
    get_default_config_path,
)
from deezy.enums.atmos import AtmosMode
from deezy.enums.dd import DolbyDigitalChannels
from deezy.enums.ddp import DolbyDigitalPlusChannels
from deezy.enums.ddp_bluray import DolbyDigitalPlusBlurayChannels
from deezy.enums.shared import DeeDRC, MeteringMode, StereoDownmix
from deezy.utils.exit import EXIT_FAIL, exit_application
from deezy.utils.logger import logger


class ConfigManager:
    """Configuration manager singleton."""

    _instance: "ConfigManager | None" = None
    _initialized = False

    def __new__(cls) -> "ConfigManager":
        """Ensure only one instance exists."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """Initialize the config manager (only runs once)."""
        if not self._initialized:
            self.config_path: Path | None = None
            self.config: dict[str, Any] = DEFAULT_CONFIG.copy()
            self._loaded = False
            ConfigManager._initialized = True

    def load_config(self, config_path: Path | None = None) -> None:
        """Load configuration from file or use defaults.

        Args:
            config_path: Specific path to config file. If not provided, looks for deezy-conf.toml beside executable.
        """
        if config_path:
            # use explicit config path
            config_paths = [config_path]
        else:
            # look for deezy-conf.toml beside executable only
            config_paths = get_config_locations()

        # try to load from existing config files
        for path in config_paths:
            if path.exists() and path.is_file():
                try:
                    with open(path, "rb") as f:
                        user_config = tomlkit.load(f)

                    # merge with defaults
                    self.config = self._merge_configs(DEFAULT_CONFIG, dict(user_config))
                    self.config_path = path
                    self._loaded = True
                    logger.debug(f"Loaded config from {path}")
                    return
                except (TOMLKitError, OSError) as e:
                    logger.warning(f"Failed to load config from {path}: {e}")
                    continue

        # no config file found, use defaults
        self.config = DEFAULT_CONFIG.copy()
        self._loaded = True
        logger.debug("Using default configuration (no deezy-conf.toml found)")

    def generate_config(
        self, output_path: Path | None = None, overwrite: bool = False
    ) -> Path:
        """Generate a default configuration file."""
        if output_path is None:
            output_path = get_default_config_path()

        if output_path.exists() and not overwrite:
            raise FileExistsError(f"Config file already exists: {output_path}")

        # ensure directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # create config with comments
        config_content = self._create_default_config_with_comments()

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(config_content)

        return output_path

    def get_default_bitrate(self, format_type: str, channel_config: str) -> int | None:
        """Get default bitrate for format/channel combination."""
        bitrates = self.config.get("default_bitrates", {})
        format_bitrates = bitrates.get(format_type, {})
        return format_bitrates.get(channel_config)

    def get_configured_default_bitrate(
        self, format_type: str, channels_enum, fallback_default: int
    ) -> int:
        """Get configured default bitrate, falling back to enum default if not configured.

        This method is intended for use by encoders to get user-configured defaults.

        Args:
            format_type: Format type ('dd', 'ddp', 'atmos', etc.)
            channels_enum: The channels enum instance
            fallback_default: The enum's built-in default

        Returns:
            Configured default bitrate or enum default
        """
        # map enum to config channel names
        channel_mapping = {
            "MONO": "mono",
            "STEREO": "stereo",
            "SURROUND": "surround",
            "SURROUNDEX": "surroundex",
            "STREAMING": "streaming",
            "BLURAY": "bluray",
        }

        if hasattr(channels_enum, "name"):
            channel_name = channel_mapping.get(channels_enum.name.upper())
            if channel_name:
                configured_bitrate = self.get_default_bitrate(format_type, channel_name)
                if configured_bitrate is not None:
                    return configured_bitrate

        # fall back to enum default
        return fallback_default

    def get_format_defaults(self, format_type: str) -> dict[str, Any]:
        """Get merged defaults for a specific format."""
        global_defaults = self.config.get("global_defaults", {})
        format_defaults = self.config.get("format_defaults", {}).get(format_type, {})

        # merge global and format-specific defaults
        merged = {**global_defaults, **format_defaults}
        return merged

    def get_preset(self, preset_name: str) -> dict[str, Any] | None:
        """Get configuration for a named preset."""
        presets = self.config.get("presets", {})
        return presets.get(preset_name)

    def get_preset_format(self, preset_name: str) -> str | None:
        """Get the format specified in a preset."""
        preset = self.get_preset(preset_name)
        if preset:
            return preset.get("format")
        return None

    def list_presets(self) -> list[str]:
        """Get list of available preset names."""
        presets = self.config.get("presets", {})
        return list(presets.keys())

    def get_dependency_path(self, tool: str) -> str | None:
        """Get dependency path for a tool."""
        dependencies = self.config.get("dependencies", {})
        path = dependencies.get(tool, "")
        return path if path else None

    def apply_config_to_args(self, args: argparse.Namespace) -> argparse.Namespace:
        """Apply configuration defaults to parsed arguments."""
        if not self._loaded:
            self.load_config()

        # handle preset command (format determined from preset)
        if hasattr(args, "format_command") and args.format_command == "preset":
            if hasattr(args, "preset_name") and args.preset_name:
                # apply preset and get format for routing
                format_type = self.apply_preset_with_format(args, args.preset_name)
                # apply format-specific defaults
                self._apply_format_defaults(args, format_type)
            else:
                exit_application(
                    "Preset name is required when using 'preset' command.", EXIT_FAIL
                )
        else:
            # apply format specific defaults for direct format commands
            if hasattr(args, "format_command") and args.format_command:
                self._apply_format_defaults(args, args.format_command)

        # apply default bitrates if no bitrate specified
        self._apply_default_bitrate(args)

        return args

    def _apply_preset(
        self, args: argparse.Namespace, preset_name: str, include_format: bool = False
    ) -> None:
        """Apply preset configuration to arguments."""
        preset = self.get_preset(preset_name)
        if not preset:
            available = ", ".join(self.list_presets()) or "None"
            exit_application(
                f"Preset '{preset_name}' not found. Available: {available}", EXIT_FAIL
            )

        # apply preset values (CLI args take precedence)
        for key, value in preset.items():
            if key == "format" and not include_format:
                # format handled by subcommand, unless explicitly requested
                continue

            arg_name = key.replace("-", "_")
            if hasattr(args, arg_name):
                current_value = getattr(args, arg_name)
                if current_value is None or self._should_override(
                    arg_name, current_value
                ):
                    converted_value = self._convert_value(arg_name, value)
                    setattr(args, arg_name, converted_value)

    def apply_preset_with_format(
        self, args: argparse.Namespace, preset_name: str
    ) -> str:
        """Apply preset configuration including format, return the format for routing."""
        preset = self.get_preset(preset_name)
        if not preset:
            available = ", ".join(self.list_presets()) or "None"
            exit_application(
                f"Preset '{preset_name}' not found. Available: {available}", EXIT_FAIL
            )

        format_type = preset.get("format")
        if not format_type:
            exit_application(
                f"Preset '{preset_name}' does not specify a format. "
                f"Please add 'format = \"dd|ddp|ddp-bluray|atmos\"' to the preset.",
                EXIT_FAIL,
            )

        # set the format_command for routing
        setattr(args, "format_command", format_type)

        # apply all preset values with format-aware conversion
        self._apply_preset_with_format_context(args, preset_name, format_type)

        return format_type

    def _apply_preset_with_format_context(
        self, args: argparse.Namespace, preset_name: str, format_type: str
    ) -> None:
        """Apply preset configuration with format context for proper type conversion."""
        preset = self.get_preset(preset_name)
        if not preset:
            return

        # validate preset compatibility with format first
        self._validate_preset_format_compatibility(preset, format_type, preset_name)

        # apply preset values (CLI args take precedence)
        for key, value in preset.items():
            arg_name = key.replace("-", "_")
            if hasattr(args, arg_name):
                current_value = getattr(args, arg_name)
                if current_value is None or self._should_override(
                    arg_name, current_value
                ):
                    converted_value = self._convert_value_with_format(
                        arg_name, value, format_type
                    )
                    setattr(args, arg_name, converted_value)
            elif key != "format":  # format is special and handled elsewhere
                # check for common key naming mistakes and provide helpful suggestions
                self._suggest_correct_preset_key(key, preset_name, format_type)

    def _validate_preset_format_compatibility(
        self, preset: dict[str, Any], format_type: str, preset_name: str
    ) -> None:
        """Validate that all preset arguments are compatible with the detected format."""
        # define format-specific valid arguments
        format_specific_args = {
            "dd": {
                "valid": [
                    "format",
                    "channels",
                    "bitrate",
                    "drc_line_mode",
                    "drc_rf_mode",
                    "custom_dialnorm",
                    "metering_mode",
                    "dialogue_intelligence",
                    "speech_threshold",
                    "stereo_down_mix",
                    "lfe_lowpass_filter",
                    "surround_3db_attenuation",
                    "surround_90_degree_phase_shift",
                    "lt_rt_center",
                    "lt_rt_surround",
                    "lo_ro_center",
                    "lo_ro_surround",
                ],
                "invalid": ["atmos_mode", "thd_warp_mode", "no_bed_conform"],
            },
            "ddp": {
                "valid": [
                    "format",
                    "channels",
                    "bitrate",
                    "drc_line_mode",
                    "drc_rf_mode",
                    "custom_dialnorm",
                    "metering_mode",
                    "dialogue_intelligence",
                    "speech_threshold",
                    "stereo_down_mix",
                    "lfe_lowpass_filter",
                    "surround_3db_attenuation",
                    "surround_90_degree_phase_shift",
                    "lt_rt_center",
                    "lt_rt_surround",
                    "lo_ro_center",
                    "lo_ro_surround",
                ],
                "invalid": ["atmos_mode", "thd_warp_mode", "no_bed_conform"],
            },
            "ddp-bluray": {
                "valid": [
                    "format",
                    "channels",
                    "bitrate",
                    "drc_line_mode",
                    "drc_rf_mode",
                    "custom_dialnorm",
                    "metering_mode",
                    "dialogue_intelligence",
                    "speech_threshold",
                    "stereo_down_mix",
                    "lfe_lowpass_filter",
                    "surround_3db_attenuation",
                    "surround_90_degree_phase_shift",
                    "lt_rt_center",
                    "lt_rt_surround",
                    "lo_ro_center",
                    "lo_ro_surround",
                ],
                "invalid": ["atmos_mode", "thd_warp_mode", "no_bed_conform"],
            },
            "atmos": {
                "valid": [
                    "format",
                    "bitrate",
                    "drc_line_mode",
                    "drc_rf_mode",
                    "custom_dialnorm",
                    "metering_mode",
                    "dialogue_intelligence",
                    "speech_threshold",
                    "lt_rt_center",
                    "lt_rt_surround",
                    "lo_ro_center",
                    "lo_ro_surround",
                    "atmos_mode",
                    "thd_warp_mode",
                    "no_bed_conform",
                ],
                "invalid": [
                    "channels",
                    "stereo_down_mix",
                    "lfe_lowpass_filter",
                    "surround_3db_attenuation",
                    "surround_90_degree_phase_shift",
                ],
            },
        }

        format_rules = format_specific_args.get(format_type)
        if not format_rules:
            # unknown format, skip validation
            return

        # check for invalid arguments
        for key in preset.keys():
            if key in format_rules["invalid"]:
                exit_application(
                    f"Invalid argument '{key}' in preset '{preset_name}' for format '{format_type}'. "
                    f"Argument '{key}' is not supported by {format_type.upper()} encoder.",
                    EXIT_FAIL,
                )

    def _suggest_correct_preset_key(
        self, key: str, preset_name: str, format_type: str
    ) -> None:
        """Suggest correct preset key for common naming mistakes."""
        # common CLI-to-preset key mappings
        cli_to_preset = {
            "--bitrate": "bitrate",
            "--channels": "channels",
            "--atmos-mode": "atmos_mode",
            "--drc-line-mode": "drc_line_mode",
            "--drc-rf-mode": "drc_rf_mode",
            "--custom-dialnorm": "custom_dialnorm",
            "--metering-mode": "metering_mode",
            "--dialogue-intelligence": "dialogue_intelligence",
            "--speech-threshold": "speech_threshold",
            "--stereo-down-mix": "stereo_down_mix",
            "--thd-warp-mode": "thd_warp_mode",
            "--no-bed-conform": "no_bed_conform",
            "--track-index": "track_index",
            "--keep-temp": "keep_temp",
            "--temp-dir": "temp_dir",
            "--delay": "delay",
            "--output": "output",
        }

        # check if user used CLI argument name instead of preset key
        cli_equivalent = f"--{key.replace('_', '-')}"
        if cli_equivalent in cli_to_preset:
            correct_key = cli_to_preset[cli_equivalent]
            if correct_key != key:
                exit_application(
                    f"Unknown preset key '{key}' in preset '{preset_name}'. "
                    f"Did you mean '{correct_key}'? "
                    f"(CLI argument '{cli_equivalent}' maps to preset key '{correct_key}')",
                    EXIT_FAIL,
                )

        # check for reverse case - used correct key but it's not supported by this argument parser
        reverse_lookup = {v: k for k, v in cli_to_preset.items()}
        if key in reverse_lookup:
            cli_arg = reverse_lookup[key]
            exit_application(
                f"Preset key '{key}' in preset '{preset_name}' is not supported by format '{format_type}'. "
                f"This key corresponds to CLI argument '{cli_arg}'. "
                f"Check the format compatibility in the configuration file comments.",
                EXIT_FAIL,
            )
        else:
            # generic unknown key error
            exit_application(
                f"Unknown preset key '{key}' in preset '{preset_name}'. "
                f"Check the configuration file comments for valid preset keys and format compatibility.",
                EXIT_FAIL,
            )

    def _apply_format_defaults(
        self, args: argparse.Namespace, format_type: str
    ) -> None:
        """Apply format-specific defaults to arguments."""
        defaults = self.get_format_defaults(format_type)

        for key, value in defaults.items():
            arg_name = key.replace("-", "_")
            if hasattr(args, arg_name):
                current_value = getattr(args, arg_name)
                if current_value is None or self._should_override(
                    arg_name, current_value
                ):
                    converted_value = self._convert_value(arg_name, value)
                    setattr(args, arg_name, converted_value)

    def _apply_default_bitrate(self, args: argparse.Namespace) -> None:
        """Apply default bitrate based on format and channel configuration."""
        if not hasattr(args, "bitrate") or args.bitrate is not None:
            # bitrate already set by user
            return

        format_type = getattr(args, "format_command", None)
        if not format_type:
            return

        # For AUTO channels, we can't determine the bitrate until runtime.
        # The encoder will handle this case using the enum defaults.
        channels = getattr(args, "channels", None)
        if channels and hasattr(channels, "name") and channels.name.lower() == "auto":
            # let encoder handle AUTO channel selection
            return

        # determine channel configuration
        channel_config = self._get_channel_config_name(args, format_type)
        if not channel_config:
            return

        # get default bitrate for this combination
        default_bitrate = self.get_default_bitrate(format_type, channel_config)
        if default_bitrate:
            setattr(args, "bitrate", default_bitrate)
            logger.debug(
                f"Applied config default bitrate {default_bitrate} for {format_type}/{channel_config}"
            )

    def _get_channel_config_name(
        self, args: argparse.Namespace, format_type: str
    ) -> str | None:
        """Get the channel configuration name for bitrate lookup."""
        if format_type == "atmos":
            atmos_mode = getattr(args, "atmos_mode", None)
            if atmos_mode:
                return str(atmos_mode).lower()

        channels = getattr(args, "channels", None)
        if not channels:
            return None

        # convert enum to string name for lookup
        if hasattr(channels, "name"):
            channel_name = channels.name.lower()
        else:
            channel_name = str(channels).lower()

        # map enum names to config names
        channel_mapping = {
            "mono": "mono",
            "stereo": "stereo",
            "surround": "surround",
            "surroundex": "surroundex",
            "auto": None,  # can't determine default for auto
        }

        return channel_mapping.get(channel_name)

    def _should_override(self, arg_name: str, current_value: Any) -> bool:
        """Check if config value should override current CLI value."""
        # override if it's a default value that should be replaced
        if arg_name == "channels" and str(current_value).lower() == "auto":
            return True
        if arg_name == "bitrate" and current_value == 448:
            return True
        return False

    def _convert_value(self, arg_name: str, value: Any) -> Any:
        """Convert config value to appropriate type for argument."""
        try:
            if arg_name == "channels":
                # try DDP first, then DD, then Bluray
                value_upper = str(value).upper()
                try:
                    return DolbyDigitalPlusChannels[value_upper]
                except KeyError:
                    try:
                        return DolbyDigitalChannels[value_upper]
                    except KeyError:
                        return DolbyDigitalPlusBlurayChannels[value_upper]
            elif arg_name in ("drc_line_mode", "drc_rf_mode"):
                return DeeDRC[str(value).upper()]
            elif arg_name == "stereo_down_mix":
                return StereoDownmix[str(value).upper()]
            elif arg_name == "metering_mode":
                return MeteringMode[f"MODE_{str(value).upper()}"]
            elif arg_name == "atmos_mode":
                return AtmosMode[str(value).upper()]
            elif arg_name in (
                "dialogue_intelligence",
                "keep_temp",
                "no_bed_conform",
                "lfe_lowpass_filter",
                "surround_3db_attenuation",
                "surround_90_degree_phase_shift",
            ):
                return bool(value)
            elif arg_name in (
                "bitrate",
                "custom_dialnorm",
                "speech_threshold",
                "track_index",
            ):
                return int(value)
            else:
                return value
        except (KeyError, ValueError, AttributeError):
            # Use the same strict error handling as format-aware conversion
            self._handle_conversion_error(arg_name, value, "unknown")

    def _convert_value_with_format(
        self, arg_name: str, value: Any, format_type: str
    ) -> Any:
        """Convert config value to appropriate type for argument with format context."""
        try:
            if arg_name == "channels":
                # convert channels based on format type
                value_upper = str(value).upper()
                if format_type == "dd":
                    return DolbyDigitalChannels[value_upper]
                elif format_type == "ddp":
                    return DolbyDigitalPlusChannels[value_upper]
                elif format_type == "ddp-bluray":
                    return DolbyDigitalPlusBlurayChannels[value_upper]
                elif format_type == "atmos":
                    # atmos doesn't use channels argument, return as-is
                    return value
                else:
                    # fallback to original method
                    return self._convert_value(arg_name, value)
            else:
                # use standard conversion for non-channel arguments
                return self._convert_value(arg_name, value)
        except (KeyError, ValueError, AttributeError):
            # provide specific error messages for different validation failures
            self._handle_conversion_error(arg_name, value, format_type)

    def _handle_conversion_error(
        self, arg_name: str, value: Any, format_type: str
    ) -> None:
        """Handle configuration value conversion errors with helpful messages."""
        if arg_name == "channels":
            # get valid options based on format
            if format_type == "dd":
                valid_options = [e.name.lower() for e in DolbyDigitalChannels]
            elif format_type == "ddp":
                valid_options = [e.name.lower() for e in DolbyDigitalPlusChannels]
            elif format_type == "ddp-bluray":
                valid_options = [e.name.lower() for e in DolbyDigitalPlusBlurayChannels]
            else:
                valid_options = ["auto", "mono", "stereo", "surround"]

            exit_application(
                f"Invalid 'channels' value '{value}' for format '{format_type}'. "
                f"Valid options: {', '.join(valid_options)}",
                EXIT_FAIL,
            )
        elif arg_name in ("drc_line_mode", "drc_rf_mode"):
            valid_options = [e.name.lower() for e in DeeDRC]
            exit_application(
                f"Invalid '{arg_name}' value '{value}'. "
                f"Valid options: {', '.join(valid_options)}",
                EXIT_FAIL,
            )
        elif arg_name == "stereo_down_mix":
            valid_options = [e.name.lower() for e in StereoDownmix]
            exit_application(
                f"Invalid 'stereo_down_mix' value '{value}'. "
                f"Valid options: {', '.join(valid_options)}",
                EXIT_FAIL,
            )
        elif arg_name == "metering_mode":
            valid_options = ["1770_1", "1770_2", "1770_3", "leqa"]
            exit_application(
                f"Invalid 'metering_mode' value '{value}'. "
                f"Valid options: {', '.join(valid_options)}",
                EXIT_FAIL,
            )
        elif arg_name == "atmos_mode":
            valid_options = [e.name.lower() for e in AtmosMode]
            exit_application(
                f"Invalid 'atmos_mode' value '{value}'. "
                f"Valid options: {', '.join(valid_options)}",
                EXIT_FAIL,
            )
        else:
            # generic error for other validation failures
            exit_application(
                f"Invalid configuration value '{value}' for '{arg_name}'. "
                f"Please check the configuration file for correct format and values.",
                EXIT_FAIL,
            )

    def _merge_configs(
        self, base: dict[str, Any], update: dict[str, Any]
    ) -> dict[str, Any]:
        """Recursively merge configuration dictionaries."""
        result = base.copy()

        for key, value in update.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = self._merge_configs(result[key], value)
            else:
                result[key] = value

        return result

    def _create_default_config_with_comments(self) -> str:
        """Create a default config file with helpful comments from DEFAULT_CONFIG."""
        # create TOML document from DEFAULT_CONFIG
        doc = tomlkit.document()

        # add header comment
        doc.add(tomlkit.comment("DeeZy Configuration File"))
        doc.add(
            tomlkit.comment(
                "This file allows you to customize default settings and create presets"
            )
        )
        doc.add(tomlkit.nl())

        # dependencies section
        deps = tomlkit.table()
        deps.add(
            tomlkit.comment("Paths to required tools (leave empty for auto-detection)")
        )
        for key, value in DEFAULT_CONFIG["dependencies"].items():
            deps[key] = value
        doc["dependencies"] = deps
        doc.add(tomlkit.nl())

        # global defaults section
        global_defaults = tomlkit.table()
        global_defaults.add(tomlkit.comment("Settings applied to all encoding formats"))
        for key, value in DEFAULT_CONFIG["global_defaults"].items():
            global_defaults[key] = value
        doc["global_defaults"] = global_defaults
        doc.add(tomlkit.nl())

        # default bitrates section
        bitrates = tomlkit.table()
        bitrates.add(
            tomlkit.comment(
                "Customize default bitrates for each codec/channel combination"
            )
        )
        bitrates.add(tomlkit.comment("These are used when no --bitrate is specified"))
        doc["default_bitrates"] = bitrates
        doc.add(tomlkit.nl())

        # add bitrate subsections with comments
        for format_name, format_bitrates in DEFAULT_CONFIG["default_bitrates"].items():
            format_table = tomlkit.table()
            for channel, bitrate in format_bitrates.items():
                # add inline comments for clarity
                if format_name == "dd":
                    comments = {
                        "mono": "Dolby Digital 1.0",
                        "stereo": "Dolby Digital 2.0",
                        "surround": "Dolby Digital 5.1",
                    }
                elif format_name == "ddp":
                    comments = {
                        "mono": "Dolby Digital Plus 1.0",
                        "stereo": "Dolby Digital Plus 2.0",
                        "surround": "Dolby Digital Plus 5.1",
                        "surroundex": "Dolby Digital Plus 7.1",
                    }
                elif format_name == "ddp_bluray":
                    comments = {"surroundex": "Dolby Digital Plus Bluray 7.1"}
                elif format_name == "atmos":
                    comments = {
                        "streaming": "Dolby Atmos Streaming mode",
                        "bluray": "Dolby Atmos Bluray mode",
                    }
                else:
                    comments = {}

                item = tomlkit.item(bitrate)
                if channel in comments:
                    item.comment(comments[channel])
                format_table[channel] = item

            bitrates.add(format_name, format_table)

        doc.add(tomlkit.nl())

        # format defaults section
        format_defaults = tomlkit.table()
        format_defaults.add(
            tomlkit.comment("Format-specific settings (override global_defaults)")
        )
        doc["format_defaults"] = format_defaults
        doc.add(tomlkit.nl())

        for format_name, format_settings in DEFAULT_CONFIG["format_defaults"].items():
            format_table = tomlkit.table()
            for key, value in format_settings.items():
                # skip no_bed_conform if it's false (default value, can be omitted)
                if key == "no_bed_conform" and value is False:
                    continue # TODO: check if we need these checks for no conform?
                format_table[key] = value
            format_defaults.add(format_name, format_table)

        doc.add(tomlkit.nl())

        # presets section
        presets = tomlkit.table()
        presets.add(tomlkit.comment("Define custom presets for common workflows"))
        presets.add(
            tomlkit.comment("Usage: deezy encode preset --name streaming_ddp input.mkv")
        )
        presets.add(tomlkit.comment(""))
        presets.add(tomlkit.comment("PRESET KEY MAPPING (CLI argument → preset key):"))
        presets.add(tomlkit.comment("--bitrate → bitrate"))
        presets.add(tomlkit.comment("--channels → channels"))
        presets.add(tomlkit.comment("--atmos-mode → atmos_mode"))
        presets.add(tomlkit.comment("--drc-line-mode → drc_line_mode"))
        presets.add(tomlkit.comment("--drc-rf-mode → drc_rf_mode"))
        presets.add(tomlkit.comment("--custom-dialnorm → custom_dialnorm"))
        presets.add(tomlkit.comment("--metering-mode → metering_mode"))
        presets.add(tomlkit.comment("--dialogue-intelligence → dialogue_intelligence"))
        presets.add(tomlkit.comment("--speech-threshold → speech_threshold"))
        presets.add(tomlkit.comment("--stereo-down-mix → stereo_down_mix"))
        presets.add(tomlkit.comment("--thd-warp-mode → thd_warp_mode"))
        presets.add(tomlkit.comment("--no-bed-conform → no_bed_conform"))
        presets.add(tomlkit.comment("--track-index → track_index"))
        presets.add(tomlkit.comment("--keep-temp → keep_temp"))
        presets.add(tomlkit.comment("--temp-dir → temp_dir"))
        presets.add(tomlkit.comment("--delay → delay"))
        presets.add(tomlkit.comment("--output → output"))
        presets.add(tomlkit.comment(""))
        presets.add(tomlkit.comment("FORMAT-SPECIFIC COMPATIBILITY:"))
        presets.add(
            tomlkit.comment(
                "DD/DDP/DDP-Bluray: format, channels, bitrate, drc_*, metering_mode,"
            )
        )
        presets.add(
            tomlkit.comment(
                "                   dialogue_intelligence, speech_threshold, stereo_down_mix"
            )
        )
        presets.add(
            tomlkit.comment(
                "Atmos: format, bitrate, drc_*, metering_mode, dialogue_intelligence,"
            )
        )
        presets.add(
            tomlkit.comment(
                "       speech_threshold, atmos_mode, thd_warp_mode, no_bed_conform"
            )
        )
        doc["presets"] = presets
        doc.add(tomlkit.nl())

        for preset_name, preset_settings in DEFAULT_CONFIG["presets"].items():
            preset_table = tomlkit.table()
            for key, value in preset_settings.items():
                # skip no_bed_conform if it's false (default value, can be omitted)
                if key == "no_bed_conform" and value is False:
                    continue
                preset_table[key] = value
            presets.add(preset_name, preset_table)

        return tomlkit.dumps(doc)


def get_config_manager() -> ConfigManager:
    """Get the singleton configuration manager instance."""
    return ConfigManager()
