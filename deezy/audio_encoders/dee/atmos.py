from pathlib import Path
import shutil
import tempfile

from deezy.audio_encoders.dee.base import BaseDeeAudioEncoder
from deezy.audio_encoders.dee.json.dee_json_generator import DeeJSONGenerator
from deezy.audio_processors.dee import process_dee_job
from deezy.audio_processors.truehdd import decode_truehd_to_atmos
from deezy.enums.atmos import AtmosMode
from deezy.exceptions import InvalidExtensionError, OutputFileNotFoundError
from deezy.exceptions import DependencyNotFoundError
from deezy.payloads.atmos import AtmosPayload
from deezy.payloads.shared import ChannelBitrates
from deezy.track_info.mediainfo import MediainfoParser
from deezy.utils.logger import logger


class AtmosEncoder(BaseDeeAudioEncoder[AtmosMode]):
    """Atmos Encoder."""

    __slots__ = ("payload",)

    def __init__(self, payload: AtmosPayload):
        super().__init__()
        self.payload = payload
        logger.debug("Starting Atmos Encoder.")

    def encode(self):
        """Handles converting everything needed for DEE."""
        # file input
        file_input = Path(self.payload.file_input)
        self._check_input_file(file_input)

        # get audio track information
        audio_track_info = MediainfoParser(
            file_input, self.payload.track_index
        ).get_audio_track_info()

        # bitrate
        # get object based off of desired channels and source audio track channels
        bitrate_obj = self._get_channel_bitrate_object(
            self.payload.atmos_mode, audio_track_info.channels
        )
        # check to see if the users bitrate is allowed
        runtime_bitrate = self.payload.bitrate
        if runtime_bitrate:
            # user/preset provided a bitrate - validate it
            if not bitrate_obj.is_valid_bitrate(runtime_bitrate):
                fixed_bitrate = bitrate_obj.get_closest_bitrate(runtime_bitrate)
                logger.warning(
                    f"Bitrate {runtime_bitrate} is invalid for this configuration. "
                    f"Using the next closest allowed bitrate: {fixed_bitrate}."
                )
                runtime_bitrate = fixed_bitrate
            else:
                logger.debug(f"Using provided bitrate: {runtime_bitrate}.")
        else:
            # no bitrate provided - use default
            runtime_bitrate = bitrate_obj.default
            logger.debug(f"No supplied bitrate, defaulting to {runtime_bitrate}.")

        # check for up-mixing
        self._check_for_up_mixing(
            audio_track_info.channels, self.payload.atmos_mode.get_channels()
        )

        # delay
        delay = self.get_delay(audio_track_info, self.payload.delay, file_input)

        # fps
        fps = self._get_fps(audio_track_info.fps)
        logger.debug(f"Detected FPS {fps.to_dee_cmd()}.")

        # temp dir
        temp_dir = self._get_temp_dir(file_input, self.payload.temp_dir)
        logger.debug(f"Temp directory {temp_dir}.")

        # check disk space
        self._check_disk_space(
            input_file_path=file_input,
            drive_path=temp_dir,
            recommended_free_space=audio_track_info.recommended_free_space,
        )

        # temp filename
        temp_filename = Path(tempfile.NamedTemporaryFile(delete=False).name).name
        logger.debug(f"Temp filename {temp_filename}.")

        # file output (if an output is a defined check users extension and use their output)
        if self.payload.file_output:
            output = Path(self.payload.file_output)
            if output.suffix not in (".ec3", ".eac3"):
                raise InvalidExtensionError(
                    "DDP output must must end with the suffix '.eac3' or '.ec3'."
                )
        else:
            output = Path(audio_track_info.auto_name).with_suffix(".ec3")
        logger.debug(f"Output path {output}.")

        # define .ac3 file names (not full path) and output path
        output_file_name = temp_filename + ".ac3"
        output_file_path = temp_dir / output_file_name
        logger.debug(f"File paths: {output_file_name=}, {output_file_path=}.")

        # decode TrueHD to atmos mezz
        if not self.payload.truehdd_path:
            raise DependencyNotFoundError(
                "Failed to locate truehdd, this is required for atmos work flows"
            )
        decoded_mezz_path = decode_truehd_to_atmos(
            output_dir=temp_dir,
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

        # generate JSON
        json_generator = DeeJSONGenerator(
            input_file_path=decoded_mezz_path,
            output_file_path=output_file_path,
            output_dir=temp_dir,
        )
        json_path = json_generator.atmos_json(
            payload=self.payload,
            bitrate=runtime_bitrate,
            fps=fps,
            delay=delay,
            temp_dir=temp_dir,
            atmos_mode=self.payload.atmos_mode,
        )
        logger.debug(f"{json_path=}.")

        # generate DEE command
        dee_cmd = self.get_dee_json_cmd(
            dee_path=self.payload.dee_path, json_path=json_path
        )
        logger.debug(f"{dee_cmd=}.")

        # process dee command
        step_info = {"current": 2, "total": 3, "name": "DEE measure"}
        _dee_job = process_dee_job(
            cmd=dee_cmd,
            step_info=step_info,
            no_progress_bars=self.payload.no_progress_bars,
        )
        logger.debug(f"Dee job: {_dee_job}.")

        # move file to output path
        logger.debug(f"Moving {output_file_path.name} to {output}.")
        move_file = Path(shutil.move(output_file_path, output))
        logger.debug("Done.")

        # delete temp folder and all files if enabled
        if not self.payload.keep_temp:
            logger.debug(f"Cleaning temp directory ({temp_dir}).")
            self._clean_temp(temp_dir, self.payload.keep_temp)
            logger.debug("Temp directory cleaned.")

        # return path
        if move_file.is_file():
            return move_file
        else:
            raise OutputFileNotFoundError(f"{move_file.name} output not found")

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
