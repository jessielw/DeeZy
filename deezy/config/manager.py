import sys
from pathlib import Path
from typing import Any

import oslex2
import tomlkit

from deezy.config.defaults import CONF_DEFAULT, get_default_config_path
from deezy.enums.codec_format import CodecFormat
from deezy.utils.exit import EXIT_FAIL, exit_application
from deezy.utils.logger import logger
from deezy.utils.utils import WORKING_DIRECTORY


class ConfigManager:
    """Simple configuration manager that handles presets and config loading."""

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
        # determine search order for config file when none is provided:
        # 1) current working directory (project/local config)
        # 2) user config directory (platformdirs recommended path)
        # 3) working directory beside the executable (bundled exe)
        if config_path is None:
            # first check cwd
            cwd_path = Path.cwd() / "deezy-conf.toml"
            user_path = Path(get_default_config_path())
            exe_path = Path(WORKING_DIRECTORY) / "deezy-conf.toml"

            candidates = [cwd_path, user_path, exe_path]
            found = None
            for p in candidates:
                try:
                    if p and p.exists():
                        found = p
                        break
                except Exception:
                    continue

            config_path = found
        else:
            config_path = Path(config_path)

        if config_path and config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    self.config.update(tomlkit.load(f))
                self.config_path = config_path
                logger.debug(f"loaded config from {config_path}")

                # validate config structure
                self._validate_config()
            except Exception as e:
                logger.warning(f"failed to load config: {e}")
                self.config.clear()
        else:
            logger.debug("no config file found, using defaults")
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
            exit_application("no presets defined in configuration.", EXIT_FAIL)

        preset_command = self.config["presets"].get(preset_name)
        if not preset_command:
            available = ", ".join(self.config["presets"].keys()) or "None"
            exit_application(
                f"preset '{preset_name}' not found. available: {available}", EXIT_FAIL
            )

        return preset_command

    def parse_preset_command(self, preset_name: str) -> list[str]:
        """Parse preset command string into arguments list."""
        preset_command = self.get_preset_command(preset_name)
        return oslex2.split(preset_command)

    def inject_preset_args(self, preset_name: str) -> None:
        """Inject preset arguments into sys.argv before argparse runs."""
        preset_args = self.parse_preset_command(preset_name)

        # find where to inject the preset args
        # we want to replace "preset --name preset_name" with the actual preset command
        try:
            preset_idx = sys.argv.index("preset")
            name_idx = sys.argv.index("--name", preset_idx)

            # remove "preset --name preset_name" (3 elements)
            del sys.argv[preset_idx : name_idx + 2]

            # skip the "encode" part from preset since we already have "encode" before "preset"
            if preset_args and preset_args[0] == "encode":
                preset_args = preset_args[1:]

            # insert preset args at the same position
            for i, arg in enumerate(preset_args):
                sys.argv.insert(preset_idx + i, arg)
            logger.debug(f"injected preset '{preset_name}': {' '.join(preset_args)}")
        except ValueError:
            # preset not found in args, this shouldn't happen
            logger.warning("could not find preset arguments to replace")

    def get_config_default(self, key: str) -> Any:
        """Get a config default value for an argument."""
        return self.config.get("global_defaults", {}).get(key)

    def get_dependency_path(self, tool: str) -> str:
        """Get dependency path from config."""
        return self.config.get("dependencies", {}).get(tool, "")

    def list_presets(self) -> list[str]:
        """List available presets."""
        return list(self.config.get("presets", {}).keys())

    def get_default_bitrate(
        self, format_command: str | CodecFormat, channels_or_mode: Any = None
    ) -> int | None:
        """Get default bitrate for a format and channel/mode configuration."""
        # convert enum to string if needed
        format_str = (
            format_command.value
            if isinstance(format_command, CodecFormat)
            else format_command
        )

        bitrates_config = self.config.get("default_bitrates", {})
        format_bitrates = bitrates_config.get(format_str, {})

        if not format_bitrates:
            return None

        # for Atmos, use the mode (streaming/bluray)
        if format_str == "atmos" and channels_or_mode:
            return format_bitrates.get(channels_or_mode)

        # for DD/DDP, use channel configuration
        if channels_or_mode:
            # map channel enums to config keys
            if hasattr(channels_or_mode, "name"):
                # use the enum name (AUTO, STEREO, SURROUND, etc.) converted to lowercase
                channels_str = channels_or_mode.name.lower()
            elif hasattr(channels_or_mode, "value"):
                channels_str = str(channels_or_mode.value).lower()
            else:
                channels_str = str(channels_or_mode).lower()

            return format_bitrates.get(channels_str)

        # no specific mode/channels provided, return None
        return None

    def generate_config(
        self, output_path: Path | None = None, overwrite: bool = False
    ) -> Path:
        """Generate a config file using the defaults template."""
        if output_path is None:
            output_path = Path(get_default_config_path())

        if output_path.exists() and not overwrite:
            raise FileExistsError(f"config file already exists: {output_path}")

        output_path.parent.mkdir(parents=True, exist_ok=True)

        # write the default config template directly
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(CONF_DEFAULT)

        logger.info(f"generated config file: {output_path}")
        return output_path

    def has_valid_config(self) -> bool:
        """Check if a valid config file is loaded."""
        return bool(self.config_path and self.config_path.exists())

    def validate_preset(self, preset_name: str) -> bool:
        """Basic validation that a preset exists and has a valid command."""
        try:
            command = self.get_preset_command(preset_name)
            args = oslex2.split(command)
            # basic validation - should start with 'encode' and have a format
            return len(args) >= 2 and args[0] == "encode"
        except Exception:
            return False

    def get_preset_info(self, preset_name: str) -> dict[str, str]:
        """Get basic info about a preset."""
        try:
            command = self.get_preset_command(preset_name)
            args = oslex2.split(command)
            info = {
                "name": preset_name,
                "command": command,
                "description": f"preset command: {command}",
            }
            if len(args) >= 2:
                info["format"] = args[1]  # e.g. 'ddp', 'dd', 'atmos'
            return info
        except Exception:
            return {
                "name": preset_name,
                "command": "invalid",
                "description": "invalid preset",
            }

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
