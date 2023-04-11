from pathlib import Path
import sys
import shutil
from argparse import ArgumentParser, ArgumentTypeError
from packages.dd_ddp import dd_ddp_bitrates
import xmltodict
from pymediainfo import MediaInfo


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
        xml_out.write(xmltodict.unparse(xml_base, pretty=True, indent="  "))

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
            ArgumentTypeError(
                f"Invalid bitrate for input channel count and file type: {arguments.format} {str(arguments.channels)}.\nValid options: {', '.join(str(v) for v in valid_bitrates)}"
            )


def check_disk_space(drive_path: Path, free_space: int):
    """
    Check for free space at the drive path, rounding to nearest whole number.
    If there isn't at least "free_space" GB of space free, raise an ArgumentTypeError.

    Args:
        drive_path (Path): Path to check
        free_space (int): Minimum space (GB)
    """

    # get free space in bytes
    free_space_cwd = shutil.disk_usage(Path(drive_path)).free

    # convert to GB's
    free_space_gb = round(free_space_cwd / (1024**3))

    # check to ensure the desired space in GB's is free
    if free_space_gb < int(free_space):
        raise ArgumentTypeError("There isn't enough free space to decode Dolby Atmos")
    else:
        return True


class PrintSameLine:
    """Class to correctly print on same line"""

    def __init__(self):
        self.last_message = ""

    def print_msg(self, msg: str):
        print(" " * len(self.last_message), end="\r", flush=True)
        print(msg, end="\r", flush=True)
        self.last_message = msg


def delay_detection(media_info: MediaInfo, file_input: Path, track_index: int):
    """Detect delay relative to video to inject into filename

    Args:
        media_info (MediaInfo): pymediainfo object of input file
        file_input (Path): Path to input file
        track_index (int): Track index from args

    Returns:
        str: Returns a formatted delay string
    """
    audio_track = media_info.tracks[track_index + 1]
    if Path(file_input).suffix == ".mp4":
        if audio_track.source_delay:
            delay_string = f"[delay {str(audio_track.source_delay)}ms]"
        else:
            delay_string = str("[delay 0ms]")
    else:
        if audio_track.delay_relative_to_video:
            delay_string = f"[delay {str(audio_track.delay_relative_to_video)}ms]"
        else:
            delay_string = str("[delay 0ms]")
    return delay_string


def language_detection(media_info: MediaInfo, track_index: int):
    """
    Detect language of input track, returning language in the format of
    "eng" instead of "en" or "english."

    Args:
        media_info (MediaInfo): pymediainfo object of input file
        track_index (int): Track index from args

    Returns:
        str: Returns a formatted language string
    """
    audio_track = media_info.tracks[track_index + 1]
    if audio_track.other_language:
        l_lengths = [len(lang) for lang in audio_track.other_language]
        l_index = next((i for i, length in enumerate(l_lengths) if length == 3), None)
        language_string = (
            f"[{audio_track.other_language[l_index]}]"
            if l_index is not None
            else "[und]"
        )
    else:
        language_string = "[und]"
    return language_string


def generate_output_filename(
    media_info: MediaInfo, file_input: Path, track_index: int, file_format: str
):
    """Automatically generate an output file name

    Args:
        media_info (MediaInfo): pymediainfo object of input file
        file_input (Path): Path to input file
        track_index (int): Track index from args
        file_format (str): Encoder format

    Returns:
        Path: Path of a automatically generated filename
    """
    # generate extension based on selected encoder format
    extension = ".ac3" if file_format == "dd" else ".ec3"

    # base directory/name
    base_dir = Path(file_input).parent
    base_name = Path(Path(file_input).name).with_suffix("")

    # if track index is 0 we can assume this audio is in a raw format
    if track_index == 0:
        file_name = f"{base_name}{extension}"
        return Path(base_dir / Path(file_name))

    # if track index is equal to or greater than 1, we can assume it's likely in a container of some
    # sort, so we'll go ahead and attempt to detect delay/language to inject into the title.
    elif track_index >= 1:
        delay = delay_detection(media_info, file_input, track_index)
        language = language_detection(media_info, track_index)
        file_name = f"{base_name}_{language}_{delay}{extension}"
        return Path(base_dir / Path(file_name))
