from configparser import ConfigParser
from pathlib import Path
from packages import custom_exit, exit_fail

config_file = "deeaw_config.ini"


def create_config():
    """Create parameters at launch"""
    if not Path(config_file).is_file():
        print(
            "Config created beside deeaw.exe, you can modify dependency paths inside."
        )

    try:
        with open(config_file, "w") as config_file_handle:
            config = ConfigParser()
            config.read(config_file)

            if not config.has_section("tool_paths"):
                config.add_section("tool_paths")

            for tool_name in ["ffmpeg", "mkvextract", "dee", "gst_launch"]:
                if not config.has_option("tool_paths", tool_name):
                    config.set("tool_paths", tool_name, "")

            config.write(config_file_handle)
    except Exception as e:
        custom_exit(f"Error while creating the config file: {e}", exit_fail)


def update_config(section: str, option: str, value: str):
    """Update the config file with the given section, option, and value.

    Args:
        section (str): The section of the config file to update.
        option (str): The option to update in the specified section.
        value (str): The new value to set for the specified option.
    """
    config_parser = ConfigParser()
    try:
        with open(config_file, "r") as cfg_file:
            config_parser.read_file(cfg_file)
    except FileNotFoundError:
        config_parser.add_section(section)
    except Exception as e:
        custom_exit(f"Error while reading the config file: {e}", exit_fail)

    if not config_parser.has_section(section):
        config_parser.add_section(section)

    if config_parser.has_option(section, option):
        current_value = config_parser.get(section, option)
        if current_value == value:
            return

    config_parser.set(section, option, value)
    try:
        with open(config_file, "w") as cfg_file:
            config_parser.write(cfg_file)
    except Exception as e:
        custom_exit(f"Error while writing to the config file: {e}", exit_fail)


def read_config(section: str, option: str):
    """Read the specified option from the config file.

    Args:
        section (str): The section of the config file to read from.
        option (str): The option to read in the specified section.

    Returns:
        str: The value of the specified option.
    """
    config_parser = ConfigParser()
    try:
        with open(config_file, "r") as cfg_file:
            config_parser.read_file(cfg_file)
    except FileNotFoundError:
        custom_exit("Config file not found.", exit_fail)
    except Exception as e:
        custom_exit(f"Error while reading the config file: {e}", exit_fail)

    return config_parser.get(section, option)
