from collections.abc import Sequence
from pathlib import Path
import shutil
import tempfile

from deezy.audio_encoders.dee.base import BaseDeeAudioEncoder
from deezy.audio_encoders.dee.bitrates import dee_dd_bitrates
from deezy.audio_encoders.dee.xml.xml import DeeXMLGenerator
from deezy.audio_encoders.delay import get_dee_delay
from deezy.audio_processors.dee import process_dee_job
from deezy.audio_processors.ffmpeg import process_ffmpeg_job
from deezy.enums.dd import DolbyDigitalChannels
from deezy.enums.shared import StereoDownmix
from deezy.exceptions import InvalidExtensionError, OutputFileNotFoundError
from deezy.payloads.dd import DDPayload
from deezy.track_info.mediainfo import MediainfoParser


class DDEncoderDEE(BaseDeeAudioEncoder):
    def __init__(self, payload: DDPayload):
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
        if self.payload.channels != DolbyDigitalChannels.AUTO:
            self._check_for_up_mixing(
                audio_track_info.channels, self.payload.channels.value
            )

        # else if user has not defined their own channel, let's find the highest channel count
        # based on their input
        elif self.payload.channels == DolbyDigitalChannels.AUTO:
            audio_track_info.channels = self._determine_auto_channel_s(
                audio_track_info.channels, DolbyDigitalChannels.get_values_list()
            )

            # update payload channels enum to automatic channel selection
            self.payload.channels = DolbyDigitalChannels(audio_track_info.channels)

        # delay
        delay_str = "0ms"
        if self.payload.delay:
            delay_str = self.payload.delay
        delay = get_dee_delay(delay_str)

        # fps
        fps = self._get_fps(audio_track_info.fps)

        # temp dir
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
            self.payload.channels,
            audio_track_info.channels,
            self.payload.stereo_mix,
            dee_allowed_input,
        )

        # determine if FFMPEG downmix is needed
        ffmpeg_down_mix = False
        if (down_mix_config == "off" and not dee_allowed_input) or (
            self.payload.channels.value == 2
            and self.payload.stereo_mix == StereoDownmix.DPLII
        ):
            ffmpeg_down_mix = self.payload.channels.value

        # stereo mix
        stereo_mix = str(self.payload.stereo_mix.name).lower()

        # file output (if an output is a defined check users extension and use their output)
        if self.payload.file_output:
            output = Path(self.payload.file_output)
            if ".ac3" not in output.suffix:
                raise InvalidExtensionError(
                    "DD output must must end with the suffix '.ac3'."
                )
        else:
            output = Path(audio_track_info.auto_name).with_suffix(".ac3")

        # Define .wav and .ac3/.ec3 file names (not full path)
        # TODO can likely handle this better.
        wav_file_name = temp_filename + ".wav"
        output_file_name = temp_filename + ".ac3"

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

        # process ffmpeg command
        _ffmpeg_job = process_ffmpeg_job(
            cmd=ffmpeg_cmd,
            progress_mode=self.payload.progress_mode,
            steps=True,
            duration=audio_track_info.duration,
            step_info={"current": 1, "total": 3, "name": "FFMPEG"},
        )

        # generate XML
        xml_generator = DeeXMLGenerator(
            bitrate=bitrate,
            input_file_name=wav_file_name,
            output_file_name=output_file_name,
            output_dir=temp_dir,
            fps=fps,
            delay=delay,
            drc=self.payload.drc,
            atmos=False,
        )
        update_xml = xml_generator.generate_xml_dd(
            down_mix_config=down_mix_config,
            stereo_down_mix=stereo_mix,
            channels=self.payload.channels,
        )

        # generate DEE command
        dee_cmd = self._get_dee_cmd(
            dee_path=Path(self.payload.dee_path), xml_path=update_xml
        )

        # process dee command
        step_info = {"current": 2, "total": 3, "name": "DEE measure"}
        _dee_job = process_dee_job(
            cmd=dee_cmd, progress_mode=self.payload.progress_mode, step_info=step_info
        )

        # move file to output path
        # TODO maybe print that we're moving the file, in the event it takes a min?
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
        desired_channels: DolbyDigitalChannels, source_channels: int
    ) -> Sequence[int]:
        if desired_channels is DolbyDigitalChannels.AUTO:
            if source_channels == 1:
                return list(dee_dd_bitrates.get("dd_10", ()))
            elif source_channels == 2 or source_channels < 6:
                dd_10 = dee_dd_bitrates.get("dd_10", ())
                dd_20 = dee_dd_bitrates.get("dd_20", ())
                return sorted(list(set(dd_10) & set(dd_20)))
            elif source_channels >= 6:
                dd_10 = dee_dd_bitrates.get("dd_10", ())
                dd_20 = dee_dd_bitrates.get("dd_20", ())
                dd_51 = dee_dd_bitrates.get("dd_51", ())
                return sorted(list(set(dd_10) & set(dd_20) & set(dd_51)))
        elif desired_channels is DolbyDigitalChannels.MONO:
            return list(dee_dd_bitrates.get("dd_10", ()))
        elif desired_channels is DolbyDigitalChannels.STEREO:
            return list(dee_dd_bitrates.get("dd_20", ()))
        elif desired_channels is DolbyDigitalChannels.SURROUND:
            return list(dee_dd_bitrates.get("dd_51", ()))

        raise ValueError("No channel layout found")

    @staticmethod
    def _get_down_mix_config(
        channels: DolbyDigitalChannels,
        input_channels: int,
        stereo_downmix: StereoDownmix,
        dee_allowed_input: bool,
    ) -> str:
        if (
            (channels.value == input_channels)
            or (
                channels == DolbyDigitalChannels.STEREO
                and stereo_downmix == StereoDownmix.DPLII
            )
            or not dee_allowed_input
        ):
            return "off"
        elif channels == DolbyDigitalChannels.MONO:
            return "mono"
        elif channels == DolbyDigitalChannels.STEREO:
            return "stereo"
        elif channels == DolbyDigitalChannels.SURROUND:
            return "5.1"
        return "off"

    def _generate_ffmpeg_cmd(
        self,
        ffmpeg_path: Path,
        file_input: Path,
        track_index: int,
        sample_rate: int | None,
        ffmpeg_down_mix: bool | int,
        channels: DolbyDigitalChannels,
        stereo_down_mix: StereoDownmix,
        output_dir: Path,
        wav_file_name: str,
    ):
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
            channels == DolbyDigitalChannels.STEREO
            and stereo_down_mix == StereoDownmix.DPLII
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
