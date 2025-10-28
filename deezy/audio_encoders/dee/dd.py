from pathlib import Path

from deezy.audio_encoders.dee.base import BaseDeeAudioEncoder
from deezy.audio_encoders.dee.json.dee_json_generator import DeeJSONGenerator
from deezy.audio_processors.dee import process_dee_job
from deezy.audio_processors.ffmpeg import process_ffmpeg_job
from deezy.enums.codec_format import CodecFormat
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

    __slots__ = ()

    def __init__(self, payload: DDPayload):
        super().__init__(payload)
        self.payload: DDPayload
        logger.debug("Starting DDEncoder.")

    def _encode(self) -> Path:
        """Handles converting everything needed for DEE."""
        # file input
        file_input = Path(self.payload.file_input)
        self._check_input_file(file_input)

        # get audio track information
        mi_parser = MediainfoParser(file_input, self.payload.track_index)
        audio_track_info = mi_parser.get_audio_track_info()

        # if source channels is 5.0 and the user wants to up-mix to 5.1
        allow_50_to_51_upmix = (
            self.payload.upmix_50_to_51
            and self.payload.channels
            in (DolbyDigitalChannels.AUTO, DolbyDigitalChannels.SURROUND)
            and audio_track_info.channels == 5
        )

        # bitrate
        # get object based off of desired channels and source audio track channels
        usr_desired_channels = self.payload.channels
        # if we're allowing a 5.0 -> 5.1 upmix then force the channel to surround
        if allow_50_to_51_upmix:
            usr_desired_channels = DolbyDigitalChannels.SURROUND
        bitrate_obj = self._get_channel_bitrate_object(
            usr_desired_channels, audio_track_info.channels
        )

        # check to see if the users bitrate is allowed
        runtime_bitrate = self.get_config_based_bitrate(
            format_command=CodecFormat.DD,
            payload_bitrate=self.payload.bitrate,
            payload_channels=self.payload.channels,
            audio_track_info=audio_track_info,
            bitrate_obj=bitrate_obj,
            source_audio_channels=audio_track_info.channels,
            auto_enum_value=DolbyDigitalChannels.AUTO,
            channel_resolver=self.dd_channel_resolver,
        )

        # check for up-mixing if user has defined their own channel
        if (
            self.payload.channels is not DolbyDigitalChannels.AUTO
            and not allow_50_to_51_upmix
        ):
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
            if ".ac3" not in output.suffix:
                raise InvalidExtensionError(
                    "DD output must must end with the suffix '.ac3'."
                )
        else:
            # If an output template was provided, prefer rendering it. This is opt-in
            # and will be ignored if not present. Keep existing generate_output_filename
            # as the fallback to avoid changing default behavior.
            if self.payload.output_template:
                output = mi_parser.render_output_template(
                    template=str(self.payload.output_template),
                    suffix=".ac3",
                    output_channels=str(self.payload.channels),
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
                    suffix=".ac3",
                    output_channels=str(self.payload.channels),
                    worker_id=self.payload.worker_id,
                )

        # If a centralized batch output directory was provided and the user did not
        # explicitly supply an output path, place final output there. This ensures
        # an explicit --output wins over config-provided batch_output_dir.
        if self.payload.file_output is None and self.payload.batch_output_dir:
            output = Path(self.payload.batch_output_dir) / output.name
        logger.debug(f"Output path {output}.")

        # temp dir: prefer a user-provided centralized temp base (per-input subfolder)
        # prefer per-track stable temp dir when keep_temp is requested; otherwise
        # create a unique per-run temp dir (short random suffix)
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
        ffmpeg_down_mix = None
        if (
            # if downmix is off and not in dee's allowed inputs
            (down_mix_config == "off" and not dee_allowed_input)
            or
            # if downmix is off and desired channels is 2 and the user wants DPLII (DD doesn't support this)
            (
                down_mix_config == "off"
                and self.payload.channels is DolbyDigitalChannels.STEREO
                and self.payload.stereo_mix is StereoDownmix.DPLII
            )
            # if source channels is 5.0 and the user wants to up-mix to 5.1
            or (
                allow_50_to_51_upmix
                and audio_track_info.channels == 5
                and self.payload.channels is DolbyDigitalChannels.SURROUND
                and self.payload.upmix_50_to_51
            )
        ):
            ffmpeg_down_mix = self.payload.channels.value
            # log the mix
            if allow_50_to_51_upmix:
                logger.debug("FFMPEG upmix needed from 5.0 to 5.1.")
            else:
                logger.debug(f"FFMPEG downmix needed mix={ffmpeg_down_mix}.")

        # early existence check: fail fast to avoid expensive work if the
        # destination already exists and the user didn't request overwrite.
        self._early_output_exists_check(output, self.payload.overwrite)

        # temp filename deterministic per input file so adjacent temp folder is reusable
        wav_file_name = f"{output.stem}.{CodecFormat.DD}.wav"
        logger.debug(f"File paths: {wav_file_name=}, {output=}.")

        # generate ffmpeg cmd
        ffmpeg_cmd = self._generate_ffmpeg_cmd(
            ffmpeg_path=self.payload.ffmpeg_path,
            file_input=file_input,
            track_index=self.payload.track_index,
            sample_rate=audio_track_info.sample_rate,
            ffmpeg_down_mix=ffmpeg_down_mix,
            channels=self.payload.channels,
            stereo_down_mix=self.payload.stereo_mix,
            output_dir=self.temp_dir,
            wav_file_name=wav_file_name,
            allow_50_to_51_upmix=allow_50_to_51_upmix,
        )
        logger.debug(f"{ffmpeg_cmd=}.")

        # process ffmpeg command
        # optionally stagger/jitter and limit concurrent ffmpeg jobs
        self._maybe_jitter()
        self._acquire_ffmpeg()
        # reuse-temp-files support: check metadata.json in adjacent temp dir
        reuse_used = False
        metadata_path = self._metadata_path_for_output(self.temp_dir, output)
        # canonical signature for FFmpeg extraction is the exact command string
        signature = " ".join(map(str, ffmpeg_cmd))
        try:
            if getattr(self.payload, "reuse_temp_files", False):
                if self._check_reuse_signature(
                    metadata_path,
                    str(CodecFormat.DD),
                    signature,
                    wav_file_name,
                    self.temp_dir,
                ):
                    logger.info("Reusing extracted wav from adjacent temp folder")
                    reuse_used = True

            if not reuse_used:
                try:
                    _ffmpeg_job = process_ffmpeg_job(
                        cmd=ffmpeg_cmd,
                        steps=True,
                        duration=audio_track_info.duration,
                        step_info={"current": 1, "total": 3, "name": "FFMPEG"},
                        no_progress_bars=self.payload.no_progress_bars,
                    )
                finally:
                    self._release_ffmpeg()
                logger.debug(f"FFMPEG job: {_ffmpeg_job}.")

                # on success register metadata for reuse
                if getattr(self.payload, "reuse_temp_files", False):
                    self._write_signature_metadata(
                        metadata_path,
                        str(CodecFormat.DD),
                        signature,
                        wav_file_name,
                        file_input,
                    )
            else:
                # we acquired the ffmpeg semaphore but didn't run ffmpeg; release it
                try:
                    self._release_ffmpeg()
                except Exception:
                    pass
        except Exception:
            # ensure ffmpeg lock is released on unexpected errors
            try:
                self._release_ffmpeg()
            except Exception:
                pass

        # generate JSON
        json_generator = DeeJSONGenerator(
            input_file_path=self.temp_dir / wav_file_name,
            output_file_path=output,
            output_dir=self.temp_dir,
            codec_format=CodecFormat.DD,
        )
        json_path = json_generator.dd_json(
            payload=self.payload,
            downmix_mode_off=(
                ffmpeg_down_mix == 2
                and self.payload.stereo_mix is StereoDownmix.DPLII
                or allow_50_to_51_upmix
            ),
            bitrate=runtime_bitrate,
            fps=fps,
            delay=delay,
            temp_dir=self.temp_dir,
            dd_mode=DDEncodingMode.DD,
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
        ffmpeg_down_mix: int | None,
        channels: DolbyDigitalChannels,
        stereo_down_mix: StereoDownmix,
        output_dir: Path,
        wav_file_name: str,
        allow_50_to_51_upmix: bool,
    ) -> list[str]:
        bits_per_sample = 32
        dplii_filter = "aresample=matrix_encoding=dplii"
        pan_50_to_51 = "pan=5.1(side)|FL=c0|FR=c1|FC=c2|LFE=0*c0|SL=c3|SR=c4"
        resample_str = "aresample=resampler=soxr:precision=28:cutoff=1:dither_scale=0"
        resample, sample_rate = self._use_resampler(sample_rate)

        audio_filter_args = []
        if (
            channels is DolbyDigitalChannels.STEREO
            and stereo_down_mix is StereoDownmix.DPLII
        ):
            if resample:
                audio_filter_args.extend(
                    (
                        "-af",
                        f"{dplii_filter},{resample_str}",
                        "-ar",
                        str(sample_rate),
                    )
                )
            else:
                audio_filter_args.extend(
                    (
                        "-af",
                        dplii_filter,
                    )
                )
        # handle conversions from 5.0 -> 5.1 if user opts in
        elif allow_50_to_51_upmix:
            if resample:
                audio_filter_args.extend(
                    (
                        "-af",
                        f"{pan_50_to_51},{resample_str}",
                        "-ar",
                        str(sample_rate),
                    )
                )
            else:
                audio_filter_args.extend(
                    (
                        "-af",
                        pan_50_to_51,
                    )
                )
        else:
            if resample:
                audio_filter_args.extend(
                    (
                        "-af",
                        resample_str,
                        "-ar",
                        str(sample_rate),
                    )
                )

        # utilize ffmpeg to downmix for channels that aren't supported by DEE
        # allow_50_to_51_upmix doesn't need -ac arg, it's handled in the filter
        if (
            ffmpeg_down_mix and not allow_50_to_51_upmix
        ) or stereo_down_mix is StereoDownmix.DPLII:
            audio_filter_args.extend(("-ac", f"{ffmpeg_down_mix}"))

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
    def dd_channel_resolver(source_channels: int) -> DolbyDigitalChannels:
        """Resolve AUTO channels based on source channel count for DD."""
        if source_channels == 1:
            return DolbyDigitalChannels.MONO
        elif source_channels > 1 and source_channels < 6:
            return DolbyDigitalChannels.STEREO
        else:
            return DolbyDigitalChannels.SURROUND
