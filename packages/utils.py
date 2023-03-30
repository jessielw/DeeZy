from pathlib import Path
import sys
from argparse import ArgumentParser
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


def validate_channels_with_format(
    arg_parser: ArgumentParser, arguments: ArgumentParser.parse_args
):
    """
    Validate channel count based on file format.
    If an invalid input is detected, raise a parser error that will update
    the user with valid options and exit the program automatically.

    Args:
        arg_parser (ArgumentParser): Parser instance
        arguments (ArgumentParser.parse_args): Parsed arguments from parser instance
    """

    if arguments.format == "dd":
        valid_channels = [1, 2, 6]
    elif arguments.format == "ddp":
        valid_channels = [1, 2, 6, 8]
    else:
        raise Exception("Unknown file format.")

    if arguments.channels not in valid_channels:
        arg_parser.error(
            message=f"Invalid channel count for designated file type: {arguments.format}.\nValid options: {valid_channels}"
        )


def validate_bitrate_with_channels_and_format(
    arg_parser: ArgumentParser, arguments: ArgumentParser.parse_args
):
    """
    Validate bitrate input based on channel input and file format.
    If an invalid input is detected, raise a parser error that will update
    the user with valid options and exit the program automatically.

    Args:
        arg_parser (ArgumentParser): Parser instance
        arguments (ArgumentParser.parse_args): Parsed arguments from parser instance
    """

    if arguments.format == "dd":
        if arguments.channels == 1:
            valid_bitrates = allowed_bitrates.get("dd_10")
        if arguments.channels == 2:
            valid_bitrates = allowed_bitrates.get("dd_20")
        if arguments.channels == 6:
            valid_bitrates = allowed_bitrates.get("dd_51")
        else:
            raise Exception("Invalid channel count.")
    elif arguments.format == "ddp":
        if arguments.channels == 1:
            valid_bitrates = allowed_bitrates.get("ddp_10")
        if arguments.channels == 2:
            valid_bitrates = allowed_bitrates.get("ddp_20")
        if arguments.channels == 6:
            valid_bitrates = allowed_bitrates.get("ddp_51")
        if arguments.channels == 8:
            valid_bitrates = allowed_bitrates.get("ddp_71_standard")
        else:
            raise Exception("Invalid channel count.")
    else:
        raise Exception("Unknown file format.")

    if arguments.bitrate not in valid_bitrates:
        arg_parser.error(
            message=f"Invalid bitrate for input channel count and file type: {arguments.format} {str(arguments.channels)}.\nValid options: {', '.join(str(v) for v in valid_bitrates)}"
        )
