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

        # handle presets first
        if hasattr(args, "preset") and args.preset:
            self._apply_preset(args, args.preset)

        # apply format specific defaults
        if hasattr(args, "format_command") and args.format_command:
            self._apply_format_defaults(args, args.format_command)

        # apply default bitrates if no bitrate specified
        self._apply_default_bitrate(args)

        return args

    def _apply_preset(self, args: argparse.Namespace, preset_name: str) -> None:
        """Apply preset configuration to arguments."""
        preset = self.get_preset(preset_name)
        if not preset:
            from deezy.utils.exit import EXIT_FAIL, exit_application

            available = ", ".join(self.list_presets()) or "None"
            exit_application(
                f"Preset '{preset_name}' not found. Available: {available}", EXIT_FAIL
            )

        # apply preset values (CLI args take precedence)
        for key, value in preset.items():
            if key == "format":
                # format handled by subcommand
                continue

            arg_name = key.replace("-", "_")
            if hasattr(args, arg_name):
                current_value = getattr(args, arg_name)
                if current_value is None or self._should_override(
                    arg_name, current_value
                ):
                    converted_value = self._convert_value(arg_name, value)
                    setattr(args, arg_name, converted_value)

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
            logger.warning(
                f"Failed to convert config value '{value}' for argument '{arg_name}'"
            )
            return value

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
                format_table[key] = value
            format_defaults.add(format_name, format_table)

        doc.add(tomlkit.nl())

        # [resets section
        presets = tomlkit.table()
        presets.add(tomlkit.comment("Define custom presets for common workflows"))
        presets.add(
            tomlkit.comment("Usage: deezy encode ddp --preset streaming input.mkv")
        )
        doc["presets"] = presets
        doc.add(tomlkit.nl())

        for preset_name, preset_settings in DEFAULT_CONFIG["presets"].items():
            preset_table = tomlkit.table()
            for key, value in preset_settings.items():
                preset_table[key] = value
            presets.add(preset_name, preset_table)

        return tomlkit.dumps(doc)


def get_config_manager() -> ConfigManager:
    """Get the singleton configuration manager instance."""
    return ConfigManager()
