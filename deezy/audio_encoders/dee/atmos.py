from pathlib import Path

from deezy.audio_encoders.dee.base import BaseDeeAudioEncoder
from deezy.audio_encoders.dee.json.dee_json_generator import DeeJSONGenerator
from deezy.audio_processors.dee import process_dee_job
from deezy.audio_processors.truehdd import decode_truehd_to_atmos
from deezy.enums.atmos import AtmosMode
from deezy.enums.codec_format import CodecFormat
from deezy.exceptions import (
    DependencyNotFoundError,
    InvalidAtmosInputError,
    InvalidExtensionError,
    OutputFileNotFoundError,
)
from deezy.payloads.atmos import AtmosPayload
from deezy.payloads.shared import ChannelBitrates
from deezy.track_info.mediainfo import MediainfoParser
from deezy.utils.logger import logger


class AtmosEncoder(BaseDeeAudioEncoder[AtmosMode]):
    """Atmos Encoder."""

    __slots__ = ()

    def __init__(self, payload: AtmosPayload):
        super().__init__(payload)
        self.payload: AtmosPayload
        logger.debug("Starting Atmos Encoder.")

    def _encode(self) -> Path:
        """Handles converting everything needed for DEE."""
        # file input
        file_input = Path(self.payload.file_input)
        self._check_input_file(file_input)

        # get audio track information
        mi_parser = MediainfoParser(file_input, self.payload.track_index)
        audio_track_info = mi_parser.get_audio_track_info()

        # bitrate
        # get object based off of desired channels and source audio track channels
        bitrate_obj = self._get_channel_bitrate_object(
            self.payload.atmos_mode, audio_track_info.channels
        )

        # check to see if the users bitrate is allowed
        runtime_bitrate = self.get_config_based_bitrate(
            format_command=CodecFormat.ATMOS,
            payload_bitrate=self.payload.bitrate,
            payload_channels=self.payload.atmos_mode,
            audio_track_info=audio_track_info,
            bitrate_obj=bitrate_obj,
            source_audio_channels=audio_track_info.channels,
            auto_enum_value=None,  # Atmos doesn't have AUTO
            channel_resolver=self.atmos_mode_resolver,
        )

        # check for up-mixing
        self._check_for_up_mixing(
            audio_track_info.channels, self.payload.atmos_mode.get_channels()
        )

        # delay
        delay = self.get_delay(
            self.payload.delay,
            file_input,
        )

        # fps
        fps = self._get_fps(audio_track_info.fps)
        logger.debug(f"Detected FPS {fps.to_dee_cmd()}.")

        # file output (if an output is a defined check users extension and use their output)
        if self.payload.file_output:
            output = Path(self.payload.file_output)
            if output.suffix not in (".ec3", ".eac3"):
                raise InvalidExtensionError(
                    "DDP output must must end with the suffix '.eac3' or '.ec3'."
                )
        else:
            # If an output template was provided, prefer rendering it. This is opt-in
            # and will be ignored if not present. Keep existing generate_output_filename
            # as the fallback to avoid changing default behavior.
            if self.payload.output_template:
                output = mi_parser.render_output_template(
                    template=str(self.payload.output_template),
                    suffix=".ec3",
                    output_channels=str(self.payload.atmos_mode.get_str_channels()),
                    delay_was_stripped=delay.is_delay(),
                    delay_relative_to_video=audio_track_info.delay_relative_to_video,
                    worker_id=self.payload.worker_id,
                )
                if self.payload.output_preview:
                    logger.info(f"Output preview: {output}")
                    return output
            else:
                output = mi_parser.generate_output_filename(
                    delay_was_stripped=delay.is_delay(),
                    delay_relative_to_video=audio_track_info.delay_relative_to_video,
                    suffix=".ec3",
                    output_channels=str(self.payload.atmos_mode.get_str_channels()),
                    worker_id=self.payload.worker_id,
                )

        # If a centralized batch output directory was provided and the user did not
        # explicitly supply an output path, place final output there. This ensures
        # an explicit --output wins over config-provided batch_output_dir.
        if self.payload.file_output is None and self.payload.batch_output_dir:
            output = Path(self.payload.batch_output_dir) / output.name
        logger.debug(f"Output path {output}.")

        # temp dir: prefer a user-provided centralized temp base (per-input subfolder)
        track_label = f"t{self.payload.track_index.index}"
        self.temp_dir = self._get_temp_dir(
            file_input,
            self.payload.temp_dir,
            track_label=track_label,
            keep_temp=self.payload.keep_temp,
        )
        logger.debug(f"Temp directory {self.temp_dir}.")

        # check disk space
        self._check_disk_space(
            input_file_path=file_input,
            drive_path=self.temp_dir,
            recommended_free_space=audio_track_info.recommended_free_space,
        )

        logger.debug(f"File paths: {output=}.")

        # early existence check: fail fast to avoid expensive work if the
        # destination already exists and the user didn't request overwrite.
        self._early_output_exists_check(output, self.payload.overwrite)

        # dee input path variable
        dee_input_path: Path | None = None

        # check if we're processing truehd atmos
        if self.payload.truehdd_path and audio_track_info.thd_atmos:
            # optionally stagger/jitter and limit concurrent TrueHD jobs
            self._maybe_jitter()
            self._acquire_truehdd()
            try:
                truehdd_signature = (
                    f"truehdd:{self.payload.thd_warp_mode.to_truehdd_cmd()}"
                )
                metadata_path = self._metadata_path_for_output(self.temp_dir, output)
                if getattr(
                    self.payload, "reuse_temp_files", False
                ) and self._check_reuse_signature(
                    metadata_path,
                    str(CodecFormat.ATMOS),
                    truehdd_signature,
                    "atmos_meta.atmos",
                    self.temp_dir,
                ):
                    dee_input_path = self.temp_dir / "atmos_meta.atmos"
                    logger.info("Reusing extracted wav from temp folder")
                else:
                    if not self.payload.truehdd_path:
                        raise DependencyNotFoundError(
                            "Failed to locate truehdd, this is required for TrueHD Atmos work flows"
                        )
                    dee_input_path = decode_truehd_to_atmos(
                        output_dir=self.temp_dir,
                        file_input=self.payload.file_input,
                        track_index=self.payload.track_index,
                        ffmpeg_path=self.payload.ffmpeg_path,
                        truehdd_path=self.payload.truehdd_path,
                        bed_conform=self.payload.bed_conform,
                        warp_mode=self.payload.thd_warp_mode,
                        duration=audio_track_info.duration,
                        step_info={"current": 1, "total": 3, "name": "truehdd"},
                        no_progress_bars=self.payload.no_progress_bars,
                    )
                    if getattr(self.payload, "reuse_temp_files", False):
                        self._write_signature_metadata(
                            metadata_path,
                            str(CodecFormat.ATMOS),
                            truehdd_signature,
                            "atmos_meta.atmos",
                            file_input,
                        )
            finally:
                self._release_truehdd()

        # check if we're processing adm atmos wav file
        elif audio_track_info.adm_atmos_wav:
            dee_input_path = file_input
            logger.info("Using ADM BWF input")

        # if it's anything raise an error
        else:
            raise InvalidAtmosInputError(
                "Cannot process input, not a valid Atmos format"
            )

        # generate JSON
        json_generator = DeeJSONGenerator(
            input_file_path=dee_input_path,
            output_file_path=output,
            output_dir=self.temp_dir,
            codec_format=CodecFormat.ATMOS,
        )
        json_path = json_generator.atmos_json(
            payload=self.payload,
            bitrate=runtime_bitrate,
            fps=fps,
            delay=delay,
            temp_dir=self.temp_dir,
            atmos_mode=self.payload.atmos_mode,
        )
        logger.debug(f"{json_path=}.")

        # generate DEE command
        dee_cmd = self.get_dee_json_cmd(
            dee_path=self.payload.dee_path, json_path=json_path
        )
        logger.debug(f"{dee_cmd=}.")

        # process dee command
        # optionally jitter and limit concurrent DEE jobs
        self._maybe_jitter()
        self._acquire_dee()
        try:
            step_info = {"current": 2, "total": 3, "name": "DEE measure"}
            _dee_job = process_dee_job(
                cmd=dee_cmd,
                step_info=step_info,
                no_progress_bars=self.payload.no_progress_bars,
                custom_dialnorm=self.payload.custom_dialnorm,
            )
        finally:
            self._release_dee()
        logger.debug(f"Dee job: {_dee_job}.")

        # return path
        if output.is_file():
            return output
        else:
            raise OutputFileNotFoundError(f"{output.name} output not found")

    def atmos_mode_resolver(self, _source_channels: int) -> AtmosMode:
        """For Atmos, mode doesn't change based on channels - return the payload mode."""
        return self.payload.atmos_mode

    def _generate_ffmpeg_cmd(self) -> list[str]:
        """Not used in AtmosEncoder."""
        raise NotImplementedError("_get_down_mix_config is not used in AtmosEncoder")

    @staticmethod
    def _get_channel_bitrate_object(
        desired_channels: AtmosMode, source_channels: int
    ) -> ChannelBitrates:
        return desired_channels.get_bitrate_obj()

    @staticmethod
    def _get_down_mix_config() -> str:
        """Not used in AtmosEncoder."""
        raise NotImplementedError("_get_down_mix_config is not used in AtmosEncoder")
