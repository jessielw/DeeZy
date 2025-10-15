from pathlib import Path

from deezy.audio_encoders.dee.base import BaseDeeAudioEncoder
from deezy.audio_encoders.dee.json.dee_json_generator import DeeJSONGenerator
from deezy.audio_processors.dee import process_dee_job
from deezy.audio_processors.ffmpeg import process_ffmpeg_job
from deezy.audio_processors.truehdd import decode_truehd_to_atmos
from deezy.enums.ac4 import Ac4Channels
from deezy.enums.codec_format import CodecFormat
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

    __slots__ = ()

    def __init__(self, payload: Ac4Payload):
        super().__init__(payload)
        self.payload: Ac4Payload
        logger.debug("Starting Ac4 Encoder.")

    def _encode(self) -> Path:
        """Handles converting everything needed for DEE."""
        # file input
        file_input = Path(self.payload.file_input)
        self._check_input_file(file_input)

        # get audio track information
        mi_parser = MediainfoParser(file_input, self.payload.track_index)
        audio_track_info = mi_parser.get_audio_track_info()

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
        runtime_bitrate = self.get_config_based_bitrate(
            format_command=CodecFormat.AC4,
            payload_bitrate=self.payload.bitrate,
            payload_channels=Ac4Channels.IMMERSIVE_STEREO,
            audio_track_info=audio_track_info,
            bitrate_obj=bitrate_obj,
            source_audio_channels=audio_track_info.channels,
            auto_enum_value=None,  # AC4 doesn't have AUTO
            channel_resolver=self.ac4_channel_resolver,
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
            if output.suffix != ".ac4":
                raise InvalidExtensionError(
                    "Ac4 output must must end with the suffix '.ac4'."
                )
        else:
            # If an output template was provided, prefer rendering it. This is opt-in
            # and will be ignored if not present. Keep existing generate_output_filename
            # as the fallback to avoid changing default behavior.
            if self.payload.output_template:
                output = mi_parser.render_output_template(
                    template=str(self.payload.output_template),
                    suffix=".ac4",
                    output_channels="2.0",
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
                    suffix=".ac4",
                    output_channels="2.0",
                    worker_id=self.payload.worker_id,
                )

        # if a centralized batch output directory was provided and the user did not
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

        # deterministic temp filenames based on final output stem
        wav_file_name = f"{output.stem}.{CodecFormat.AC4}.wav"
        logger.debug(f"File paths: {wav_file_name=}, {output=}.")

        # early existence check: fail fast to avoid expensive work if the
        # destination already exists and the user didn't request overwrite.
        self._early_output_exists_check(output, self.payload.overwrite)

        # decode TrueHD to atmos mezz
        if self.payload.truehdd_path and audio_track_info.thd_atmos:
            # optionally stagger/jitter and limit concurrent TrueHD jobs
            self._maybe_jitter()
            self._acquire_truehdd()
            try:
                # for TrueHD we can reuse if the signature matches the truehdd command
                truehdd_signature = (
                    f"truehdd:{self.payload.thd_warp_mode.to_truehdd_cmd()}"
                )
                metadata_path = self._metadata_path_for_output(self.temp_dir, output)
                if getattr(
                    self.payload, "reuse_temp_files", False
                ) and self._check_reuse_signature(
                    metadata_path,
                    str(CodecFormat.AC4),
                    truehdd_signature,
                    "atmos_meta.atmos",
                    self.temp_dir,
                ):
                    logger.info("Reusing decoded atmos from temp folder")
                    decoded_mezz_path = self.temp_dir / "atmos_meta.atmos"
                else:
                    if not self.payload.truehdd_path:
                        raise DependencyNotFoundError(
                            "Failed to locate truehdd, this is required for atmos work flows"
                        )
                    decoded_mezz_path = decode_truehd_to_atmos(
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
                # register metadata on success
                if getattr(self.payload, "reuse_temp_files", False):
                    self._write_signature_metadata(
                        metadata_path,
                        str(CodecFormat.AC4),
                        truehdd_signature,
                        "atmos_meta.atmos",
                        file_input,
                    )
            finally:
                self._release_truehdd()
            # make input_file_path point to the decoded mezz when TrueHD path used
            input_file_path = decoded_mezz_path

        # check if we're processing adm atmos wav file
        elif audio_track_info.adm_atmos_wav:
            input_file_path = file_input
            logger.info("Using ADM BWF input")

        # if not truehd/adm we know it's valid channel based audio since we checked above
        else:
            # generate ffmpeg cmd
            ffmpeg_cmd = self._generate_ffmpeg_cmd(
                ffmpeg_path=self.payload.ffmpeg_path,
                file_input=file_input,
                track_index=self.payload.track_index,
                sample_rate=audio_track_info.sample_rate,
                output_dir=self.temp_dir,
                wav_file_name=wav_file_name,
                audio_channels=audio_track_info.channels,
            )
            logger.debug(f"{ffmpeg_cmd=}.")

            # process ffmpeg command
            # optionally stagger/jitter and limit concurrent ffmpeg jobs
            self._maybe_jitter()
            self._acquire_ffmpeg()
            reuse_used = False
            metadata_path = self._metadata_path_for_output(self.temp_dir, output)

            try:
                if getattr(
                    self.payload, "reuse_temp_files", False
                ) and self._check_reuse_signature(
                    metadata_path,
                    str(CodecFormat.AC4),
                    " ".join(map(str, ffmpeg_cmd)),
                    wav_file_name,
                    self.temp_dir,
                ):
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

                    # on success register metadata for reuse
                    if getattr(self.payload, "reuse_temp_files", False):
                        self._write_signature_metadata(
                            metadata_path,
                            str(CodecFormat.AC4),
                            " ".join(map(str, ffmpeg_cmd)),
                            wav_file_name,
                            file_input,
                        )
            except Exception:
                try:
                    self._release_ffmpeg()
                except Exception:
                    pass
            input_file_path = Path(self.temp_dir / wav_file_name)

        # generate JSON
        json_generator = DeeJSONGenerator(
            input_file_path=input_file_path,
            output_file_path=output,
            output_dir=self.temp_dir,
            codec_format=CodecFormat.AC4,
        )
        json_path = json_generator.ac4_json(
            payload=self.payload,
            bitrate=runtime_bitrate,
            fps=fps,
            delay=delay,
            temp_dir=self.temp_dir,
            atmos_enabled=bool(
                audio_track_info.adm_atmos_wav or audio_track_info.thd_atmos
            ),
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
            _dee_job = process_dee_job(
                cmd=dee_cmd,
                step_info={"current": 2, "total": 3, "name": "DEE measure"},
                no_progress_bars=self.payload.no_progress_bars,
            )
        finally:
            self._release_dee()
        logger.debug(f"Dee job: {_dee_job}.")

        # return path
        if output.is_file():
            return output
        else:
            raise OutputFileNotFoundError(f"{output.name} output not found")

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

    @staticmethod
    def ac4_channel_resolver(_source_channels: int) -> Ac4Channels:
        """AC4 doesn't have AUTO channel resolution - return fixed channel."""
        return Ac4Channels.IMMERSIVE_STEREO
