"""Configuration integration for DeeZy CLI."""

import argparse
from pathlib import Path
from typing import Any, Dict, Optional

from deezy.enums.dd import DolbyDigitalChannels
from deezy.enums.ddp import DolbyDigitalPlusChannels
from deezy.enums.shared import DeeDRC, ProgressMode, StereoDownmix

from .loader import ConfigLoader
from .generator import ConfigGenerator


class ConfigIntegration:
    """Integrates configuration system with CLI argument parsing."""
    
    def __init__(self):
        self.loader = ConfigLoader()
        self._config_loaded = False
    
    def load_config(self, config_path: Optional[Path] = None) -> None:
        """Load configuration file.
        
        Args:
            config_path: Specific config file path, or None for auto-detection
        """
        self.loader.load_config(config_path)
        self._config_loaded = True
    
    def apply_config_defaults(self, parser: argparse.ArgumentParser) -> None:
        """Apply configuration defaults to argument parser.
        
        Args:
            parser: ArgumentParser to modify with config defaults
        """
        if not self._config_loaded:
            self.load_config()
        
        # This would be called after parser setup but before parsing
        # For now, we'll handle defaults in merge_args_with_config
        pass
    
    def merge_args_with_config(self, args: argparse.Namespace, 
                             format_type: Optional[str] = None) -> argparse.Namespace:
        """Merge CLI arguments with configuration defaults.
        
        Priority: CLI args > Config file > Built-in defaults
        
        Args:
            args: Parsed CLI arguments
            format_type: Encoding format ('dd' or 'ddp')
            
        Returns:
            Updated arguments namespace with config defaults applied
        """
        if not self._config_loaded:
            self.load_config()
        
        # Get defaults for the format
        if format_type:
            defaults = self.loader.get_format_defaults(format_type)
        else:
            defaults = self.loader.get_format_defaults("global")
        
        # Apply defaults where CLI args are not set or are default values
        self._apply_dependency_defaults(args)
        self._apply_encoding_defaults(args, defaults)
        
        return args
    
    def get_dependency_path(self, tool: str) -> Optional[str]:
        """Get configured dependency path.
        
        Args:
            tool: Tool name ('ffmpeg', 'dee', 'truehd')
            
        Returns:
            Configured path or None if not set
        """
        if not self._config_loaded:
            self.load_config()
        
        return self.loader.get_dependency_path(tool)
    
    def generate_config(self, output_path: Optional[Path] = None,
                       from_args: Optional[argparse.Namespace] = None,
                       overwrite: bool = False) -> Path:
        """Generate a configuration file.
        
        Args:
            output_path: Where to save config, or None for default location
            from_args: CLI args to use as defaults, or None for built-in defaults
            overwrite: Whether to overwrite existing files
            
        Returns:
            Path where config was saved
        """
        if from_args:
            return ConfigGenerator.generate_config_from_args(
                from_args, output_path, overwrite
            )
        else:
            return ConfigGenerator.generate_default_config(output_path, overwrite)
    
    def _apply_dependency_defaults(self, args: argparse.Namespace) -> None:
        """Apply dependency path defaults from config.
        
        Args:
            args: Arguments namespace to update
        """
        # Only apply if CLI arg was not provided
        for tool in ['ffmpeg', 'dee', 'truehd']:
            if hasattr(args, tool):
                cli_value = getattr(args, tool)
                if not cli_value:  # Not provided via CLI
                    config_value = self.loader.get_dependency_path(tool)
                    if config_value:
                        setattr(args, tool, config_value)
    
    def _apply_encoding_defaults(self, args: argparse.Namespace, 
                               defaults: Dict[str, Any]) -> None:
        """Apply encoding defaults from config.
        
        Args:
            args: Arguments namespace to update
            defaults: Default values from config
        """
        # Map config keys to argument names
        key_mapping = {
            'progress_mode': ('progress_mode', self._convert_progress_mode),
            'keep_temp': ('keep_temp', bool),
            'temp_dir': ('temp_dir', str),
            'track_index': ('track_index', int),
            'channels': ('channels', self._convert_channels),
            'bitrate': ('bitrate', int),
            'drc': ('dynamic_range_compression', self._convert_drc),
            'stereo_down_mix': ('stereo_down_mix', self._convert_stereo_mix),
            'normalize': ('normalize', bool),
            'atmos': ('atmos', bool),
            'no_bed_conform': ('no_bed_conform', bool),
        }
        
        for config_key, (arg_key, converter) in key_mapping.items():
            if config_key in defaults and hasattr(args, arg_key):
                cli_value = getattr(args, arg_key)
                
                # Apply default if CLI value is None or default value
                if self._should_apply_default(cli_value, arg_key):
                    try:
                        converted_value = converter(defaults[config_key])
                        setattr(args, arg_key, converted_value)
                    except (ValueError, KeyError):
                        # Skip invalid config values
                        pass
    
    def _should_apply_default(self, cli_value: Any, arg_key: str) -> bool:
        """Check if config default should be applied.
        
        Args:
            cli_value: Value from CLI
            arg_key: Argument key name
            
        Returns:
            True if default should be applied
        """
        if cli_value is None:
            return True
        
        # Check if it's a default value that should be overridden
        # This is format-specific logic
        if arg_key == 'bitrate' and cli_value == 448:  # Default bitrate
            return True
        
        return False
    
    def _convert_progress_mode(self, value: str) -> ProgressMode:
        """Convert string to ProgressMode enum."""
        return ProgressMode[value.upper()]
    
    def _convert_channels(self, value: str) -> Any:
        """Convert string to appropriate channels enum."""
        # Try DDP channels first, then DD channels
        try:
            return DolbyDigitalPlusChannels[value.upper()]
        except KeyError:
            return DolbyDigitalChannels[value.upper()]
    
    def _convert_drc(self, value: str) -> DeeDRC:
        """Convert string to DeeDRC enum."""
        return DeeDRC[value.upper()]
    
    def _convert_stereo_mix(self, value: str) -> StereoDownmix:
        """Convert string to StereoDownmix enum."""
        return StereoDownmix[value.upper()]


# Global config instance
_config_integration: Optional[ConfigIntegration] = None


def get_config_integration() -> ConfigIntegration:
    """Get the global configuration integration instance."""
    global _config_integration
    if _config_integration is None:
        _config_integration = ConfigIntegration()
    return _config_integration
