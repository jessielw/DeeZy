from pathlib import Path
import shutil
import tempfile

from deezy.audio_encoders.dee.base import BaseDeeAudioEncoder
from deezy.audio_encoders.dee.json.dee_json_generator import DeeJSONGenerator
from deezy.audio_processors.dee import process_dee_job
from deezy.audio_processors.ffmpeg import process_ffmpeg_job
from deezy.enums.dd import DolbyDigitalChannels
from deezy.enums.shared import DDEncodingMode, StereoDownmix
from deezy.exceptions import InvalidExtensionError, OutputFileNotFoundError
from deezy.payloads.dd import DDPayload
from deezy.payloads.shared import ChannelBitrates
from deezy.track_info.mediainfo import MediainfoParser
from deezy.track_info.track_index import TrackIndex
from deezy.utils.logger import logger


class DDEncoderDEE(BaseDeeAudioEncoder[DolbyDigitalChannels]):
    """Dolby Digital Encoder."""

    __slots__ = ("payload",)

    def __init__(self, payload: DDPayload):
        super().__init__()
        self.payload = payload
        logger.debug("Starting DDEncoder.")

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
            self.payload.channels, audio_track_info.channels
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

        # check for up-mixing if user has defined their own channel
        if self.payload.channels is not DolbyDigitalChannels.AUTO:
            self._check_for_up_mixing(
                audio_track_info.channels, self.payload.channels.value
            )

        # else if user has not defined their own channel, let's find the highest channel count
        # based on their input
        elif self.payload.channels is DolbyDigitalChannels.AUTO:
            audio_track_info.channels = self._determine_auto_channel_s(
                audio_track_info.channels, DolbyDigitalChannels.get_values_list()
            )

            # update payload channels enum to automatic channel selection
            self.payload.channels = DolbyDigitalChannels(audio_track_info.channels)
            logger.info(f"No supplied channels, defaulting to {self.payload.channels}.")

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

        # check to see if input channels are accepted by dee
        dee_allowed_input = self._dee_allowed_input(audio_track_info.channels)

        # downmix config
        down_mix_config = self._get_down_mix_config(
            self.payload.channels,
            audio_track_info.channels,
            self.payload.stereo_mix,
            dee_allowed_input,
        )
        logger.debug(f"Downmix config {down_mix_config}.")

        # determine if FFMPEG downmix is needed
        ffmpeg_down_mix = False
        if (down_mix_config == "off" and not dee_allowed_input) or (
            self.payload.channels is DolbyDigitalChannels.STEREO
            and self.payload.stereo_mix is StereoDownmix.DPLII
        ):
            ffmpeg_down_mix = self.payload.channels.value
            logger.debug(f"FFMPEG downmix needed {ffmpeg_down_mix}.")

        # file output (if an output is a defined check users extension and use their output)
        if self.payload.file_output:
            output = Path(self.payload.file_output)
            if ".ac3" not in output.suffix:
                raise InvalidExtensionError(
                    "DD output must must end with the suffix '.ac3'."
                )
        else:
            output = Path(audio_track_info.auto_name).with_suffix(".ac3")
        logger.debug(f"Output path {output}.")

        # define .wav and .ac3/.ec3 file names (not full path)
        wav_file_name = temp_filename + ".wav"
        output_file_name = temp_filename + ".ac3"
        output_file_path = temp_dir / output_file_name
        logger.debug(
            f"File paths: {wav_file_name=}, {output_file_name=}, {output_file_path=}."
        )

        # generate ffmpeg cmd
        ffmpeg_cmd = self._generate_ffmpeg_cmd(
            ffmpeg_path=self.payload.ffmpeg_path,
            file_input=file_input,
            track_index=self.payload.track_index,
            sample_rate=audio_track_info.sample_rate,
            ffmpeg_down_mix=ffmpeg_down_mix,
            channels=self.payload.channels,
            stereo_down_mix=self.payload.stereo_mix,
            output_dir=temp_dir,
            wav_file_name=wav_file_name,
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

        # generate JSON
        json_generator = DeeJSONGenerator(
            input_file_path=temp_dir / wav_file_name,
            output_file_path=output_file_path,
            output_dir=temp_dir,
        )
        json_path = json_generator.dd_json(
            payload=self.payload,
            bitrate=runtime_bitrate,
            fps=fps,
            delay=delay,
            temp_dir=temp_dir,
            dd_mode=DDEncodingMode.DD,
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

    @staticmethod
    def _get_channel_bitrate_object(
        desired_channels: DolbyDigitalChannels, source_channels: int
    ) -> ChannelBitrates:
        if desired_channels is DolbyDigitalChannels.AUTO:
            if source_channels == 1:
                return DolbyDigitalChannels.MONO.get_bitrate_obj()
            elif source_channels > 1 and source_channels < 6:
                return DolbyDigitalChannels.STEREO.get_bitrate_obj()
            else:
                return DolbyDigitalChannels.SURROUND.get_bitrate_obj()
        else:
            return desired_channels.get_bitrate_obj()

    @staticmethod
    def _get_down_mix_config(
        channels: DolbyDigitalChannels,
        input_channels: int,
        stereo_downmix: StereoDownmix,
        dee_allowed_input: bool,
    ) -> str:
        # if channels and input channels are the same or
        # channels are stereo and downmix is DPLII (fall back to using FFMPEG to mix the audio) or
        # not in dee allowed input return AUTO ("off").
        if (
            (channels.value == input_channels)
            or (
                channels is DolbyDigitalChannels.STEREO
                and stereo_downmix is StereoDownmix.DPLII
            )
            or not dee_allowed_input
        ):
            return DolbyDigitalChannels.AUTO.to_dee_cmd()
        elif channels in (
            DolbyDigitalChannels.MONO,
            DolbyDigitalChannels.STEREO,
            DolbyDigitalChannels.SURROUND,
        ):
            return channels.to_dee_cmd()
        return DolbyDigitalChannels.AUTO.to_dee_cmd()

    def _generate_ffmpeg_cmd(
        self,
        ffmpeg_path: Path,
        file_input: Path,
        track_index: TrackIndex,
        sample_rate: int | None,
        ffmpeg_down_mix: bool | int,
        channels: DolbyDigitalChannels,
        stereo_down_mix: StereoDownmix,
        output_dir: Path,
        wav_file_name: str,
    ) -> list[str]:
        # work out if we need to do a complex or simple resample
        bits_per_sample = 32
        if sample_rate and sample_rate != 48000:
            sample_rate = 48000
            resample = True
        else:
            resample = False

        # resample and add dplii
        audio_filter_args = []
        if (
            channels is DolbyDigitalChannels.STEREO
            and stereo_down_mix is StereoDownmix.DPLII
        ):
            if resample:
                audio_filter_args = [
                    "-af",
                    "aresample=matrix_encoding=dplii,aresample=resampler=soxr:precision=28:cutoff=1:dither_scale=0",
                    "-ar",
                    str(sample_rate),
                ]
            elif not resample:
                audio_filter_args = [
                    "-ac",
                    "2",
                    "-af",
                    "aresample=matrix_encoding=dplii",
                ]
        elif resample:
            audio_filter_args = [
                "-af",
                "aresample=resampler=soxr:precision=28:cutoff=1:dither_scale=0",
                "-ar",
                str(sample_rate),
            ]

        # utilize ffmpeg to downmix for channels that aren't supported by DEE
        if ffmpeg_down_mix or stereo_down_mix == StereoDownmix.DPLII:
            audio_filter_args.extend(["-ac", f"{ffmpeg_down_mix}"])

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
