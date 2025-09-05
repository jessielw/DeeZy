from collections.abc import Sequence
from pathlib import Path
import shutil
import tempfile

from deezy.audio_encoders.dee.base import BaseDeeAudioEncoder
from deezy.audio_encoders.dee.bitrates import dee_ddp_bitrates
from deezy.audio_encoders.dee.xml.xml import DeeXMLGenerator
from deezy.audio_encoders.delay import DelayGenerator
from deezy.audio_processors.dee import process_dee_job
from deezy.audio_processors.ffmpeg import process_ffmpeg_job
from deezy.audio_processors.truehdd import decode_truehd_to_atmos
from deezy.enums.ddp import DolbyDigitalPlusChannels
from deezy.exceptions import InvalidExtensionError, OutputFileNotFoundError
from deezy.payloads.ddp import DDPPayload
from deezy.track_info.mediainfo import MediainfoParser


class DDPEncoderDEE(BaseDeeAudioEncoder[DolbyDigitalPlusChannels]):
    def __init__(self, payload: DDPPayload):
        super().__init__()
        self.payload = payload

    def encode(self):
        # convert for dee XML
        # file input
        file_input = Path(self.payload.file_input)
        self._check_input_file(file_input)

        # get audio track information
        audio_track_info = MediainfoParser(
            file_input, self.payload.track_index
        ).get_audio_track_info()

        # if user selected an Atmos channel but did NOT enable --atmos, treat as non‑Atmos:
        if self.payload.channels.is_atmos() and not self.payload.atmos:
            # replace Atmos enum with its non-Atmos fallback (e.g. ATMOS_5_1_4 -> SURROUND)
            self.payload.channels = self.payload.channels.get_fallback_layout()

        # check if user requested Atmos and handle fallbacks as needed
        if self.payload.atmos:
            if not self.payload.channels.is_atmos():
                # user enabled --atmos but didn't select an Atmos channel -> disable flag
                self.payload.atmos = False
            elif not audio_track_info.thd_atmos:
                # user requested Atmos (flag + Atmos channel) but source has no THD Atmos -> disable and fallback
                self.payload.atmos = False
                self.payload.channels = self.payload.channels.get_fallback_layout()

        # bitrate
        bitrate = str(
            self._get_closest_allowed_bitrate(
                bitrate=self.payload.bitrate,
                accepted_bitrates=self._get_accepted_bitrates(
                    desired_channels=self.payload.channels,
                    source_channels=int(audio_track_info.channels),
                ),
            )
        )

        # check for up-mixing if user has defined their own channel
        if self.payload.channels != DolbyDigitalPlusChannels.AUTO:
            # if user picked an Atmos layout, compare using the non-Atmos fallback
            if self.payload.channels.is_atmos():
                desired_channels = self.payload.channels.get_fallback_layout().value
            else:
                desired_channels = self.payload.channels.value
            self._check_for_up_mixing(audio_track_info.channels, desired_channels)

        # else if user has not defined their own channel, let's find the highest channel count
        # based on their input
        elif self.payload.channels is DolbyDigitalPlusChannels.AUTO:
            audio_track_info.channels = self._determine_auto_channel_s(
                audio_track_info.channels, DolbyDigitalPlusChannels.get_values_list()
            )

            # update self.payload channels enum to automatic channel selection
            self.payload.channels = DolbyDigitalPlusChannels(audio_track_info.channels)

        # delay
        delay_str = "0ms"
        if self.payload.delay:
            delay_str = self.payload.delay
        delay = DelayGenerator().get_dee_delay(delay_str)

        # fps
        fps = self._get_fps(audio_track_info.fps)

        # output dir
        temp_dir = self._get_temp_dir(file_input, self.payload.temp_dir)

        # check disk space
        self._check_disk_space(
            input_file_path=file_input,
            drive_path=temp_dir,
            recommended_free_space=audio_track_info.recommended_free_space,
        )

        # temp filename
        temp_filename = Path(tempfile.NamedTemporaryFile(delete=False).name).name

        # check to see if input channels are accepted by dee
        dee_allowed_input = self._dee_allowed_input(audio_track_info.channels)

        # downmix config
        down_mix_config = self._get_down_mix_config(
            self.payload.channels, audio_track_info.channels, dee_allowed_input
        )

        # determine if FFMPEG downmix is needed for unsupported channels
        ffmpeg_down_mix = False
        if down_mix_config == "off" and not dee_allowed_input:
            # if user selected an Atmos layout, use the non‑Atmos fallback channel count
            if self.payload.channels.is_atmos():
                ffmpeg_down_mix = self.payload.channels.get_fallback_layout().value
            # if user left channels AUTO (should be resolved earlier), fall back to detected input channels
            elif self.payload.channels is DolbyDigitalPlusChannels.AUTO:
                ffmpeg_down_mix = int(audio_track_info.channels)
            else:
                ffmpeg_down_mix = self.payload.channels.value

        # stereo mix
        stereo_mix = str(self.payload.stereo_mix.name).lower()

        # file output (if an output is a defined check users extension and use their output)
        if self.payload.file_output:
            output = Path(self.payload.file_output)
            if output.suffix not in [".ec3", ".eac3"]:
                raise InvalidExtensionError(
                    "DDP output must must end with the suffix '.eac3' or '.ec3'."
                )
        else:
            output = Path(audio_track_info.auto_name).with_suffix(".ec3")

        # define .wav and .ac3/.ec3 file names (not full path)
        input_file_name = temp_filename + ".wav"
        output_file_name = temp_filename + output.suffix

        if not self.payload.atmos:
            # generate ffmpeg cmd
            ffmpeg_cmd = self._generate_ffmpeg_cmd(
                ffmpeg_path=self.payload.ffmpeg_path,
                file_input=file_input,
                track_index=self.payload.track_index,
                sample_rate=audio_track_info.sample_rate,
                ffmpeg_down_mix=ffmpeg_down_mix,
                channels=self.payload.channels,
                output_dir=temp_dir,
                wav_file_name=input_file_name,
            )

            # process ffmpeg command
            _ffmpeg_job = process_ffmpeg_job(
                cmd=ffmpeg_cmd,
                progress_mode=self.payload.progress_mode,
                steps=True,
                duration=audio_track_info.duration,
            )
        else:
            atmos_job = decode_truehd_to_atmos(
                output_dir=temp_dir,
                file_input=file_input,
                track_index=self.payload.track_index,
                ffmpeg_path=self.payload.ffmpeg_path,
                truehdd_path=self.payload.truehdd_path,
                progress_mode=self.payload.progress_mode,
                duration=audio_track_info.duration,
            )
            if atmos_job:
                input_file_name = atmos_job.name

        # generate XML
        xml_generator = DeeXMLGenerator(
            bitrate=bitrate,
            input_file_name=input_file_name,
            output_file_name=output_file_name,
            output_dir=temp_dir,
            fps=fps,
            delay=delay,
            drc=self.payload.drc,
            atmos=self.payload.atmos,
        )
        if not self.payload.atmos:
            update_xml = xml_generator.generate_xml_ddp(
                down_mix_config=down_mix_config,
                stereo_down_mix=stereo_mix,
                channels=self.payload.channels,
                normalize=self.payload.normalize,
            )
        else:
            update_xml = xml_generator.generate_xml_atmos(
                channels=self.payload.channels
            )

        # generate DEE command
        dee_cmd = self._get_dee_cmd(
            dee_path=Path(self.payload.dee_path), xml_path=update_xml
        )

        # process dee command
        _dee_job = process_dee_job(
            cmd=dee_cmd, progress_mode=self.payload.progress_mode
        )

        # move file to output path
        # TODO maybe print that we're moving the file, in the event it takes a min via a callback or queue to frontend?
        move_file = Path(shutil.move(Path(temp_dir / output_file_name), output))
        # TODO maybe cheek if move_file exists and print success?

        # delete temp folder and all files if enabled
        # TODO if set to no, maybe let the user know where they are stored maybe, idk?
        self._clean_temp(temp_dir, self.payload.keep_temp)

        # return path
        if move_file.is_file():
            return move_file
        else:
            raise OutputFileNotFoundError(f"{move_file.name} output not found")

    @staticmethod
    def _get_accepted_bitrates(
        desired_channels: DolbyDigitalPlusChannels, source_channels: int
    ) -> Sequence[int]:
        """
        Return the allowed DDP bitrates for the requested channel layout.

        desired_channels may be a DolbyDigitalPlusChannels enum instance or an int.
        This supports Atmos layouts (ATMOS_5_1_2 / ATMOS_5_1_4 -> atmos_51x,
        ATMOS_7_1_2 / ATMOS_7_1_4 -> atmos_71x).
        """
        # atmos specific bitrates
        if desired_channels.is_atmos():
            if desired_channels.is_joc_atmos():
                return list(dee_ddp_bitrates.get("atmos_51x", ()))
            if desired_channels.is_bluray_atmos():
                return list(dee_ddp_bitrates.get("atmos_71x", ()))

        # non-atmos / fallback behavior
        if desired_channels is DolbyDigitalPlusChannels.AUTO:
            if source_channels == 1:
                return list(dee_ddp_bitrates.get("ddp_10", ()))
            elif source_channels == 2 or source_channels < 6:
                return sorted(
                    list(
                        set(dee_ddp_bitrates.get("ddp_10", ()))
                        & set(dee_ddp_bitrates.get("ddp_20", ()))
                    )
                )
            elif source_channels == 6:
                return sorted(
                    list(
                        set(dee_ddp_bitrates.get("ddp_10", ()))
                        & set(dee_ddp_bitrates.get("ddp_20", ()))
                        & set(dee_ddp_bitrates.get("ddp_51", ()))
                    )
                )
            elif source_channels >= 8:
                return sorted(
                    list(
                        set(dee_ddp_bitrates.get("ddp_10", ()))
                        & set(dee_ddp_bitrates.get("ddp_20", ()))
                        & set(dee_ddp_bitrates.get("ddp_51", ()))
                        & set(dee_ddp_bitrates.get("ddp_71_combined", ()))
                    )
                )
        elif desired_channels is DolbyDigitalPlusChannels.MONO:
            return list(dee_ddp_bitrates.get("ddp_10", ()))
        elif desired_channels is DolbyDigitalPlusChannels.STEREO:
            return list(dee_ddp_bitrates.get("ddp_20", ()))
        elif desired_channels is DolbyDigitalPlusChannels.SURROUND:
            return list(dee_ddp_bitrates.get("ddp_51", ()))
        elif desired_channels is DolbyDigitalPlusChannels.SURROUNDEX:
            return list(dee_ddp_bitrates.get("ddp_71_combined", ()))

        raise ValueError("No channel layout found")

    @staticmethod
    def _get_down_mix_config(
        channels: DolbyDigitalPlusChannels, input_channels: int, dee_allowed_input: bool
    ) -> str:
        if channels.value == input_channels or not dee_allowed_input:
            return "off"
        elif channels == DolbyDigitalPlusChannels.MONO:
            return "mono"
        elif channels == DolbyDigitalPlusChannels.STEREO:
            return "stereo"
        elif channels == DolbyDigitalPlusChannels.SURROUND:
            return "5.1"
        elif channels == DolbyDigitalPlusChannels.SURROUNDEX:
            return "off"
        return "off"

    def _generate_ffmpeg_cmd(
        self,
        ffmpeg_path: Path,
        file_input: Path,
        track_index: int,
        sample_rate: int | None,
        channels: DolbyDigitalPlusChannels,
        ffmpeg_down_mix: bool | int,
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

        # resample and add swap channels
        audio_filter_args = []
        if resample:
            if channels == DolbyDigitalPlusChannels.SURROUNDEX:
                audio_filter_args = [
                    "-af",
                    (
                        "pan=7.1|c0=c0|c1=c1|c2=c2|c3=c3|c4=c6|c5=c7|c6=c4|c7=c5,"
                        "aresample=resampler=soxr:precision=28:cutoff=1:dither_scale=0"
                    ),
                    "-ar",
                    str(sample_rate),
                ]
            elif channels != DolbyDigitalPlusChannels.SURROUNDEX:
                audio_filter_args = [
                    "-af",
                    "aresample=resampler=soxr:precision=28:cutoff=1:dither_scale=0",
                    "-ar",
                    str(sample_rate),
                ]

        elif not resample:
            if channels == DolbyDigitalPlusChannels.SURROUNDEX:
                audio_filter_args = [
                    "-af",
                    "pan=7.1|c0=c0|c1=c1|c2=c2|c3=c3|c4=c6|c5=c7|c6=c4|c7=c5",
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
