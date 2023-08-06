import shutil
import os
from pathlib import Path
from deezy.exceptions import (
    ChannelMixError,
    InputFileNotFoundError,
    NotEnoughSpaceError,
)


class BaseAudioEncoder:
    @staticmethod
    def _check_for_up_mixing(source_channels: int, desired_channels: int):
        """Provide source_channels and ensure that desired channels is less than source"""
        if source_channels < desired_channels:
            raise ChannelMixError("Up-mixing is not supported.")

    @staticmethod
    def _check_input_file(input_file: Path):
        """Checks to ensure input file exists retuning a boolean value

        Args:
            input_file (Path): Input file path

        Returns:
            bool: True or False
        """
        if not input_file.exists():
            raise InputFileNotFoundError(f"Could not find {input_file.name}.")
        return input_file.exists()

    @staticmethod
    def _check_disk_space(input_file_path: Path, temp_path: Path):
        """
        Check for free space at the temporary directory, rounding to the nearest whole number.
        If there isn't at least 110% of the size of the input file as free space in the temporary directory,
        raise an exception.

        Args:
            input_file_path (Path): Path to the input file.
            temp_path (Path): Path to the temporary directory where intermediate files will be stored.
        """

        # Get the size of the input file in bytes
        input_file_size = os.path.getsize(input_file_path)

        # Get free space in bytes in the temporary directory
        free_space_bytes = shutil.disk_usage(temp_path).free

        # Calculate the required space (110% of the input file size) in bytes
        required_space_bytes = int(input_file_size * 1.1)

        # Check if the required space is available
        if free_space_bytes < required_space_bytes:
            raise NotEnoughSpaceError(
                "Insufficient storage in the temporary directory to complete the process."
            )

    @staticmethod
    def _get_closest_allowed_bitrate(bitrate: int, accepted_bitrates: list):
        """Returns the closest allowed bitrate from a given input bitrate in a list of accepted bitrates.

        Args:
            bitrate (int): The input bitrate to find the closest allowed bitrate for.
            accepted_bitrates (list): A list of accepted bitrates.

        Returns:
            int: The closest allowed bitrate in the list of accepted bitrates.
        """
        return min(accepted_bitrates, key=lambda x: abs(x - bitrate))
