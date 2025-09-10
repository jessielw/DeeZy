import argparse
from pathlib import Path
import tempfile
from unittest.mock import patch

import pytest
import tomlkit

from deezy.config.defaults import DEFAULT_CONFIG
from deezy.config.manager import ConfigManager
from deezy.enums.ddp import DolbyDigitalPlusChannels
from deezy.enums.shared import DeeDRC, StereoDownmix


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset the ConfigManager singleton before each test."""
    # Reset the singleton for clean tests
    ConfigManager._instance = None
    ConfigManager._initialized = False
    yield
    # Clean up after test
    ConfigManager._instance = None
    ConfigManager._initialized = False


class TestConfigManagerSingleton:
    """Test singleton behavior of ConfigManager."""

    def test_singleton_same_instance(self):
        """Test that multiple calls return the same instance."""
        cm1 = ConfigManager()
        cm2 = ConfigManager()
        assert cm1 is cm2

    def test_singleton_initialization_once(self):
        """Test that initialization only happens once."""
        cm1 = ConfigManager()

        # Modify the config
        cm1.config["test_key"] = "test_value"

        # Get another instance
        cm2 = ConfigManager()

        # Should have the modified config (same instance)
        assert cm2.config["test_key"] == "test_value"
        assert cm1 is cm2


class TestConfigManagerLoading:
    """Test configuration loading functionality."""

    def test_load_config_defaults_when_no_file(self):
        """Test that defaults are used when no config file exists."""
        cm = ConfigManager()

        # Mock get_config_locations to return non-existent path
        with patch("deezy.config.manager.get_config_locations") as mock_locations:
            mock_locations.return_value = [Path("/nonexistent/deezy-conf.toml")]

            cm.load_config()

            assert cm._loaded is True
            assert cm.config_path is None
            assert cm.config == DEFAULT_CONFIG

    def test_load_config_from_file(self):
        """Test loading configuration from a TOML file."""
        # Create a temporary config file
        config_data = {
            "dependencies": {"ffmpeg": "/custom/ffmpeg"},
            "global_defaults": {"keep_temp": True},
            "default_bitrates": {"ddp": {"stereo": 256}},
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            tomlkit.dump(config_data, f)
            temp_path = Path(f.name)

        try:
            cm = ConfigManager()
            cm.load_config(temp_path)

            assert cm._loaded is True
            assert cm.config_path == temp_path

            # Check merged config
            assert cm.config["dependencies"]["ffmpeg"] == "/custom/ffmpeg"
            assert cm.config["global_defaults"]["keep_temp"] is True
            assert cm.config["default_bitrates"]["ddp"]["stereo"] == 256

            # Check that defaults are preserved for unspecified values
            assert "dee" in cm.config["dependencies"]
            assert "drc_line_mode" in cm.config["global_defaults"]

        finally:
            temp_path.unlink()

    def test_load_config_invalid_toml(self):
        """Test handling of invalid TOML files."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write("invalid toml content [[[")
            temp_path = Path(f.name)

        try:
            cm = ConfigManager()
            cm.load_config(temp_path)

            # Should fall back to defaults (loading continues even if one file fails)
            assert cm._loaded is True
            assert cm.config_path is None
            assert cm.config == DEFAULT_CONFIG

        finally:
            temp_path.unlink()


class TestConfigManagerGeneration:
    """Test configuration file generation."""

    def test_generate_config_default_location(self):
        """Test generating config at default location."""
        cm = ConfigManager()

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "deezy-conf.toml"

            with patch("deezy.config.manager.get_default_config_path") as mock_path:
                mock_path.return_value = output_path

                result_path = cm.generate_config()

                assert result_path == output_path
                assert output_path.exists()

                # Check that generated file is valid TOML
                with open(output_path, "rb") as f:
                    loaded_config = tomlkit.load(f)
                    assert "dependencies" in loaded_config
                    assert "default_bitrates" in loaded_config

    def test_generate_config_custom_path(self):
        """Test generating config at custom location."""
        cm = ConfigManager()

        with tempfile.TemporaryDirectory() as temp_dir:
            custom_path = Path(temp_dir) / "custom-config.toml"

            result_path = cm.generate_config(custom_path)

            assert result_path == custom_path
            assert custom_path.exists()

    def test_generate_config_file_exists_no_overwrite(self):
        """Test that generation fails when file exists and overwrite=False."""
        cm = ConfigManager()

        with tempfile.NamedTemporaryFile(suffix=".toml", delete=False) as f:
            existing_path = Path(f.name)

        try:
            with pytest.raises(FileExistsError):
                cm.generate_config(existing_path, overwrite=False)

        finally:
            existing_path.unlink()

    def test_generate_config_overwrite(self):
        """Test that generation succeeds with overwrite=True."""
        cm = ConfigManager()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write("# old content")
            existing_path = Path(f.name)

        try:
            result_path = cm.generate_config(existing_path, overwrite=True)

            assert result_path == existing_path

            # Check that file was overwritten
            content = existing_path.read_text()
            assert "DeeZy Configuration File" in content
            assert "# old content" not in content

        finally:
            existing_path.unlink()


class TestConfigManagerBitrates:
    """Test bitrate-related functionality."""

    def test_get_default_bitrate(self):
        """Test getting default bitrates for format/channel combinations."""
        cm = ConfigManager()
        cm.config = DEFAULT_CONFIG.copy()

        # Test existing combinations
        assert cm.get_default_bitrate("ddp", "stereo") == 128
        assert cm.get_default_bitrate("dd", "surround") == 448
        assert cm.get_default_bitrate("atmos", "streaming") == 448

        # Test non-existent combinations
        assert cm.get_default_bitrate("nonexistent", "format") is None
        assert cm.get_default_bitrate("ddp", "nonexistent") is None

    def test_get_configured_default_bitrate_with_config(self):
        """Test configured default bitrate when user has custom config."""
        cm = ConfigManager()
        cm.config = DEFAULT_CONFIG.copy()
        cm.config["default_bitrates"]["ddp"]["stereo"] = 256

        # Mock channels enum
        class MockChannels:
            name = "STEREO"

        result = cm.get_configured_default_bitrate("ddp", MockChannels(), 128)
        assert result == 256  # Should use configured value

    def test_get_configured_default_bitrate_fallback(self):
        """Test fallback to enum default when no config exists."""
        cm = ConfigManager()
        cm.config = DEFAULT_CONFIG.copy()

        # Mock channels enum for non-existent config
        class MockChannels:
            name = "NONEXISTENT"

        result = cm.get_configured_default_bitrate("ddp", MockChannels(), 128)
        assert result == 128  # Should use enum default


class TestConfigManagerPresets:
    """Test preset functionality."""

    def test_get_preset_existing(self):
        """Test getting an existing preset."""
        cm = ConfigManager()
        cm.config = DEFAULT_CONFIG.copy()

        preset = cm.get_preset("streaming_ddp")
        assert preset is not None
        assert preset["format"] == "ddp"
        assert preset["channels"] == "surround"

    def test_get_preset_nonexistent(self):
        """Test getting a non-existent preset."""
        cm = ConfigManager()
        cm.config = DEFAULT_CONFIG.copy()

        preset = cm.get_preset("nonexistent")
        assert preset is None

    def test_list_presets(self):
        """Test listing available presets."""
        cm = ConfigManager()
        cm.config = DEFAULT_CONFIG.copy()

        presets = cm.list_presets()
        assert "streaming_ddp" in presets
        assert "bluray_atmos" in presets
        assert "quick_stereo" in presets


class TestConfigManagerArgumentIntegration:
    """Test integration with argparse arguments."""

    def test_apply_config_to_args_preset_command(self):
        """Test applying preset configuration with new preset command."""
        cm = ConfigManager()
        cm.config = DEFAULT_CONFIG.copy()
        cm._loaded = True

        # Create args namespace with new preset command
        args = argparse.Namespace()
        args.format_command = "preset"
        args.preset_name = "streaming_ddp"
        args.bitrate = None
        args.channels = None

        result_args = cm.apply_config_to_args(args)

        # Should apply preset values and set format_command from preset
        assert result_args.format_command == "ddp"  # Set from preset format
        assert result_args.bitrate == 448
        assert result_args.channels == DolbyDigitalPlusChannels.SURROUND

    def test_apply_config_to_args_format_defaults(self):
        """Test applying format-specific defaults."""
        cm = ConfigManager()
        cm.config = DEFAULT_CONFIG.copy()
        cm._loaded = True

        # Create args namespace
        args = argparse.Namespace()
        args.preset = None
        args.format_command = "ddp"
        args.bitrate = None
        args.channels = None
        args.lfe_lowpass_filter = None

        result_args = cm.apply_config_to_args(args)

        # Should apply format defaults
        assert result_args.lfe_lowpass_filter is True

    def test_apply_config_to_args_default_bitrate(self):
        """Test applying default bitrate based on channel configuration."""
        cm = ConfigManager()
        cm.config = DEFAULT_CONFIG.copy()
        cm._loaded = True

        # Create args namespace with specific channel config
        args = argparse.Namespace()
        args.preset = None
        args.format_command = "ddp"
        args.bitrate = None
        args.channels = DolbyDigitalPlusChannels.STEREO

        result_args = cm.apply_config_to_args(args)

        # Should apply default bitrate for DDP stereo
        expected_bitrate = DEFAULT_CONFIG["default_bitrates"]["ddp"]["stereo"]
        assert result_args.bitrate == expected_bitrate

    def test_apply_config_preserves_cli_args(self):
        """Test that CLI arguments take precedence over config."""
        cm = ConfigManager()
        cm.config = DEFAULT_CONFIG.copy()
        cm._loaded = True

        # Create args namespace with explicit CLI values using new preset command
        args = argparse.Namespace()
        args.format_command = "preset"
        args.preset_name = "streaming_ddp"  # This has bitrate=448
        args.bitrate = 320  # Explicit CLI value
        args.channels = None

        result_args = cm.apply_config_to_args(args)

        # CLI bitrate should be preserved
        assert result_args.bitrate == 320

    def test_apply_preset_with_format_validation_error(self):
        """Test format compatibility validation for presets."""
        cm = ConfigManager()
        cm.config = DEFAULT_CONFIG.copy()
        cm._loaded = True

        # Add invalid preset with atmos-specific args for ddp format
        cm.config["presets"]["invalid_preset"] = {
            "format": "ddp",
            "channels": "surround",
            "bitrate": 448,
            "atmos_mode": "streaming",  # Invalid for DDP
        }

        args = argparse.Namespace()
        args.format_command = "preset"
        args.preset_name = "invalid_preset"
        args.channels = None
        args.atmos_mode = None

        # Should raise exit_application due to validation error
        with pytest.raises(SystemExit):
            cm.apply_config_to_args(args)

    def test_suggest_correct_preset_key_hyphen_error(self):
        """Test preset key suggestion for hyphen vs underscore mistakes."""
        cm = ConfigManager()
        cm.config = DEFAULT_CONFIG.copy()
        cm._loaded = True

        # Add preset with unknown key that will trigger suggestion
        cm.config["presets"]["bad_preset"] = {
            "format": "ddp",
            "channels": "surround",
            "unknown_key": 5,  # This won't match hasattr, will trigger suggestion
        }

        args = argparse.Namespace()
        args.format_command = "preset"
        args.preset_name = "bad_preset"
        args.channels = None

        # Should raise exit_application with helpful suggestion
        with pytest.raises(SystemExit):
            cm.apply_config_to_args(args)


class TestConfigManagerConversion:
    """Test value conversion functionality."""

    def test_convert_enum_values(self):
        """Test conversion of enum values from config strings."""
        cm = ConfigManager()

        # Test DRC conversion
        result = cm._convert_value("drc_line_mode", "film_light")
        assert result == DeeDRC.FILM_LIGHT

        # Test stereo downmix conversion
        result = cm._convert_value("stereo_down_mix", "loro")
        assert result == StereoDownmix.LORO

        # Test channels conversion (DDP)
        result = cm._convert_value("channels", "stereo")
        assert result == DolbyDigitalPlusChannels.STEREO

    def test_convert_value_with_format_context(self):
        """Test format-aware value conversion."""
        cm = ConfigManager()

        # Test DDP channels conversion
        result = cm._convert_value_with_format("channels", "stereo", "ddp")
        assert result == DolbyDigitalPlusChannels.STEREO

        # Test DD channels conversion - should use DD enum
        from deezy.enums.dd import DolbyDigitalChannels
        result = cm._convert_value_with_format("channels", "surround", "dd")
        assert result == DolbyDigitalChannels.SURROUND

        # Test atmos channels - should pass through as-is
        result = cm._convert_value_with_format("channels", "auto", "atmos")
        assert result == "auto"

    def test_convert_boolean_values(self):
        """Test conversion of boolean values."""
        cm = ConfigManager()

        result = cm._convert_value("keep_temp", True)
        assert result is True

        result = cm._convert_value("dialogue_intelligence", False)
        assert result is False

    def test_convert_integer_values(self):
        """Test conversion of integer values."""
        cm = ConfigManager()

        result = cm._convert_value("bitrate", "320")
        assert result == 320

        result = cm._convert_value("track_index", "1")
        assert result == 1

    def test_convert_invalid_values(self):
        """Test handling of invalid conversion values."""
        cm = ConfigManager()

        # Invalid enum value should raise SystemExit via exit_application
        with pytest.raises(SystemExit):
            cm._convert_value("drc_line_mode", "invalid_mode")


class TestConfigManagerMerging:
    """Test configuration merging functionality."""

    def test_merge_configs_simple(self):
        """Test merging simple key-value pairs."""
        cm = ConfigManager()

        base = {"key1": "value1", "key2": "value2"}
        update = {"key2": "updated", "key3": "new"}

        result = cm._merge_configs(base, update)

        assert result["key1"] == "value1"  # Preserved
        assert result["key2"] == "updated"  # Updated
        assert result["key3"] == "new"  # Added

    def test_merge_configs_nested(self):
        """Test merging nested dictionaries."""
        cm = ConfigManager()

        base = {"section1": {"a": 1, "b": 2}, "section2": {"c": 3}}
        update = {"section1": {"b": 20, "d": 4}, "section3": {"e": 5}}

        result = cm._merge_configs(base, update)

        assert result["section1"]["a"] == 1  # Preserved
        assert result["section1"]["b"] == 20  # Updated
        assert result["section1"]["d"] == 4  # Added
        assert result["section2"]["c"] == 3  # Preserved
        assert result["section3"]["e"] == 5  # Added


if __name__ == "__main__":
    pytest.main([__file__])
