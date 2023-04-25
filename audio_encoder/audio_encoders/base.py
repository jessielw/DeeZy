from abc import ABC, abstractmethod
from pathlib import Path
import shutil


class NotEnoughSpace(Exception):
    """Custom error class to for insufficient storage"""

    pass


class BaseAudioEncoder(ABC):
    @staticmethod
    def _check_input_file(input_file: Path):
        """Checks to ensure input file exists retuning a boolean value

        Args:
            input_file (Path): Input file path

        Returns:
            bool: True or False
        """
        if not input_file.exists():
            raise FileNotFoundError(f"Could not find {input_file.name}.")
        return input_file.exists()

    @staticmethod
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
            raise NotEnoughSpace(f"Insufficient storage to complete the process.")
        else:
            return True
