from pathlib import Path
import sys
from argparse import ArgumentTypeError, ArgumentParser
from packages.bitrates import allowed_bitrates


def get_working_dir():
    """
    Used to determine the correct working directory automatically.
    This way we can utilize files/relative paths easily.

    Returns:
        (Path): Current working directory
    """
    # we're in a pyinstaller.exe bundle
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys.executable).parent

    # we're running from a *.py file
    else:
        return Path.cwd()


def validate_channels(value: any):
    """Ensure we are utilizing the correct amount of channels.

    Args:
        value (any): Can be any input

    Returns:
        int: Input as an integer
    """

    valid_channels = [1, 2, 6]
    if not value.isdigit():
        raise ArgumentTypeError(f"Invalid input channels. Value must be an integer.")
    value = int(value)
    if value not in valid_channels:
        raise ArgumentTypeError(
            f"Invalid number of channels. Valid options: {valid_channels}"
        )
    return value


def validate_track_index(value: any):
    """
    Determines if the input is a valid number.
    If it's not returns the default of 0.

    Args:
        value (any): Can be any input

    Returns:
        int: Corrected track index
    """

    # Check if the input is valid
    if value.isdigit():
        return int(value)
    # If the input is invalid, return the default value
    return 0


def validate_bitrate(arg_parser: ArgumentParser, arguments: ArgumentParser.parse_args):
    """
    Validate bitrate input based on channel input.
    If an invalid input is detected, raise a parser error that will update
    the user with valid options and exit the program automatically.

    Args:
        arg_parser (ArgumentParser): Parser instance
        arguments (ArgumentParser.parse_args): Parsed arguments from parser instance
    """

    if arguments.channels == 1:
        if arguments.bitrate not in allowed_bitrates.get("dd_10"):
            arg_parser.error(
                message=f"Invalid bitrate for channel input of 1 (mono).\nValid choices: {', '.join(str(v) for v in allowed_bitrates.get('dd_10'))}"
            )
    elif arguments.channels == 2:
        if arguments.bitrate not in allowed_bitrates.get("dd_20"):
            arg_parser.error(
                message=f"Invalid bitrate for channel input of 2 (stereo).\nValid choices: {', '.join(str(v) for v in allowed_bitrates.get('dd_20'))}"
            )
    elif arguments.channels == 6:
        if arguments.bitrate not in allowed_bitrates.get("dd_51"):
            arg_parser.error(
                message=f"Invalid bitrate for channel input of 6 (5.1).\nValid choices: {', '.join(str(v) for v in allowed_bitrates.get('dd_51'))}"
            )