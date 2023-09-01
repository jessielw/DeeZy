import shutil
import os
from pathlib import Path
from typing import Union
from deezy.exceptions import (
    AutoChannelDetectionError,
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
    def _check_disk_space(
        input_file_path: Path,
        drive_path: Path,
        recommended_free_space: Union[None, int],
    ):
        """
        Check for free space at the temporary directory, rounding to the nearest whole number.
        If there isn't at least 110% of the size of the input file as free space in the temporary directory,
        raise an exception.

        Args:
            input_file_path (Path): Path to the input file.
            drive_path (Path): Path to the temporary directory where intermediate files will be stored.
            recommended_free_space (None or int): None or calculated free space in bytes.
        """

        # Calculate the required space (110% of the input file size if no recommendation) in bytes
        if recommended_free_space:
            required_space_bytes = recommended_free_space
        else:
            # Get the size of the input file in bytes
            input_file_size = os.path.getsize(input_file_path)

            required_space_bytes = int(input_file_size * 1.1)

        # Get free space in bytes in the temporary directory
        free_space_bytes = shutil.disk_usage(drive_path).free

        # Check if the required space is available
        if free_space_bytes < required_space_bytes:
            raise NotEnoughSpaceError(
                "Insufficient storage in the temporary directory to complete the process. "
                f"Calculated required storage (bytes): {required_space_bytes}"
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

    @staticmethod
    def _determine_auto_channel_s(
        input_track_channel_s: int, accepted_channel_list: list
    ):
        """Determine the highest quality automatic channel selection based on the input track and codec accepted channels

        Args:
            input_track_channel_s (int): Audio tracks input channel(s).
            accepted_channel_list (list): Dolby encoder used accepted channel list.

        Raises:
            AutoChannelDetectionError: If unable to detect the output channel raise an error.

        Returns:
            int: Highest accepted channel allowed by the codec.
        """
        if input_track_channel_s in accepted_channel_list:
            return input_track_channel_s
        else:
            lower_values = [
                x for x in accepted_channel_list if x < input_track_channel_s
            ]
            if lower_values:
                try:
                    return int(max(lower_values))
                except ValueError:
                    raise AutoChannelDetectionError(
                        "Failed to determine output channel automatically"
                    )
