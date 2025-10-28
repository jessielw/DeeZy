from pathlib import Path

from deezy.audio_encoders.dee.base import BaseDeeAudioEncoder
from deezy.audio_encoders.dee.json.dee_json_generator import DeeJSONGenerator
from deezy.audio_processors.dee import process_dee_job
from deezy.audio_processors.ffmpeg import process_ffmpeg_job
from deezy.enums.codec_format import CodecFormat
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

    __slots__ = ()

    def __init__(self, payload: DDPPayload):
        super().__init__(payload)
        self.payload: DDPPayload
        logger.debug("Starting DDPEncoder.")

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
            and self.payload.channels is DolbyDigitalPlusChannels.SURROUND
            and audio_track_info.channels == 5
        )

        # bitrate
        # get object based off of desired channels and source audio track channels
        usr_desired_channels = self.payload.channels
        # if we're allowing a 5.0 -> 5.1 upmix then force the channel to surround
        if allow_50_to_51_upmix:
            usr_desired_channels = DolbyDigitalPlusChannels.SURROUND
        bitrate_obj = self._get_channel_bitrate_object(
            usr_desired_channels, audio_track_info.channels
        )

        # check to see if the users bitrate is allowed
        # determine format command based on channel type
        format_command = (
            CodecFormat.DDP_BLURAY
            if isinstance(self.payload.channels, DolbyDigitalPlusBlurayChannels)
            else CodecFormat.DDP
        )
        runtime_bitrate = self.get_config_based_bitrate(
            format_command=format_command,
            payload_bitrate=self.payload.bitrate,
            payload_channels=self.payload.channels,
            audio_track_info=audio_track_info,
            bitrate_obj=bitrate_obj,
            source_audio_channels=audio_track_info.channels,
            auto_enum_value=DolbyDigitalPlusChannels.AUTO,
            channel_resolver=self.ddp_channel_resolver,
        )

        # check for up-mixing if user has defined their own channel
        if (
            self.payload.channels != DolbyDigitalPlusChannels.AUTO
            and not allow_50_to_51_upmix
        ):
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
                    output_channels=str(self.payload.channels),
                    delay_was_stripped=delay.is_delay(),
                    delay_relative_to_video=audio_track_info.delay_relative_to_video,
                    worker_id=self.payload.worker_id,
                )
                # If preview-only mode is enabled, log and return the rendered
                # path immediately so callers can display it without performing
                # any work or writing outputs.
                if self.payload.output_preview:
                    logger.info(f"Output preview: {output}")
                    return output
            else:
                output = mi_parser.generate_output_filename(
                    delay_was_stripped=delay.is_delay(),
                    delay_relative_to_video=audio_track_info.delay_relative_to_video,
                    suffix=".ec3",
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

        # deterministic temp filenames based on the final output stem and codec
        # include codec id so ddp and ddp-bluray use separate temp artifacts
        wav_file_name = f"{output.stem}.{format_command}.wav"
        logger.debug(f"File paths: {wav_file_name=}, {output=}.")

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
        ffmpeg_down_mix = None
        # if downmix is off and not in dee's allowed inputs or we're doing a 50 to 51 upmix
        if down_mix_config == "off" and not dee_allowed_input or allow_50_to_51_upmix:
            # if user left channels AUTO (should be resolved earlier), fall back to detected input channels
            if self.payload.channels is DolbyDigitalPlusChannels.AUTO:
                ffmpeg_down_mix = audio_track_info.channels
            else:
                ffmpeg_down_mix = self.payload.channels.value

            # log the mix
            if allow_50_to_51_upmix:
                logger.debug("FFMPEG upmix needed from 5.0 to 5.1.")
            else:
                logger.debug(f"FFMPEG downmix needed mix={ffmpeg_down_mix}.")

        # early existence check: fail fast to avoid expensive work if the
        # destination already exists and the user didn't request overwrite.
        self._early_output_exists_check(output, self.payload.overwrite)

        # generate ffmpeg cmd
        ffmpeg_cmd = self._generate_ffmpeg_cmd(
            ffmpeg_path=self.payload.ffmpeg_path,
            file_input=file_input,
            track_index=self.payload.track_index,
            sample_rate=audio_track_info.sample_rate,
            ffmpeg_down_mix=ffmpeg_down_mix,
            channels=self.payload.channels,
            output_dir=self.temp_dir,
            wav_file_name=wav_file_name,
            allow_50_to_51_upmix=allow_50_to_51_upmix,
        )
        logger.debug(f"{ffmpeg_cmd=}.")

        # process ffmpeg command
        # optionally stagger/jitter and limit concurrent ffmpeg jobs
        self._maybe_jitter()
        self._acquire_ffmpeg()
        reuse_used = False
        # DDP uses temp_dir in system/user temp; metadata naming still uses output stem
        metadata_path = self._metadata_path_for_output(self.temp_dir, output)
        try:
            if getattr(self.payload, "reuse_temp_files", False):
                meta = self._read_reuse_metadata(metadata_path) or {}
                encs = meta.get("encoders") or {}
                enc_entry = encs.get(str(format_command))
                sig = " ".join(map(str, ffmpeg_cmd))
                if enc_entry and enc_entry.get("signature") == sig:
                    recorded_file = enc_entry.get("produced_file")
                    if recorded_file and (self.temp_dir / recorded_file).exists():
                        logger.info("Reusing extracted wav from temp folder")
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

                if getattr(self.payload, "reuse_temp_files", False):
                    self._write_signature_metadata(
                        metadata_path,
                        str(format_command),
                        " ".join(map(str, ffmpeg_cmd)),
                        wav_file_name,
                        file_input,
                    )
        except Exception:
            try:
                self._release_ffmpeg()
            except Exception:
                pass

        # generate JSON
        json_generator = DeeJSONGenerator(
            input_file_path=self.temp_dir / wav_file_name,
            output_file_path=output,
            output_dir=self.temp_dir,
            codec_format=format_command,
        )
        json_path = json_generator.dd_json(
            payload=self.payload,
            downmix_mode_off=False,
            bitrate=runtime_bitrate,
            fps=fps,
            delay=delay,
            temp_dir=self.temp_dir,
            dd_mode=self._determine_output_mode(),
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
        ffmpeg_down_mix: int | None,
        output_dir: Path,
        wav_file_name: str,
        allow_50_to_51_upmix: bool,
    ) -> list[str]:
        bits_per_sample = 32
        pan_50_to_51 = "pan=5.1(side)|FL=c0|FR=c1|FC=c2|LFE=0*c0|SL=c3|SR=c4"
        pan_7_1 = "pan=7.1|c0=c0|c1=c1|c2=c2|c3=c3|c4=c6|c5=c7|c6=c4|c7=c5"
        resample_str = "aresample=resampler=soxr:precision=28:cutoff=1:dither_scale=0"
        resample, sample_rate = self._use_resampler(sample_rate)
        is_bluray = isinstance(channels, DolbyDigitalPlusBlurayChannels)
        is_surround_ex = (
            channels == DolbyDigitalPlusChannels.SURROUNDEX if not is_bluray else True
        )

        audio_filter_args = []
        if is_surround_ex:
            if resample:
                audio_filter_args.extend(
                    (
                        "-af",
                        f"{pan_7_1},{resample_str}",
                        "-ar",
                        str(sample_rate),
                    )
                )
            else:
                audio_filter_args.extend(
                    (
                        "-af",
                        pan_7_1,
                    )
                )
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
        if ffmpeg_down_mix and not allow_50_to_51_upmix:
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

    def _determine_output_mode(self) -> DDEncodingMode:
        if isinstance(self.payload.channels, DolbyDigitalPlusBlurayChannels):
            return DDEncodingMode.BLURAY
        else:
            if self.payload.channels.value == 8:
                return DDEncodingMode.DDP71
            else:
                return DDEncodingMode.DDP

    @staticmethod
    def ddp_channel_resolver(source_channels: int) -> DolbyDigitalPlusChannels:
        """Resolve AUTO channels based on source channel count for DDP."""
        if source_channels == 1:
            return DolbyDigitalPlusChannels.MONO
        elif source_channels > 1 and source_channels < 6:
            return DolbyDigitalPlusChannels.STEREO
        elif source_channels == 6:
            return DolbyDigitalPlusChannels.SURROUND
        else:
            return DolbyDigitalPlusChannels.SURROUNDEX
