from pathlib import Path
import sys
from argparse import ArgumentParser, ArgumentTypeError
from packages.dd_ddp import dd_ddp_bitrates
from xmltodict import unparse


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


def save_xml(output_dir: Path, output_file_name: Path, xml_base: dict):
    """Creates/Deletes old XML files for use with DEE

    Args:
        output_dir (Path): Full output directory
        output_file_name (Path): File name
        xml_base (dict): XML generated dictionary

    Returns:
        Path: Path to XML file for DEE
    """
    # Save out the updated template (use filename output with xml suffix)
    updated_template_file = Path(output_dir / Path(output_file_name)).with_suffix(
        ".xml"
    )

    # delete xml output template if one already exists
    if updated_template_file.exists():
        updated_template_file.unlink()

    # write new xml template for dee
    with open(updated_template_file, "w", encoding="utf-8") as xml_out:
        xml_out.write(unparse(xml_base, pretty=True, indent="  "))

    # check to ensure template file was created
    if updated_template_file.exists():
        return updated_template_file
    else:
        raise ArgumentTypeError("XML file could not be created")


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


def validate_channels_with_format(arguments: ArgumentParser.parse_args):
    """
    Validate channel count based on encoder format.

    We'll only check channels if we're using dd/ddp, ignoring this function for atmos.

    If an invalid input is detected, raise a parser error that will update
    the user with valid options and exit the program automatically.

    Args:
        arguments (ArgumentParser.parse_args): Parsed arguments from parser instance
    """

    if arguments.format != "atmos":
        if arguments.format == "dd":
            valid_channels = [1, 2, 6]
        elif arguments.format == "ddp":
            valid_channels = [1, 2, 6, 8]
        else:
            raise ArgumentTypeError("Unknown file format.")

        if arguments.channels not in valid_channels:
            ArgumentTypeError.error(
                message=f"Invalid channel count for designated file type: {arguments.format}.\nValid options: {valid_channels}"
            )


def validate_bitrate_with_channels_and_format(arguments: ArgumentParser.parse_args):
    """
    Validate bitrate input based on channel input and file format.
    If an invalid input is detected, raise a parser error that will update
    the user with valid options and exit the program automatically.

    Args:
        arguments (ArgumentParser.parse_args): Parsed arguments from parser instance
    """

    if arguments.format != "atmos":
        if arguments.format == "dd":
            if arguments.channels == 1:
                valid_bitrates = dd_ddp_bitrates.get("dd_10")
            elif arguments.channels == 2:
                valid_bitrates = dd_ddp_bitrates.get("dd_20")
            elif arguments.channels == 6:
                valid_bitrates = dd_ddp_bitrates.get("dd_51")
            else:
                raise ArgumentTypeError("Invalid channel count.")
        elif arguments.format == "ddp":
            if arguments.channels == 1:
                valid_bitrates = dd_ddp_bitrates.get("ddp_10")
            elif arguments.channels == 2:
                valid_bitrates = dd_ddp_bitrates.get("ddp_20")
            elif arguments.channels == 6:
                valid_bitrates = dd_ddp_bitrates.get("ddp_51")
            elif arguments.channels == 8:
                valid_bitrates = dd_ddp_bitrates.get("ddp_71_standard")
            else:
                raise ArgumentTypeError("Invalid channel count.")
        else:
            raise ArgumentTypeError("Unknown file format.")

        if arguments.bitrate not in valid_bitrates:
            ArgumentTypeError.error(
                message=f"Invalid bitrate for input channel count and file type: {arguments.format} {str(arguments.channels)}.\nValid options: {', '.join(str(v) for v in valid_bitrates)}"
            )
