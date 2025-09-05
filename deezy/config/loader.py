from copy import deepcopy
from pathlib import Path
from typing import Any

import tomlkit
from tomlkit.exceptions import TOMLKitError

from deezy.config.defaults import DEFAULT_CONFIG, get_config_locations
from deezy.config.schema import ConfigSchema, ConfigValidationError


class ConfigLoader:
    """Loads and manages DeeZy configuration files."""

    __slots__ = ("_config", "_config_path")

    def __init__(self):
        self._config: dict[str, Any] | None = None
        self._config_path: Path | None = None

    def load_config(self, config_path: Path | None = None) -> dict[str, Any]:
        """Load configuration from file or use defaults.

        Args:
            config_path: Specific config file path, or None for auto-detection

        Returns:
            Loaded and validated configuration dictionary
        """
        if tomlkit is None:
            # if tomlkit is not available, return defaults
            return DEFAULT_CONFIG.copy()

        if config_path:
            config_paths = [config_path]
        else:
            config_paths = get_config_locations()

        # try to load from existing config files
        for path in config_paths:
            if path.exists() and path.is_file():
                try:
                    config = self._load_toml_file(path)
                    self._config_path = path
                    self._config = config
                    return config
                except Exception as e:
                    # log warning but continue to next path
                    print(f"Warning: Failed to load config from {path}: {e}")
                    continue

        # no config file found, use defaults
        self._config = DEFAULT_CONFIG.copy()
        return self._config

    def _load_toml_file(self, path: Path) -> dict[str, Any]:
        """Load and validate TOML configuration file.

        Args:
            path: Path to TOML config file

        Returns:
            Validated configuration dictionary

        Raises:
            ConfigValidationError: If file is invalid
        """
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw_config = tomlkit.load(f).unwrap()

            # merge with defaults to ensure all keys exist
            config = self._merge_with_defaults(raw_config)

            # validate the configuration
            validated_config = ConfigSchema.validate_config(config)

            return validated_config

        except TOMLKitError as e:
            raise ConfigValidationError(f"Invalid TOML syntax: {e}")
        except Exception as e:
            raise ConfigValidationError(f"Failed to load config: {e}")

    def _merge_with_defaults(self, user_config: dict[str, Any]) -> dict[str, Any]:
        """Merge user configuration with defaults.

        Args:
            user_config: User-provided configuration

        Returns:
            Merged configuration with defaults filled in
        """
        # start with defaults
        merged = deepcopy(DEFAULT_CONFIG)

        # recursively update with user config
        self._deep_update(merged, user_config)

        return merged

    def _deep_update(self, base: dict[str, Any], update: dict[str, Any]) -> None:
        """Recursively update nested dictionary.

        Args:
            base: Base dictionary to update
            update: Dictionary with updates
        """
        for key, value in update.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_update(base[key], value)
            else:
                base[key] = value

    def get_dependency_path(self, tool: str) -> str | None:
        """Get configured path for a dependency tool.

        Args:
            tool: Tool name ('ffmpeg', 'dee', 'truehd')

        Returns:
            Configured path or None if not set
        """
        if not self._config:
            return None

        deps = self._config.get("dependencies", {})
        path = deps.get(tool, "")
        return path if path else None

    def get_format_defaults(self, format_type: str) -> dict[str, Any]:
        """Get default settings for encoding format.

        Args:
            format_type: Format type ('dd' or 'ddp')

        Returns:
            Dictionary of default settings for the format
        """
        if not self._config:
            return {}

        defaults = self._config.get("defaults", {})
        global_defaults = defaults.get("global", {})
        format_defaults = defaults.get(format_type, {})

        # merge global and format-specific defaults
        merged = {**global_defaults, **format_defaults}
        return merged

    def get_preset(self, preset_name: str) -> dict[str, Any] | None:
        """Get configuration for a named preset.

        Args:
            preset_name: Name of the preset

        Returns:
            Preset configuration or None if not found
        """
        if not self._config:
            return None

        presets = self._config.get("presets", {})
        return presets.get(preset_name)

    def list_presets(self) -> list[str]:
        """Get list of available preset names.

        Returns:
            List of preset names
        """
        if not self._config:
            return []

        presets = self._config.get("presets", {})
        return list(presets.keys())

    @property
    def config_path(self) -> Path | None:
        """Get the path of the loaded configuration file."""
        return self._config_path

    @property
    def config(self) -> dict[str, Any] | None:
        """Get the loaded configuration dictionary."""
        return self._config
