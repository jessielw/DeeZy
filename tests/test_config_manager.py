import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import tomlkit

from deezy.config.manager import ConfigManager, get_config_manager


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
        assert (
            "preset command:" in info["description"]
        )  # lowercase 'p' to match actual output

    def test_validate_preset_valid(self):
        """Test validating a well-formed preset."""
        cm = ConfigManager()
        cm.config = {
            "presets": {"valid_preset": "encode ddp --channels surround --bitrate 448"}
        }

        assert cm.validate_preset("valid_preset") is True

    def test_validate_preset_invalid_format(self):
        """Test validating preset with invalid format - basic validation only checks structure."""
        cm = ConfigManager()
        cm.config = {
            "presets": {"invalid_preset": "encode invalid_format --channels surround"}
        }

        # Basic validation only checks structure (encode + format), not format validity
        assert cm.validate_preset("invalid_preset") is True

    def test_validate_preset_short_command(self):
        """Test validating preset with too short command."""
        cm = ConfigManager()
        cm.config = {"presets": {"short_preset": "encode"}}

        assert cm.validate_preset("short_preset") is False


class TestConfigManagerUtilities:
    """Test utility methods."""

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
