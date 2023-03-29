from pathlib import Path
import sys
from argparse import ArgumentTypeError
import subprocess
from packages._version import program_name, __version__, developed_by


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


def process_job(cmd: list, banner: bool = False):
    """Process jobs"""

    with subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True
    ) as proc:
        print("####################")
        if banner:
            print(f"{program_name} {__version__}\nDeveloped by: {developed_by}\n")
        for line in proc.stdout:
            print(line.strip())
        print("####################\n")
