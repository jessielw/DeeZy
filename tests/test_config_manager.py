import argparse
from pathlib import Path
import tempfile
from unittest.mock import patch

import pytest
import tomlkit

from deezy.config.manager import ConfigManager, get_config_manager
from deezy.enums.dd import DolbyDigitalChannels
from deezy.enums.ddp import DolbyDigitalPlusChannels
from deezy.enums.ddp_bluray import DolbyDigitalPlusBlurayChannels
from deezy.enums.shared import MeteringMode


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

    def test_get_instance_method(self):
        """Test the class method for getting instance."""
        cm1 = ConfigManager.get_instance()
        cm2 = ConfigManager.get_instance()
        assert cm1 is cm2

    def test_get_config_manager_function(self):
        """Test the module-level function for getting config manager."""
        cm1 = get_config_manager()
        cm2 = get_config_manager()
        assert cm1 is cm2


class TestConfigManagerLoading:
    """Test configuration loading functionality."""

    def test_load_config_nonexistent_file(self):
        """Test loading when config file doesn't exist."""
        cm = ConfigManager()

        # Try to load from non-existent path
        cm.load_config(Path("/nonexistent/deezy-conf.toml"))

        # Should have empty config and no config_path
        assert cm.config == {}
        assert cm.config_path is None

    def test_load_config_from_file(self):
        """Test loading configuration from a TOML file."""
        # Create a temporary config file
        config_data = {
            "dependencies": {"ffmpeg": "/custom/ffmpeg"},
            "global_defaults": {"keep_temp": True},
            "default_bitrates": {"ddp": {"stereo": 256}},
            "presets": {"test_preset": "encode ddp --bitrate 320"},
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            tomlkit.dump(config_data, f)
            temp_path = Path(f.name)

        try:
            cm = ConfigManager()
            cm.load_config(temp_path)

            # Check config is loaded correctly
            assert cm.config_path == temp_path
            assert cm.config["dependencies"]["ffmpeg"] == "/custom/ffmpeg"
            assert cm.config["global_defaults"]["keep_temp"] is True
            assert cm.config["default_bitrates"]["ddp"]["stereo"] == 256
            assert cm.config["presets"]["test_preset"] == "encode ddp --bitrate 320"

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

            # Should have empty config due to parsing error
            assert cm.config == {}
            assert cm.config_path is None

        finally:
            temp_path.unlink()

    def test_validate_config_structure(self):
        """Test that _validate_config ensures required sections exist."""
        cm = ConfigManager()
        cm.config = {"some_section": "value"}

        cm._validate_config()

        # Should have all required sections
        assert "presets" in cm.config
        assert "global_defaults" in cm.config
        assert "default_bitrates" in cm.config
        assert "dependencies" in cm.config


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

                # Check that generated file contains expected content
                content = output_path.read_text()
                assert "DeeZy Configuration File" in content
                assert "[dependencies]" in content
                assert "[global_defaults]" in content

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


class TestConfigManagerPresets:
    """Test preset functionality."""

    def test_get_preset_command_existing(self):
        """Test getting command for an existing preset."""
        cm = ConfigManager()
        cm.config = {
            "presets": {"streaming_ddp": "encode ddp --channels surround --bitrate 448"}
        }

        command = cm.get_preset_command("streaming_ddp")
        assert command == "encode ddp --channels surround --bitrate 448"

    def test_get_preset_command_nonexistent(self):
        """Test getting command for non-existent preset raises SystemExit."""
        cm = ConfigManager()
        cm.config = {"presets": {"existing": "encode dd"}}

        with pytest.raises(SystemExit):
            cm.get_preset_command("nonexistent")

    def test_parse_preset_command(self):
        """Test parsing preset command into arguments list."""
        cm = ConfigManager()
        cm.config = {
            "presets": {
                "test_preset": "encode ddp --channels 6 --bitrate 448 --keep-temp"
            }
        }

        args = cm.parse_preset_command("test_preset")
        expected = [
            "encode",
            "ddp",
            "--channels",
            "6",
            "--bitrate",
            "448",
            "--keep-temp",
        ]
        assert args == expected

    def test_list_presets(self):
        """Test listing available presets."""
        cm = ConfigManager()
        cm.config = {
            "presets": {
                "streaming_ddp": "encode ddp --channels surround",
                "bluray_atmos": "encode atmos --atmos-mode bluray",
                "quick_stereo": "encode ddp --channels stereo",
            }
        }

        presets = cm.list_presets()
        assert set(presets) == {"streaming_ddp", "bluray_atmos", "quick_stereo"}

    def test_list_presets_empty(self):
        """Test listing presets when none exist."""
        cm = ConfigManager()
        cm.config = {}

        presets = cm.list_presets()
        assert presets == []

    def test_get_preset_info(self):
        """Test getting preset information."""
        cm = ConfigManager()
        cm.config = {
            "presets": {"test_preset": "encode ddp --channels surround --bitrate 448"}
        }

        info = cm.get_preset_info("test_preset")
        assert info["name"] == "test_preset"
        assert info["command"] == "encode ddp --channels surround --bitrate 448"
        assert info["format"] == "ddp"
        assert "Preset command:" in info["description"]

    def test_validate_preset_valid(self):
        """Test validating a well-formed preset."""
        cm = ConfigManager()
        cm.config = {
            "presets": {"valid_preset": "encode ddp --channels surround --bitrate 448"}
        }

        assert cm.validate_preset("valid_preset") is True

    def test_validate_preset_invalid_format(self):
        """Test validating preset with invalid format."""
        cm = ConfigManager()
        cm.config = {
            "presets": {"invalid_preset": "encode invalid_format --channels surround"}
        }

        assert cm.validate_preset("invalid_preset") is False

    def test_validate_preset_short_command(self):
        """Test validating preset with too short command."""
        cm = ConfigManager()
        cm.config = {"presets": {"short_preset": "encode"}}

        assert cm.validate_preset("short_preset") is False


class TestConfigManagerBitrates:
    """Test bitrate-related functionality."""

    def test_get_default_bitrate_existing(self):
        """Test getting default bitrate for existing format/channel combination."""
        cm = ConfigManager()
        cm.config = {
            "default_bitrates": {
                "ddp": {"stereo": 128, "surround": 192},
                "dd": {"surround": 448},
            }
        }

        assert cm.get_default_bitrate("ddp", "stereo") == 128
        assert cm.get_default_bitrate("ddp", "surround") == 192
        assert cm.get_default_bitrate("dd", "surround") == 448

    def test_get_default_bitrate_nonexistent(self):
        """Test getting default bitrate for non-existent combinations."""
        cm = ConfigManager()
        cm.config = {"default_bitrates": {"ddp": {"stereo": 128}}}

        assert cm.get_default_bitrate("nonexistent", "format") is None
        assert cm.get_default_bitrate("ddp", "nonexistent") is None


class TestConfigManagerArgumentApplication:
    """Test applying configuration to arguments."""

    def test_apply_global_defaults_no_cli_args(self):
        """Test applying global defaults when no CLI args present."""
        cm = ConfigManager()
        cm.config = {
            "global_defaults": {"keep_temp": True, "drc_line_mode": "music_standard"}
        }

        args = argparse.Namespace()
        cm._apply_global_defaults(args)

        assert args.keep_temp is True
        assert args.drc_line_mode == "music_standard"

    def test_apply_global_defaults_with_cli_args(self):
        """Test that CLI args are preserved over config defaults."""
        cm = ConfigManager()
        cm.config = {
            "global_defaults": {"keep_temp": True, "drc_line_mode": "music_standard"}
        }

        args = argparse.Namespace()
        args.keep_temp = False  # CLI value should be preserved
        cm._apply_global_defaults(args)

        assert args.keep_temp is False  # CLI value preserved
        assert args.drc_line_mode == "music_standard"  # Config value applied

    def test_apply_format_defaults_channels(self):
        """Test applying format-specific channel defaults."""
        cm = ConfigManager()
        cm.config = {}

        # Test DD format
        args = argparse.Namespace()
        cm._apply_format_defaults(args, "dd")
        assert args.channels == DolbyDigitalChannels.AUTO

        # Test DDP format
        args = argparse.Namespace()
        cm._apply_format_defaults(args, "ddp")
        assert args.channels == DolbyDigitalPlusChannels.AUTO

        # Test DDP-BluRay format
        args = argparse.Namespace()
        cm._apply_format_defaults(args, "ddp-bluray")
        assert args.channels == DolbyDigitalPlusBlurayChannels.SURROUNDEX

    def test_apply_format_defaults_metering_mode(self):
        """Test applying format-specific metering mode defaults."""
        cm = ConfigManager()
        cm.config = {}

        # Test Atmos format (should get 1770-4)
        args = argparse.Namespace()
        cm._apply_format_defaults(args, "atmos")
        assert args.metering_mode == MeteringMode.MODE_1770_4

        # Test DD format (should get 1770-3)
        args = argparse.Namespace()
        cm._apply_format_defaults(args, "dd")
        assert args.metering_mode == MeteringMode.MODE_1770_3

        # Test DDP format (should get 1770-3)
        args = argparse.Namespace()
        cm._apply_format_defaults(args, "ddp")
        assert args.metering_mode == MeteringMode.MODE_1770_3

    def test_apply_default_bitrate(self):
        """Test applying default bitrate based on format and channels."""
        cm = ConfigManager()
        cm.config = {"default_bitrates": {"ddp": {"stereo": 128, "surround": 192}}}

        # Test with enum channels
        args = argparse.Namespace()
        args.bitrate = None
        args.format_command = "ddp"
        args.channels = DolbyDigitalPlusChannels.STEREO
        cm._apply_default_bitrate(args)
        assert args.bitrate == 128

        # Test with string channels
        args = argparse.Namespace()
        args.bitrate = None
        args.format_command = "ddp"
        args.channels = "surround"
        cm._apply_default_bitrate(args)
        assert args.bitrate == 192

    def test_apply_defaults_to_args_integration(self):
        """Test the full apply_defaults_to_args method."""
        cm = ConfigManager()
        cm.config = {
            "global_defaults": {"keep_temp": True, "drc_line_mode": "music_standard"},
            "default_bitrates": {
                "ddp": {
                    "auto": 128  # Use 'auto' to match the enum name conversion
                }
            },
        }

        args = argparse.Namespace()
        args.format_command = "ddp"
        args.bitrate = None
        cm.apply_defaults_to_args(args)

        # Should have global defaults
        assert args.keep_temp is True
        assert args.drc_line_mode == "music_standard"

        # Should have format-specific defaults
        assert args.channels == DolbyDigitalPlusChannels.AUTO
        assert args.metering_mode == MeteringMode.MODE_1770_3

        # Should have bitrate applied based on AUTO channels
        assert args.bitrate == 128


class TestConfigManagerUtilities:
    """Test utility methods."""

    def test_get_dependencies_paths(self):
        """Test getting dependency paths."""
        cm = ConfigManager()
        cm.config = {
            "dependencies": {
                "ffmpeg": "/usr/bin/ffmpeg",
                "dee": "/opt/dee/dee",
                "truehd": "",
            }
        }

        deps = cm.get_dependencies_paths()
        assert deps["ffmpeg"] == "/usr/bin/ffmpeg"
        assert deps["dee"] == "/opt/dee/dee"
        assert deps["truehd"] == ""

    def test_get_dependencies_paths_empty(self):
        """Test getting dependency paths when none configured."""
        cm = ConfigManager()
        cm.config = {}

        deps = cm.get_dependencies_paths()
        assert deps == {}

    def test_has_valid_config_true(self):
        """Test has_valid_config returns True when config file exists."""
        cm = ConfigManager()

        with tempfile.NamedTemporaryFile(suffix=".toml", delete=False) as f:
            temp_path = Path(f.name)

        try:
            cm.config_path = temp_path
            assert cm.has_valid_config() is True
        finally:
            temp_path.unlink()

    def test_has_valid_config_false(self):
        """Test has_valid_config returns False when no config or file doesn't exist."""
        cm = ConfigManager()

        # No config path set
        cm.config_path = None
        assert cm.has_valid_config() is False

        # Non-existent config path
        cm.config_path = Path("/nonexistent/config.toml")
        assert cm.has_valid_config() is False


if __name__ == "__main__":
    pytest.main([__file__])
