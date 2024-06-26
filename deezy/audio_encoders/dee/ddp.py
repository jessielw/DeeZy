import shutil
import tempfile
from typing import Union, List
from pathlib import Path

from deezy.audio_encoders.dee.base import BaseDeeAudioEncoder
from deezy.audio_encoders.dee.bitrates import dee_ddp_bitrates
from deezy.audio_encoders.dee.xml.xml import DeeXMLGenerator
from deezy.audio_encoders.delay import DelayGenerator
from deezy.audio_processors.dee import ProcessDEE
from deezy.audio_processors.ffmpeg import ProcessFFMPEG
from deezy.enums.ddp import DolbyDigitalPlusChannels
from deezy.exceptions import InvalidExtensionError, OutputFileNotFoundError
from deezy.track_info.mediainfo import MediainfoParser


class DDPEncoderDEE(BaseDeeAudioEncoder):
    def __init__(self):
        super().__init__()

        # TODO account for bitrate/other params not passed that needs to be
        # print(vars(payload))

    def encode(self, payload: object):
        # TODO I'm sure we can still split this method up!

        # convert for dee XML
        # file input
        file_input = Path(payload.file_input)
        self._check_input_file(file_input)

        # get audio track information (using payload.track_index here since it's already an int)
        audio_track_info = MediainfoParser().get_track_by_id(
            file_input, payload.track_index
        )

        # bitrate
        bitrate = str(
            self._get_closest_allowed_bitrate(
                bitrate=payload.bitrate,
                accepted_bitrates=self._get_accepted_bitrates(
                    desired_channels=payload.channels,
                    source_channels=int(audio_track_info.channels),
                ),
            )
        )

        # check for up-mixing if user has defined their own channel
        if payload.channels != DolbyDigitalPlusChannels.AUTO:
            self._check_for_up_mixing(audio_track_info.channels, payload.channels.value)

        # else if user has not defined their own channel, let's find the highest channel count
        # based on their input
        elif payload.channels == DolbyDigitalPlusChannels.AUTO:
            audio_track_info.channels = self._determine_auto_channel_s(
                audio_track_info.channels, DolbyDigitalPlusChannels.get_values_list()
            )

            # update payload channels enum to automatic channel selection
            payload.channels = DolbyDigitalPlusChannels(audio_track_info.channels)

        # delay
        delay_str = "0ms"
        if payload.delay:
            delay_str = payload.delay
        delay = DelayGenerator().get_dee_delay(delay_str)

        # fps
        fps = str(self._get_fps(audio_track_info.fps))

        # channels
        # TODO need to figure out what to do if no channels are supplied
        # not even sure we need this atm though...
        # channels = payload.channels.value

        # output dir
        temp_dir = self._get_temp_dir(file_input, payload.temp_dir)

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
            payload.channels, audio_track_info.channels, dee_allowed_input
        )

        # determine if FFMPEG downmix is needed for unsupported channels
        ffmpeg_down_mix = False
        if down_mix_config == "off" and not dee_allowed_input:
            ffmpeg_down_mix = payload.channels.value

        # stereo mix
        stereo_mix = str(payload.stereo_mix.name).lower()

        # file output (if an output is a defined check users extension and use their output)
        if payload.file_output:
            output = Path(payload.file_output)
            if output.suffix not in [".ec3", ".eac3"]:
                raise InvalidExtensionError(
                    "DDP output must must end with the suffix '.eac3' or '.ec3'."
                )
        elif not payload.file_output:
            output = Path(audio_track_info.auto_name).with_suffix(".ec3")

        # Define .wav and .ac3/.ec3 file names (not full path)
        # TODO can likely handle this better.
        wav_file_name = temp_filename + ".wav"
        output_file_name = temp_filename + output.suffix

        # generate ffmpeg cmd
        ffmpeg_cmd = self._generate_ffmpeg_cmd(
            ffmpeg_path=payload.ffmpeg_path,
            file_input=file_input,
            track_index=payload.track_index,
            sample_rate=audio_track_info.sample_rate,
            ffmpeg_down_mix=ffmpeg_down_mix,
            channels=payload.channels,
            output_dir=temp_dir,
            wav_file_name=wav_file_name,
        )

        # process ffmpeg command
        # TODO fix progress mode to enums
        # TODO can check for True return from ffmpeg_job if we need?
        ffmpeg_job = ProcessFFMPEG().process_job(
            cmd=ffmpeg_cmd,
            progress_mode=payload.progress_mode,
            steps=True,
            duration=audio_track_info.duration,
        )

        # generate XML
        xml_generator = DeeXMLGenerator(
            bitrate=bitrate,
            wav_file_name=wav_file_name,
            output_file_name=output_file_name,
            output_dir=temp_dir,
            fps=fps,
            delay=delay,
            drc=payload.drc,
        )
        update_xml = xml_generator.generate_xml_ddp(
            down_mix_config=down_mix_config,
            stereo_down_mix=stereo_mix,
            channels=payload.channels,
            normalize=payload.normalize,
        )

        # generate DEE command
        dee_cmd = self._get_dee_cmd(
            dee_path=Path(payload.dee_path), xml_path=update_xml
        )

        # Process dee command
        # TODO can check for True return from dee_job if we need?
        dee_job = ProcessDEE().process_job(
            cmd=dee_cmd, progress_mode=payload.progress_mode
        )

        # move file to output path
        # TODO handle this in a function/cleaner
        # TODO maybe print that we're moving the file, in the event it takes a min?
        move_file = Path(shutil.move(Path(temp_dir / output_file_name), output))
        # TODO maybe cheek if move_file exists and print success?

        # delete temp folder and all files if enabled
        # TODO if set to no, maybe let the user know where they are stored maybe, idk?
        self._clean_temp(temp_dir, payload.keep_temp)

        # return path
        if move_file.is_file():
            return move_file
        else:
            raise OutputFileNotFoundError(f"{move_file.name} output not found")

    @staticmethod
    def _get_accepted_bitrates(
        desired_channels: int, source_channels: int
    ) -> List[int]:
        if desired_channels == DolbyDigitalPlusChannels.AUTO:
            if source_channels == 1:
                return dee_ddp_bitrates.get("ddp_10")
            elif source_channels == 2 or source_channels < 6:
                return sorted(
                    list(
                        set(dee_ddp_bitrates.get("ddp_10"))
                        & set(dee_ddp_bitrates.get("ddp_20"))
                    )
                )
            elif source_channels == 6:
                return sorted(
                    list(
                        set(dee_ddp_bitrates.get("ddp_10"))
                        & set(dee_ddp_bitrates.get("ddp_20"))
                        & set(dee_ddp_bitrates.get("ddp_51"))
                    )
                )
            elif source_channels >= 8:
                return sorted(
                    list(
                        set(dee_ddp_bitrates.get("ddp_10"))
                        & set(dee_ddp_bitrates.get("ddp_20"))
                        & set(dee_ddp_bitrates.get("ddp_51"))
                        & set(dee_ddp_bitrates.get("ddp_71_combined"))
                    )
                )
        elif desired_channels == DolbyDigitalPlusChannels.MONO:
            return dee_ddp_bitrates.get("ddp_10")
        elif desired_channels == DolbyDigitalPlusChannels.STEREO:
            return dee_ddp_bitrates.get("ddp_20")
        elif desired_channels == DolbyDigitalPlusChannels.SURROUND:
            return dee_ddp_bitrates.get("ddp_51")
        elif desired_channels == DolbyDigitalPlusChannels.SURROUNDEX:
            return dee_ddp_bitrates.get("ddp_71_combined")

    @staticmethod
    def _get_down_mix_config(
        channels: DolbyDigitalPlusChannels, input_channels: int, dee_allowed_input: bool
    ):
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

    def _generate_ffmpeg_cmd(
        self,
        ffmpeg_path: Path,
        file_input: Path,
        track_index: int,
        sample_rate: int,
        ffmpeg_down_mix: Union[bool, DolbyDigitalPlusChannels],
        channels: DolbyDigitalPlusChannels,
        output_dir: Path,
        wav_file_name: str,
    ):
        # Work out if we need to do a complex or simple resample
        # TODO we need to allow custom sample rates
        if sample_rate != 48000:
            bits_per_sample = 32
            sample_rate = 48000
            resample = True
        else:
            # TODO Need to figure out if this is the right way to handle this, this is temporary
            # I added this temporarily, was sys.maxsize
            bits_per_sample = 32
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
