import tempfile
from abc import ABC, abstractmethod
from typing import Union
from pathlib import Path

from deezy.audio_encoders.base import BaseAudioEncoder
from deezy.enums.dd import DolbyDigitalChannels
from deezy.enums.shared import DeeFPS, StereoDownmix
from deezy.exceptions import PathTooLongError


class BaseDeeAudioEncoder(BaseAudioEncoder, ABC):
    @abstractmethod
    def _get_accepted_bitrates(self, channels: int):
        """Gets a list of accepted bitrates for the channel type"""

    @abstractmethod
    def _get_down_mix_config(self, channels: DolbyDigitalChannels):
        """Gets the correct downmix string for DEE depending on channel count"""

    @abstractmethod
    def _generate_ffmpeg_cmd(
        self,
        ffmpeg_path: Path,
        file_input: Path,
        track_index: int,
        sample_rate: int,
        channels: DolbyDigitalChannels,
        stereo_down_mix: StereoDownmix,
        output_dir: Path,
        wav_file_name: str,
    ):
        """Method to generate FFMPEG command to process"""

    @staticmethod
    def _dee_allowed_input(input_channels: int):
        """Check's if the input channels are in the DEE allowed input channel list"""
        if input_channels in [1, 2, 6, 8]:
            return True
        return False

    @staticmethod
    def _get_ffmpeg_cmd(
        ffmpeg_path: Path,
        file_input: Path,
        track_index: int,
        bits_per_sample: int,
        audio_filter_args: list,
        output_dir: Path,
        wav_file_name: str,
    ):
        """
        Generates an FFmpeg command as a list of strings to convert an audio file
        to a WAV file with the specified parameters.

        Args:
            ffmpeg_path (Path): Path to the FFmpeg executable.
            file_input (Path): Path to the input audio file.
            track_index (int): Index of the audio track to extract.
            bits_per_sample (int): Number of bits per sample of the output WAV file.
            audio_filter_args (list): List of additional audio filter arguments to apply.
            output_dir (Path): Path to the directory where the output WAV file will be saved.
            wav_file_name (str): Name of the output WAV file.

        Returns:
            List[str]: A list of strings representing the FFmpeg command.
        """
        ffmpeg_cmd = [
            str(ffmpeg_path),
            "-y",
            "-drc_scale",
            "0",
            "-i",
            str(Path(file_input)),
            "-map",
            f"0:a:{track_index}",
            "-c",
            f"pcm_s{str(bits_per_sample)}le",
            *(audio_filter_args),
            "-rf64",
            "always",
            "-hide_banner",
            "-v",
            "-stats",
            str(Path(output_dir / wav_file_name)),
        ]
        return ffmpeg_cmd

    @staticmethod
    def _get_dee_cmd(dee_path: Path, xml_path: Path):
        """
        Generate the command for running DEE using the specified DEE and XML paths.

        Args:
            dee_path (Path): The path to the DEE executable.
            xml_path (Path): The path to the input XML file.

        Returns:
            List[str]: The DEE command with the specified paths.
        """
        dee_cmd = [
            str(dee_path),
            "--progress-interval",
            "500",
            "--diagnostics-interval",
            "90000",
            "--verbose",
            "-x",
            str(xml_path),
            "--disable-xml-validation",
        ]
        return dee_cmd

    @staticmethod
    def _get_fps(fps: Union[str, None]):
        """
        Tries to get a valid FPS value from the input, handling conversion from string to float/int,
        otherwise returns 'not_indicated'.

        Args:
            fps (str, float): The input FPS input to check.

        Returns:
            DeeFPS: A valid DeeFPS value from the input, or FPS_NOT_INDICATED if not found.

        """
        try:
            if fps:
                if "." in fps:
                    return DeeFPS(float(fps))
                else:
                    return DeeFPS(int(fps))
            else:
                return str(DeeFPS.FPS_NOT_INDICATED)
        except ValueError:
            return str(DeeFPS.FPS_NOT_INDICATED)

    @staticmethod
    def _get_temp_dir(file_input: Path, temp_dir: Path):
        """
        Creates a temporary directory and returns its path. If `temp_dir` is provided,
        creates a directory with that name instead of a randomly generated one.
        If the length of the path to the input file plus the length of `temp_dir`
        exceeds 259 characters, raises a `PathTooLongError`.

        Args:
            file_input (Path): Path object representing the input file.
            temp_dir (Path): Path object representing the location to create the temporary directory in.

        Returns:
            Path: Path object representing the path to the temporary directory.
        """
        if temp_dir:
            if len(file_input.name) + len(temp_dir) < 259:
                raise PathTooLongError(
                    "Path provided with input file exceeds path length for DEE."
                )
            temp_directory = Path(temp_dir)
            temp_directory.mkdir(exist_ok=True)

        else:
            temp_directory = Path(tempfile.mkdtemp(prefix="dee_temp_"))

        return temp_directory
