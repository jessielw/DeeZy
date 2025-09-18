from abc import ABC, abstractmethod
from collections.abc import Callable
from enum import Enum
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Generic, TypeVar

from deezy.audio_encoders.base import BaseAudioEncoder
from deezy.audio_encoders.delay import get_dee_delay
from deezy.config.manager import get_config_manager
from deezy.enums.codec_format import CodecFormat
from deezy.enums.shared import DeeDelay, DeeFPS, TrackType
from deezy.exceptions import PathTooLongError
from deezy.payloads.shared import ChannelBitrates
from deezy.track_info.audio_track_info import AudioTrackInfo
from deezy.track_info.track_index import TrackIndex
from deezy.utils.logger import logger

DolbyChannelType = TypeVar("DolbyChannelType", bound=Enum)


class BaseDeeAudioEncoder(BaseAudioEncoder, ABC, Generic[DolbyChannelType]):
    def get_delay(
        self,
        audio_track_info: AudioTrackInfo,
        payload_delay: str | None,
        file_input: Path,
    ) -> DeeDelay:
        delay_str = "0ms"
        # if audio is raw we'll parse delay from file if it exists
        if audio_track_info.is_raw_audio:
            delay_str = self._parse_delay_from_file(file_input)
        # if delay is provided via payload (CLI) we'll override the above
        if payload_delay:
            delay_str = payload_delay
        # generate dee delay
        delay = get_dee_delay(delay_str)
        if delay.is_delay():
            logger.debug(f"Generated delay {delay.MODE}:{delay.DELAY}.")
        return delay

    def get_config_based_bitrate(
        self,
        format_command: CodecFormat,
        payload_bitrate: int | None,
        payload_channels: Any,
        audio_track_info: AudioTrackInfo,
        bitrate_obj: ChannelBitrates,
        auto_enum_value: Any,
        channel_resolver: Callable[[int], Any],
    ) -> int:
        """
        Helper method to get bitrate with intelligent config-based defaults.

        Args:
            format_command: CodecFormat enum for config lookup (e.g., CodecFormat.DD, CodecFormat.DDP)
            payload_bitrate: User-provided bitrate (None if not provided)
            payload_channels: Channel enum from payload
            audio_track_info: Audio track information with source channel count
            bitrate_obj: ChannelBitrates object for validation
            auto_enum_value: The AUTO enum value for this codec
            channel_resolver: Function that takes (source_channels) and returns resolved channel enum

        Returns:
            Validated bitrate to use
        """
        if payload_bitrate:
            # user/preset provided a bitrate - validate it
            if not bitrate_obj.is_valid_bitrate(payload_bitrate):
                fixed_bitrate = bitrate_obj.get_closest_bitrate(payload_bitrate)
                logger.warning(
                    f"Bitrate {payload_bitrate} is invalid for this configuration. "
                    f"Using the next closest allowed bitrate: {fixed_bitrate}."
                )
                return fixed_bitrate
            else:
                logger.debug(f"Using provided bitrate: {payload_bitrate}.")
                return payload_bitrate
        else:
            # no bitrate provided - try config defaults first, then enum defaults
            config_bitrate = None
            target_channels = None

            # try to get config-based default for the detected channels
            try:
                config_manager = get_config_manager()
                if config_manager:
                    # determine the actual target channels after AUTO resolution
                    target_channels = payload_channels
                    if (
                        auto_enum_value is not None
                        and payload_channels == auto_enum_value
                    ):
                        # resolve AUTO to actual channel layout based on source
                        target_channels = channel_resolver(audio_track_info.channels)

                    # get config default for the resolved channels
                    config_bitrate = config_manager.get_default_bitrate(
                        format_command, target_channels
                    )
            except Exception:
                # if config lookup fails, continue to enum default
                pass

            # validate config bitrate if found
            if config_bitrate is not None:
                if bitrate_obj.is_valid_bitrate(config_bitrate):
                    logger.debug(
                        f"No supplied bitrate, using config default {config_bitrate} for {target_channels}."
                    )
                    return config_bitrate
                else:
                    # config bitrate is invalid, fix it
                    fixed_config_bitrate = bitrate_obj.get_closest_bitrate(
                        config_bitrate
                    )
                    logger.warning(
                        f"Config bitrate {config_bitrate} is invalid for this configuration. "
                        f"Using the next closest allowed bitrate: {fixed_config_bitrate}."
                    )
                    return fixed_config_bitrate

            # fallback to enum default if config lookup failed
            logger.debug(f"No supplied bitrate, defaulting to {bitrate_obj.default}.")
            return bitrate_obj.default

    @staticmethod
    @abstractmethod
    def _get_channel_bitrate_object(
        desired_channels: DolbyChannelType, source_channels: int
    ) -> ChannelBitrates:
        """Gets a ChannelBitrates object"""

    @staticmethod
    @abstractmethod
    def _get_down_mix_config(*args, **kwargs) -> str:
        """Gets the correct downmix string for DEE depending on channel count"""

    @abstractmethod
    def _generate_ffmpeg_cmd(self, *args, **kwargs) -> list[str]:
        """Method to generate FFMPEG command to process"""

    @staticmethod
    def _dee_allowed_input(input_channels: int) -> bool:
        """Check's if the input channels are in the DEE allowed input channel list"""
        return input_channels in (1, 2, 6, 8)

    @staticmethod
    def _get_ffmpeg_cmd(
        ffmpeg_path: Path,
        file_input: Path,
        track_index: TrackIndex,
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
            track_index (TrackIndex): TrackIndex object.
            bits_per_sample (int): Number of bits per sample of the output WAV file.
            audio_filter_args (list): list of additional audio filter arguments to apply.
            output_dir (Path): Path to the directory where the output WAV file will be saved.
            wav_file_name (str): Name of the output WAV file.

        Returns:
            list[str]: A list of strings representing the FFmpeg command.
        """
        ffmpeg_cmd = [
            str(ffmpeg_path),
            "-y",
            "-drc_scale",
            "0",
            "-hide_banner",
            "-v",  # verbosity level will be injected by processor
            "-i",
            str(Path(file_input)),
            "-map",
            f"0:a:{track_index.index}"
            if track_index.track_type is TrackType.AUDIO
            else f"0:{track_index.index}",
            "-c",
            f"pcm_s{str(bits_per_sample)}le",
            *(audio_filter_args),
            "-rf64",
            "always",
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
    def get_dee_json_cmd(dee_path: Path, json_path: Path):
        """
        Generate the command for running DEE using the specified DEE and JSON paths.

        Args:
            dee_path (Path): The path to the DEE executable.
            json_path (Path): The path to the input JSON file.

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
            "-j",
            str(json_path),
        ]
        return dee_cmd

    @staticmethod
    def _get_fps(fps: str | float | int | None):
        """
        Tries to get a valid FPS value from the input, handling conversion from string to float/int,
        otherwise returns 'not_indicated'.

        Args:
            fps (str, float | int | None): The input FPS input to check.

        Returns:
            DeeFPS: A valid DeeFPS value from the input, or FPS_NOT_INDICATED if not found.

        """
        try:
            if fps is None:
                return DeeFPS.FPS_NOT_INDICATED

            if isinstance(fps, str):
                value = float(fps) if "." in fps else int(fps)
            elif isinstance(fps, float):
                # allow integer-valued floats, otherwise keep float
                value = int(fps) if fps.is_integer() else fps
            # int
            else:
                value = fps

            return DeeFPS(value)
        except (ValueError, TypeError):
            return DeeFPS.FPS_NOT_INDICATED

    @staticmethod
    def _get_temp_dir(file_input: Path, temp_dir: Path | None) -> Path:
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
            # create job folder in user-specified temp directory
            temp_directory = Path(tempfile.mkdtemp(dir=temp_dir))
            if len(file_input.name) + len(str(temp_directory)) > 259:
                raise PathTooLongError(
                    "Path provided with input file exceeds path length for DEE."
                )
        else:
            # create deezy parent folder in system temp if it doesn't exist
            system_temp = Path(tempfile.gettempdir())
            deezy_temp_base = system_temp / "deezy"
            deezy_temp_base.mkdir(exist_ok=True)

            # create job-specific folder without deezy_ prefix
            temp_directory = Path(tempfile.mkdtemp(dir=deezy_temp_base))

        return temp_directory

    @staticmethod
    def _clean_temp(temp_dir: Path, keep_temp: bool):
        """
        Deletes temp folder and all child files.

        Args:
            temp_dir (Path): Path to the directory that we're deleting.
            keep_temp (bool): Boolean on rather or not we'd like to keep the files.
        """
        if not keep_temp:
            shutil.rmtree(temp_dir)

    @staticmethod
    def _parse_delay_from_file(media_path: Path) -> str:
        """Parse delay from filename, if None found return 0ms."""
        match = re.search(r"delay\s*(-?\d+(?:ms|s))", media_path.name, flags=re.I)
        if match:
            return match.group(1)
        return "0ms"
