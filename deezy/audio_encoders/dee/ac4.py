from pathlib import Path
import shutil
import tempfile

from deezy.audio_encoders.dee.base import BaseDeeAudioEncoder
from deezy.audio_encoders.dee.json.dee_json_generator import DeeJSONGenerator
from deezy.audio_processors.dee import process_dee_job
from deezy.audio_processors.ffmpeg import process_ffmpeg_job
from deezy.audio_processors.truehdd import decode_truehd_to_atmos
from deezy.enums.ac4 import Ac4Channels
from deezy.exceptions import (
    ChannelMixError,
    DependencyNotFoundError,
    InvalidExtensionError,
    OutputFileNotFoundError,
)
from deezy.payloads.ac4 import Ac4Payload
from deezy.payloads.shared import ChannelBitrates
from deezy.track_info.mediainfo import MediainfoParser
from deezy.track_info.track_index import TrackIndex
from deezy.utils.logger import logger


class Ac4Encoder(BaseDeeAudioEncoder[Ac4Channels]):
    """AC4 Encoder."""

    __slots__ = ("payload",)

    def __init__(self, payload: Ac4Payload):
        super().__init__()
        self.payload = payload
        logger.debug("Starting Ac4 Encoder.")

    def encode(self):
        """Handles converting everything needed for DEE."""
        # file input
        file_input = Path(self.payload.file_input)
        self._check_input_file(file_input)

        # get audio track information
        audio_track_info = MediainfoParser(
            file_input, self.payload.track_index
        ).get_audio_track_info()

        # ensure we have truehd atmos OR => 6 channel audio
        if audio_track_info.thd_atmos:
            logger.debug("Input track is TrueHD Atmos")
        elif not audio_track_info.thd_atmos and audio_track_info.channels < 6:
            raise ChannelMixError(
                "[Ac3Encoder] Failed to encode. Audio track should either be >= 6 channels "
                f"or TrueHD Atmos (track channels: {audio_track_info.channels})"
            )

        # bitrate
        # get object based off of desired channels and source audio track channels
        bitrate_obj = Ac4Channels.IMMERSIVE_STEREO.get_bitrate_obj()
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
            if output.suffix != ".ac4":
                raise InvalidExtensionError(
                    "Ac4 output must must end with the suffix '.ac4'."
                )
        else:
            output = Path(audio_track_info.auto_name).with_suffix(".ac4")
        logger.debug(f"Output path {output}.")

        # define .wav and .ac4 file names (not full path)
        wav_file_name = temp_filename + ".wav"
        output_file_name = temp_filename + ".ac4"
        output_file_path = temp_dir / output_file_name
        logger.debug(f"File paths: {output_file_name=}, {output_file_path=}.")

        # decode TrueHD to atmos mezz
        if audio_track_info.thd_atmos:
            if not self.payload.truehdd_path:
                raise DependencyNotFoundError(
                    "Failed to locate truehdd, this is required for atmos work flows"
                )
            input_file_path = decode_truehd_to_atmos(
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
        # if not truehd we know it's valid channel based audio since we checked above
        else:
            # generate ffmpeg cmd
            ffmpeg_cmd = self._generate_ffmpeg_cmd(
                ffmpeg_path=self.payload.ffmpeg_path,
                file_input=file_input,
                track_index=self.payload.track_index,
                sample_rate=audio_track_info.sample_rate,
                output_dir=temp_dir,
                wav_file_name=wav_file_name,
                audio_channels=audio_track_info.channels,
            )
            logger.debug(f"{ffmpeg_cmd=}.")

            # process ffmpeg command
            _ffmpeg_job = process_ffmpeg_job(
                cmd=ffmpeg_cmd,
                steps=True,
                duration=audio_track_info.duration,
                step_info={"current": 1, "total": 3, "name": "FFMPEG"},
                no_progress_bars=self.payload.no_progress_bars,
            )
            logger.debug(f"FFMPEG job: {_ffmpeg_job}.")
            input_file_path = Path(temp_dir / wav_file_name)

        # generate JSON
        json_generator = DeeJSONGenerator(
            input_file_path=input_file_path,
            output_file_path=output_file_path,
            output_dir=temp_dir,
        )
        json_path = json_generator.ac4_json(
            payload=self.payload,
            bitrate=runtime_bitrate,
            fps=fps,
            delay=delay,
            temp_dir=temp_dir,
        )
        logger.debug(f"{json_path=}.")

        # generate DEE command
        dee_cmd = self.get_dee_json_cmd(
            dee_path=self.payload.dee_path, json_path=json_path
        )
        logger.debug(f"{dee_cmd=}.")

        # process dee command
        _dee_job = process_dee_job(
            cmd=dee_cmd,
            step_info={"current": 2, "total": 3, "name": "DEE measure"},
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

    def _generate_ffmpeg_cmd(
        self,
        ffmpeg_path: Path,
        file_input: Path,
        track_index: TrackIndex,
        sample_rate: int | None,
        output_dir: Path,
        wav_file_name: str,
        audio_channels: int,
    ) -> list[str]:
        bits_per_sample = 32
        pan_7_1 = "pan=7.1|c0=c0|c1=c1|c2=c2|c3=c3|c4=c6|c5=c7|c6=c4|c7=c5"
        resample_str = "aresample=resampler=soxr:precision=28:cutoff=1:dither_scale=0"
        audio_filter_args = []

        # work out if we need to do a complex or simple resample
        if sample_rate and sample_rate != 48000:
            sample_rate = 48000
            resample = True
        else:
            resample = False

        if audio_channels == 8:
            if resample:
                audio_filter_args = [
                    "-af",
                    f"{pan_7_1},{resample_str}",
                    "-ar",
                    str(sample_rate),
                ]
            else:
                audio_filter_args = [
                    "-af",
                    pan_7_1,
                ]
        elif resample:
            audio_filter_args = [
                "-af",
                resample_str,
                "-ar",
                str(sample_rate),
            ]

        # ac4 requires 6 channel input, so we'll downmix to that
        if audio_channels != 6:
            audio_filter_args.extend(["-ac", "6"])

        # base ffmpeg command
        ffmpeg_cmd = self._get_ffmpeg_cmd(
            ffmpeg_path,
            file_input,
            track_index,
            bits_per_sample,
            audio_filter_args,
            output_dir,
            wav_file_name,
        )

        return ffmpeg_cmd

    @staticmethod
    def _get_channel_bitrate_object(
        desired_channels: Ac4Channels, source_channels: int
    ) -> ChannelBitrates:
        raise NotImplementedError(
            "_get_channel_bitrate_object is not used in Ac4Encoder"
        )

    @staticmethod
    def _get_down_mix_config() -> str:
        """Not used in Ac4Encoder."""
        raise NotImplementedError("_get_down_mix_config is not used in Ac4Encoder")
