from pathlib import Path
import sys
import shutil
from argparse import ArgumentParser
from packages.dd_ddp import dd_ddp_bitrates
from packages.shared.config_control import _create_config, _read_config
import xmltodict
from pymediainfo import MediaInfo


def _get_working_dir():
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


def _save_xml(output_dir: Path, output_file_name: Path, xml_base: dict):
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
        raise ValueError("XML file could not be created")


def _validate_track_index(value: any):
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


def _validate_bitrate_with_channels_and_format(arguments: ArgumentParser.parse_args):
    """
    Validate bitrate input based on channel input and file format.
    If an invalid input is detected, raise a parser error that will update
    the user with valid options and exit the program automatically.

    Args:
        arguments (ArgumentParser.parse_args): Parsed arguments from parser instance
    """
    # TODO we might need to change this for atmos once we do full support for all channels

    if arguments.encoder != "atmos":
        if arguments.encoder == "dd":
            if arguments.channels == 1:
                valid_bitrates = dd_ddp_bitrates.get("dd_10")
            elif arguments.channels == 2:
                valid_bitrates = dd_ddp_bitrates.get("dd_20")
            elif arguments.channels == 6:
                valid_bitrates = dd_ddp_bitrates.get("dd_51")
            else:
                raise ValueError("Invalid channel count.")
        elif arguments.encoder == "ddp":
            if arguments.channels == 1:
                valid_bitrates = dd_ddp_bitrates.get("ddp_10")
            elif arguments.channels == 2:
                valid_bitrates = dd_ddp_bitrates.get("ddp_20")
            elif arguments.channels == 6:
                valid_bitrates = dd_ddp_bitrates.get("ddp_51")
            elif arguments.channels == 8:
                valid_bitrates = dd_ddp_bitrates.get("ddp_71_standard")
            else:
                raise ValueError("Invalid channel count.")
        else:
            raise ValueError("Unknown file format.")

        if arguments.bitrate not in valid_bitrates:
            raise ValueError(
                f"Invalid bitrate for input channel count and file type: {arguments.encoder} {str(arguments.channels)}.\nValid options: {', '.join(str(v) for v in valid_bitrates)}"
            )


def _check_disk_space(drive_path: Path, required_space: int):
    """
    Check for free space at the drive path, rounding to nearest whole number.
    If there isn't at least "required_space" GB of space free, raise an ArgumentTypeError.

    Args:
        drive_path (Path): Path to check
        required_space (int): Minimum space (GB)
    """

    # get free space in bytes
    required_space_cwd = shutil.disk_usage(Path(drive_path)).free

    # convert to GB's
    free_space_gb = round(required_space_cwd / (1024**3))

    # check to ensure the desired space in GB's is free
    if free_space_gb < int(required_space):
        raise ValueError("There isn't enough free space to decode Dolby Atmos.")
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


def _delay_detection(media_info: MediaInfo, file_input: Path, track_index: int):
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


def _language_detection(media_info: MediaInfo, track_index: int):
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


def _generate_output_filename(
    media_info: MediaInfo, file_input: Path, track_index: int, encoder: str
):
    """Automatically generate an output file name

    Args:
        media_info (MediaInfo): pymediainfo object of input file
        file_input (Path): Path to input file
        track_index (int): Track index from args
        encoder (str): Encoder format

    Returns:
        Path: Path of a automatically generated filename
    """
    # generate extension based on selected encoder format
    extension = ".ac3" if encoder == "dd" else ".ec3"

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
        delay = _delay_detection(media_info, file_input, track_index)
        language = _language_detection(media_info, track_index)
        file_name = f"{base_name}_{language}_{delay}{extension}"
        return Path(base_dir / Path(file_name))


class FindDependencies:
    """
    A utility class for finding and verifying dependencies required by a program.
    It first tries to locate the dependencies beside the program,
    then in the configuration file, and finally on the system PATH.

    Attributes:
        ffmpeg (str): The path to the FFmpeg executable, or None if not found.
        mkvextract (str): The path to the mkvextract executable, or None if not found.
        dee (str): The path to the Dee executable, or None if not found.
        gst_launch (str): The path to the gst-launch-1.0 executable, or None if not found.

    Args:
        base_wd (Path): The base working directory of the program.
    """

    def __init__(self, base_wd: Path):
        self.ffmpeg = None
        self.mkvextract = None
        self.dee = None
        self.gst_launch = None

        self._locate_beside_program(base_wd)

        if None in [self.ffmpeg, self.mkvextract, self.dee, self.gst_launch]:
            _create_config()
            self._locate_in_config()

        if None in [self.ffmpeg, self.mkvextract, self.dee, self.gst_launch]:
            self._locate_on_path()

        self._verify_dependencies(
            [self.ffmpeg, self.mkvextract, self.dee, self.gst_launch]
        )

    def _locate_beside_program(self, base_wd):
        ffmpeg_path = Path(base_wd / "apps/ffmpeg/ffmpeg.exe")
        mkvextract_path = Path(base_wd / "apps/mkvextract/mkvextract.exe")
        dee_path = Path(base_wd / "apps/dee/dee.exe")
        gst_launch_path = Path(base_wd / "apps/drp/gst-launch-1.0.exe")

        found_paths = [
            str(path)
            for path in [ffmpeg_path, mkvextract_path, dee_path, gst_launch_path]
            if path.exists()
        ]

        for path in found_paths:
            if str(path) == str(ffmpeg_path) and not self.ffmpeg:
                self.ffmpeg = str(path)
            elif str(path) == str(mkvextract_path) and not self.mkvextract:
                self.mkvextract = str(path)
            elif str(path) == str(dee_path) and not self.dee:
                self.dee = str(path)
            elif str(path) == str(gst_launch_path) and not self.gst_launch:
                self.gst_launch = str(path)

    def _locate_in_config(self):
        attribute_names = ["ffmpeg", "mkvextract", "dee", "gst_launch"]
        config_section = "tool_paths"
        for attr_name in attribute_names:
            value = _read_config(config_section, attr_name)
            if value and Path(value).is_file():
                setattr(self, attr_name, str(value))

    def _locate_on_path(self):
        if self.ffmpeg is None:
            self.ffmpeg = shutil.which("ffmpeg")
        if self.mkvextract is None:
            self.mkvextract = shutil.which("mkvextract")
        if self.dee is None:
            self.dee = shutil.which("dee")
        if self.gst_launch is None:
            self.gst_launch = shutil.which("gst-launch-1.0")

    @staticmethod
    def _verify_dependencies(dependencies: list):
        executable_names = ["ffmpeg", "mkvextract", "dee", "gst_launch"]
        for exe_path, exe_name in zip(dependencies, executable_names):
            if exe_path is None or exe_path == "" or not Path(exe_path).is_file():
                raise FileNotFoundError(f"{exe_name} path not found")
