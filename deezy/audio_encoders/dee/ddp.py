from pathlib import Path
import shutil
import tempfile

from deezy.audio_encoders.dee.base import BaseDeeAudioEncoder
from deezy.audio_encoders.dee.json.dee_json_generator import DeeJSONGenerator
from deezy.audio_processors.dee import process_dee_job
from deezy.audio_processors.ffmpeg import process_ffmpeg_job
from deezy.enums.ddp import DolbyDigitalPlusChannels
from deezy.enums.ddp_bluray import DolbyDigitalPlusBlurayChannels
from deezy.enums.shared import DDEncodingMode, StereoDownmix
from deezy.exceptions import InvalidExtensionError, OutputFileNotFoundError
from deezy.payloads.ddp import DDPPayload
from deezy.payloads.shared import ChannelBitrates
from deezy.track_info.mediainfo import MediainfoParser
from deezy.track_info.track_index import TrackIndex
from deezy.utils.logger import logger


class DDPEncoderDEE(BaseDeeAudioEncoder[DolbyDigitalPlusChannels]):
    """Dolby Digital Plus Encoder."""

    __slots__ = ("payload",)

    def __init__(self, payload: DDPPayload):
        super().__init__()
        self.payload = payload
        logger.debug("Starting DDPEncoder.")

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
        if self.payload.channels != DolbyDigitalPlusChannels.AUTO:
            self._check_for_up_mixing(
                audio_track_info.channels, self.payload.channels.value
            )

        # else if user has not defined their own channel, let's find the highest channel count
        # based on their input
        elif self.payload.channels is DolbyDigitalPlusChannels.AUTO:
            audio_track_info.channels = self._determine_auto_channel_s(
                audio_track_info.channels, DolbyDigitalPlusChannels.get_values_list()
            )

            # update self.payload channels enum to automatic channel selection
            self.payload.channels = DolbyDigitalPlusChannels(audio_track_info.channels)
            logger.info(f"No supplied channels, defaulting to {self.payload.channels}.")

        # delay
        delay = self.get_delay(audio_track_info, self.payload.delay, file_input)

        # fps
        fps = self._get_fps(audio_track_info.fps)
        logger.debug(f"Detected FPS {fps.to_dee_cmd()}.")

        # output dir
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

        # determine if FFMPEG downmix is needed for unsupported channels
        ffmpeg_down_mix = False
        if down_mix_config == "off" and not dee_allowed_input:
            # if user left channels AUTO (should be resolved earlier), fall back to detected input channels
            if self.payload.channels is DolbyDigitalPlusChannels.AUTO:
                ffmpeg_down_mix = audio_track_info.channels
            else:
                ffmpeg_down_mix = self.payload.channels.value

        # file output (if an output is a defined check users extension and use their output)
        if self.payload.file_output:
            output = Path(self.payload.file_output)
            if output.suffix not in (".ec3", ".eac3"):
                raise InvalidExtensionError(
                    "DDP output must must end with the suffix '.eac3' or '.ec3'."
                )
        else:
            output = Path(audio_track_info.auto_name).with_suffix(".ec3")

        # define .wav and .ac3/.ec3 file names (not full path)
        wav_file_name = temp_filename + ".wav"
        output_file_name = temp_filename + output.suffix
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
            dd_mode=self._determine_output_mode(),
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
        desired_channels: DolbyDigitalPlusChannels | DolbyDigitalPlusBlurayChannels,
        source_channels: int,
    ) -> ChannelBitrates:
        # handle DolbyDigitalPlusBlurayChannels
        if isinstance(desired_channels, DolbyDigitalPlusBlurayChannels):
            return DolbyDigitalPlusBlurayChannels.SURROUNDEX.get_bitrate_obj()

        # handle normal DolbyDigitalPlusChannels
        if desired_channels is DolbyDigitalPlusChannels.AUTO:
            if source_channels == 1:
                return DolbyDigitalPlusChannels.MONO.get_bitrate_obj()
            elif source_channels > 1 and source_channels < 6:
                return DolbyDigitalPlusChannels.STEREO.get_bitrate_obj()
            elif source_channels == 6:
                return DolbyDigitalPlusChannels.SURROUND.get_bitrate_obj()
            else:
                return DolbyDigitalPlusChannels.SURROUNDEX.get_bitrate_obj()
        else:
            return desired_channels.get_bitrate_obj()

    @staticmethod
    def _get_down_mix_config(
        channels: DolbyDigitalPlusChannels | DolbyDigitalPlusBlurayChannels,
        input_channels: int,
        stereo_downmix: StereoDownmix,
        dee_allowed_input: bool,
    ) -> str:
        # handle DolbyDigitalPlusBlurayChannels
        if isinstance(channels, DolbyDigitalPlusBlurayChannels):
            return channels.to_dee_cmd()

        # handle normal DolbyDigitalPlusChannels
        if channels.value == input_channels or not dee_allowed_input:
            return DolbyDigitalPlusChannels.AUTO.to_dee_cmd()
        return channels.to_dee_cmd()

    def _generate_ffmpeg_cmd(
        self,
        ffmpeg_path: Path,
        file_input: Path,
        track_index: TrackIndex,
        sample_rate: int | None,
        channels: DolbyDigitalPlusChannels | DolbyDigitalPlusBlurayChannels,
        ffmpeg_down_mix: bool | int,
        output_dir: Path,
        wav_file_name: str,
    ) -> list[str]:
        bits_per_sample = 32
        pan_7_1 = "pan=7.1|c0=c0|c1=c1|c2=c2|c3=c3|c4=c6|c5=c7|c6=c4|c7=c5"
        resample_str = "aresample=resampler=soxr:precision=28:cutoff=1:dither_scale=0"
        audio_filter_args = []

        is_bluray = isinstance(channels, DolbyDigitalPlusBlurayChannels)
        is_surround_ex = (
            channels == DolbyDigitalPlusChannels.SURROUNDEX if not is_bluray else True
        )

        # work out if we need to do a complex or simple resample
        if sample_rate and sample_rate != 48000:
            sample_rate = 48000
            resample = True
        else:
            resample = False

        if is_surround_ex:
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

        # utilize ffmpeg to downmix for channels that aren't supported by DEE
        if ffmpeg_down_mix:
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

    def _determine_output_mode(self) -> DDEncodingMode:
        if isinstance(self.payload.channels, DolbyDigitalPlusBlurayChannels):
            return DDEncodingMode.BLURAY
        else:
            if self.payload.channels.value == 8:
                return DDEncodingMode.DDP71
            else:
                return DDEncodingMode.DDP
