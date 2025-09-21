from abc import ABC, abstractmethod
from collections.abc import Callable
from enum import Enum
import json
import os
from pathlib import Path
import random
import shutil
import tempfile
import threading
import time
from typing import Any, Generic, Optional, TypeVar

from deezy.audio_encoders.base import BaseAudioEncoder
from deezy.audio_encoders.delay import get_dee_delay
from deezy.config.manager import ConfigManager, get_config_manager
from deezy.enums.channel_count import ChannelCount
from deezy.enums.codec_format import CodecFormat
from deezy.enums.shared import DeeDelay, DeeFPS, TrackType
from deezy.exceptions import PathTooLongError
from deezy.exceptions import OutputExistsError
from deezy.payloads.shared import ChannelBitrates
from deezy.track_info.audio_track_info import AudioTrackInfo
from deezy.track_info.track_index import TrackIndex
from deezy.track_info.utils import parse_delay_from_file
from deezy.utils.logger import logger

DolbyChannelType = TypeVar("DolbyChannelType", bound=Enum)


class BaseDeeAudioEncoder(BaseAudioEncoder, ABC, Generic[DolbyChannelType]):
    def get_delay(
        self,
        audio_track_info: AudioTrackInfo,
        payload_delay: str | None,
        payload_parse_elementary_delay: bool,
        file_input: Path,
    ) -> DeeDelay:
        delay_str = "0ms"
        # if audio is raw we'll parse delay from file if it exists
        if audio_track_info.is_elementary and payload_parse_elementary_delay:
            parse_delay = parse_delay_from_file(file_input)
            if parse_delay:
                delay_str = parse_delay
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
        source_audio_channels: int,
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
            source_audio_channels: Source audio channels.
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
            # no bitrate provided - try config defaults first: (source channel > target channel), then enum defaults
            config_bitrate = None
            target_channels = None

            # try to get config-based default for the detected channels
            try:
                config_manager = get_config_manager()
                if config_manager:
                    # try source channel from config if the user has it enabled
                    get_src_conf_bitrate = self._source_bitrate_from_config(
                        config_manager, format_command.value, source_audio_channels
                    )
                    if get_src_conf_bitrate:
                        logger.debug(
                            f"Got source channel bitrate from config ({get_src_conf_bitrate})"
                        )
                        config_bitrate = get_src_conf_bitrate

                    # determine the actual target channels after AUTO resolution
                    target_channels = payload_channels
                    if (
                        auto_enum_value is not None
                        and payload_channels == auto_enum_value
                    ):
                        # resolve AUTO to actual channel layout based on source
                        target_channels = channel_resolver(audio_track_info.channels)

                    # get config default for the resolved channels if not already determined from source config
                    if not config_bitrate:
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
    def _source_bitrate_from_config(
        conf_manager: ConfigManager, fmt: str, source_channels: int
    ) -> int | None:
        """Safely collects config from config manager if available."""
        try:
            channel_obj = ChannelCount(int(source_channels))
            # check in config
            section = conf_manager.config.get("default_source_bitrates")
            if not section:
                return None
            fmt_conf = section.get(fmt)
            if not fmt_conf:
                return None
            bitrate = fmt_conf.get(channel_obj.to_config())
            if bitrate is None or bitrate <= 0:
                return None
            return bitrate
        except Exception as e:
            logger.warning(f"Failed to get source bitrate from config: {e}")
            return None

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

    def _adjacent_temp_dir(self, file_input: Path) -> Path:
        """
        Returns an adjacent per-file temp/cache directory path (e.g. <parent>/<stem>_deezy).
        Ensures the directory exists.
        """
        temp_dir = file_input.parent / f"{file_input.stem}_deezy"
        temp_dir.mkdir(parents=True, exist_ok=True)
        return temp_dir

    def _metadata_path_for_output(self, temp_dir: Path, output: Path) -> Path:
        """Return the metadata.json path used for a given computed output."""
        return temp_dir / f"{output.stem}_metadata.json"

    def _read_reuse_metadata(self, metadata_path: Path) -> Optional[dict]:
        """Read metadata JSON if present. Returns dict or None on failure."""
        if not metadata_path.exists():
            return None
        try:
            with open(metadata_path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            logger.debug("Failed to read/parse metadata.json; ignoring and continuing.")
            return None

    def _check_reuse_signature(
        self,
        metadata_path: Path,
        encoder_id: str,
        signature: str,
        produced_file: str,
        temp_dir: Path,
    ) -> bool:
        """
        Generic reuse check scoped by encoder_id. Metadata format supports multiple encoders:

        {
            "source_mtime": ..., "source_size": ...,
            "encoders": {
                "dd": {"signature": "...", "produced_file": "..."},
                "ddp": {...}
            }
        }

        This function returns True when the encoder's recorded signature matches the
        provided signature and the produced_file exists in temp_dir. Only encoder-
        scoped entries under the 'encoders' mapping are considered.
        """
        meta = self._read_reuse_metadata(metadata_path)
        if not meta:
            return False

        # Primary: encoder-scoped metadata
        encs = meta.get("encoders") or {}
        enc_entry = encs.get(encoder_id)
        if enc_entry:
            rec_sig = enc_entry.get("signature")
            rec_file = enc_entry.get("produced_file")
            if rec_sig and rec_file and rec_sig == signature:
                return (temp_dir / rec_file).exists()

        # Only encoder-scoped entries are valid
        return False

    def _write_signature_metadata(
        self,
        metadata_path: Path,
        encoder_id: str,
        signature: str,
        produced_file: str,
        source_file: Path,
    ) -> None:
        """
        Atomically write/merge encoder-scoped signature metadata for reuse. Fail silently on error.

        If a metadata file already exists, merge the encoder entry into the 'encoders'
        mapping preserving existing top-level source_mtime/source_size where possible.
        """
        try:
            # read existing metadata if present
            existing = self._read_reuse_metadata(metadata_path) or {}

            # collect source info (prefer existing values)
            src_mtime = existing.get("source_mtime") or int(source_file.stat().st_mtime)
            src_size = existing.get("source_size") or int(source_file.stat().st_size)

            encs = existing.get("encoders") or {}
            encs[encoder_id] = {
                "signature": signature,
                "produced_file": produced_file,
            }

            meta = {
                "source_mtime": int(src_mtime),
                "source_size": int(src_size),
                "encoders": encs,
            }

            # atomic write via temp file in same directory
            tmp_path = None
            try:
                import tempfile as _tmp

                with _tmp.NamedTemporaryFile(
                    "w", delete=False, dir=str(metadata_path.parent), encoding="utf-8"
                ) as fh:
                    json.dump(meta, fh)
                    tmp_path = Path(fh.name)
                os.replace(str(tmp_path), str(metadata_path))
            finally:
                if tmp_path and tmp_path.exists():
                    try:
                        tmp_path.unlink()
                    except Exception:
                        pass
        except Exception:
            logger.debug("Failed to write metadata.json for reuse.")

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

    def _early_output_exists_check(self, output: Path, overwrite: bool) -> None:
        """Early check for output existence to fail fast.

        Args:
            output: final computed output Path
            overwrite: whether the job intends to overwrite existing output

        Raises:
            OutputExistsError: if output exists and overwrite is False
        """
        if output.exists():
            if overwrite:
                logger.debug(f"Output already exists and will be overwritten: {output}")
            else:
                raise OutputExistsError(f"Output already exists: {output}")

    # --- Phase semaphores and jitter for staggered processing ---
    # class-level semaphores so all encoder instances share the same limits.
    _ffmpeg_sem: threading.Semaphore | None = None
    _dee_sem: threading.Semaphore | None = None
    _truehdd_sem: threading.Semaphore | None = None
    _jitter_ms: int = 0

    @classmethod
    def init_phase_limits(
        cls,
        max_parallel: int,
        jitter_ms: int | None = None,
        ffmpeg_limit: int | None = None,
        dee_limit: int | None = None,
        truehdd_limit: int | None = None,
    ) -> None:
        """
        Initialize semaphores for FFmpeg and DEE phases.

        Args:
            max_parallel: maximum worker count from dispatcher; used to size semaphores.
            jitter_ms: maximum jitter in milliseconds to apply before heavy phases.
        """

        # determine per-phase limits (apply sensible defaults if not provided)
        ff_limit = ffmpeg_limit if (ffmpeg_limit is not None) else max(1, max_parallel)
        de_limit = dee_limit if (dee_limit is not None) else max(1, max_parallel)
        th_limit = (
            truehdd_limit if (truehdd_limit is not None) else max(1, max_parallel)
        )

        # cap limits to max_parallel to avoid confusing configurations
        capped_ff = min(max(1, ff_limit), max_parallel)
        capped_de = min(max(1, de_limit), max_parallel)
        capped_th = min(max(1, th_limit), max_parallel)

        # warn if user provided limits were capped
        if ffmpeg_limit is not None and capped_ff != ff_limit:
            logger.warning(
                f"--limit-ffmpeg {ffmpeg_limit} capped to {capped_ff} (max_parallel={max_parallel})"
            )
        if dee_limit is not None and capped_de != de_limit:
            logger.warning(
                f"--limit-dee {dee_limit} capped to {capped_de} (max_parallel={max_parallel})"
            )
        if truehdd_limit is not None and capped_th != th_limit:
            logger.warning(
                f"--limit-truehdd {truehdd_limit} capped to {capped_th} (max_parallel={max_parallel})"
            )

        ff_limit = capped_ff
        de_limit = capped_de
        th_limit = capped_th

        # (re)create semaphores sized to the computed limits
        cls._ffmpeg_sem = threading.Semaphore(ff_limit)
        cls._dee_sem = threading.Semaphore(de_limit)
        cls._truehdd_sem = threading.Semaphore(th_limit)

        if jitter_ms is not None:
            cls._jitter_ms = int(jitter_ms)

    def _maybe_jitter(self) -> None:
        """Apply a small random jitter sleep before heavy phases when configured."""
        jitter = getattr(self, "_jitter_ms", 0) or 0
        if jitter > 0:
            time.sleep(random.uniform(0, jitter) / 1000.0)

    def _acquire_ffmpeg(self) -> None:
        if self._ffmpeg_sem:
            self._ffmpeg_sem.acquire()

    def _release_ffmpeg(self) -> None:
        if self._ffmpeg_sem:
            try:
                self._ffmpeg_sem.release()
            except ValueError:
                # ignore release errors
                pass

    def _acquire_dee(self) -> None:
        if self._dee_sem:
            self._dee_sem.acquire()

    def _release_dee(self) -> None:
        if self._dee_sem:
            try:
                self._dee_sem.release()
            except ValueError:
                pass

    def _acquire_truehdd(self) -> None:
        if self._truehdd_sem:
            self._truehdd_sem.acquire()

    def _release_truehdd(self) -> None:
        if self._truehdd_sem:
            try:
                self._truehdd_sem.release()
            except ValueError:
                pass
