from audio_encoder.audio_encoders.base import (
    BaseAudioEncoder,
    PathTooLongError,
    InvalidExtensionError,
)
from audio_encoder.audio_encoders.dee.xml.utils import _generate_xml_dd
from audio_encoder.track_info.mediainfo import MediainfoParser
from audio_encoder.audio_encoders.dee.bitrates import dee_dd_bitrates
from audio_encoder.enums.shared import ProgressMode, StereoDownmix
from audio_encoder.enums.dd import DolbyDigitalChannels
from audio_encoder.audio_processors.ffmpeg import ProcessFFMPEG
from audio_encoder.audio_processors.dee import ProcessDEE
from pathlib import Path
import tempfile
import shutil


class DDEncoderDEE(BaseAudioEncoder):
    def __init__(self):
        super().__init__()

        # TODO account for bitrate/other params not passed that needs to be
        # print(vars(payload))

    def encode(self, payload: object):
        # TODO I'm sure we can still split this method up!

        # convert for dee XML
        # file input
        # TODO actually allow multiple inputs, for now hard coded to first one
        file_input = Path(payload.file_input[0])
        self._check_input_file(file_input)

        # # track index
        # track_index = str(payload.track_index)

        # bitrate
        bitrate = str(
            self._get_closest_allowed_bitrate(
                bitrate=payload.bitrate,
                accepted_bitrates=self._get_accepted_bitrates(
                    channels=payload.channels
                ),
            )
        )

        # get audio track information (using payload.track_index here since it's already an int)
        audio_track_info = MediainfoParser().get_track_by_id(
            file_input, payload.track_index
        )

        # delay
        if payload.delay:
            delay = str(payload.delay)
        else:
            delay = None
        # fps
        fps = self._get_fps(audio_track_info.fps)

        # channels
        # TODO need to figure out what to do if no channels are supplied
        # not even sure we need this atm though...
        # channels = payload.channels.value

        # temp dir
        temp_dir = self._get_temp_dir(file_input, payload.temp_dir)
        # temp filename
        temp_filename = Path(tempfile.NamedTemporaryFile(delete=False).name).name
        # keep temp
        keep_temp = payload.keep_temp
        # progress mode
        progress_mode = payload.progress_mode
        # downmix config
        down_mix_config = self._get_down_mix_config(payload.channels)
        # stereo mix
        stereo_mix = str(payload.stereo_mix.name).lower()
        # file output (if an output is a defined check users extension and use their output)
        if payload.file_output:
            output = Path(payload.file_output)
            if "ac3" not in output.suffix:
                raise InvalidExtensionError(
                    "DD output must must end with the suffix '.ac3'."
                )
        elif not payload.file_output:
            output = Path(audio_track_info.auto_name).with_suffix(".ac3")

        # Define .wav and .ac3/.ec3 file names (not full path)
        # TODO can likely handle this better.
        wav_file_name = temp_filename + ".wav"
        output_file_name = temp_filename + ".ac3"

        # generate ffmpeg cmd
        ffmpeg_cmd = self._generate_ffmpeg_cmd(
            ffmpeg_path=payload.ffmpeg_path,
            file_input=file_input,
            track_index=payload.track_index,
            sample_rate=audio_track_info.sample_rate,
            channels=payload.channels,
            stereo_down_mix=payload.stereo_mix,
            output_dir=temp_dir,
            wav_file_name=wav_file_name,
        )

        # process ffmpeg command
        # TODO fix progress mode to enums
        # TODO can check for True return from ffmpeg_job if we need?
        ffmpeg_job = ProcessFFMPEG().process_job(
            cmd=ffmpeg_cmd,
            progress_mode="standard",
            steps=True,
            duration=audio_track_info.duration,
        )

        print("wait")

        # generate XML
        # TODO deal with sending the encoder to this correctly later
        # Optimize all of this correctly
        update_xml = _generate_xml_dd(
            down_mix_config=down_mix_config,
            stereo_down_mix=stereo_mix,
            bitrate=bitrate,
            # TODO handle dd format
            dd_format="dd",
            channels=payload.channels,
            # TODO deal with normalize correctly, only enable for DDP
            normalize=False,
            wav_file_name=wav_file_name,
            output_file_name=output_file_name,
            output_dir=temp_dir,
            fps=fps,
        )

        print("pause")

        # Call dee to generate the encode file
        dee_cm = [
            str(payload.dee_path),
            "--progress-interval",
            "500",
            "--diagnostics-interval",
            "90000",
            "--verbose",
            "-x",
            str(update_xml),
            "--disable-xml-validation",
        ]

        # Process dee command
        # TODO handle hard coded progress_mode
        # TODO can check for True return from dee_job if we need?
        dee_job = ProcessDEE().process_job(cmd=dee_cm, progress_mode="standard")

        # move file to output path
        # TODO handle this in a function/cleaner
        # TODO maybe print that we're moving the file, in the event it takes a min?
        move_file = shutil.move(Path(temp_dir / output_file_name), output)
        # TODO maybe cheek if move_file exists and print success?

    @staticmethod
    def _get_fps(fps: object):
        accepted_choices = {
            "23.976",
            "24",
            "25",
            "29.97",
            "30",
            "48",
            "50",
            "59.94",
            "60",
        }
        fps_out = "not_indicated"
        str_fps = str(fps)
        if str_fps in accepted_choices:
            fps_out = str_fps
        return fps_out

    @staticmethod
    def _get_accepted_bitrates(channels: int):
        if channels == DolbyDigitalChannels.MONO:
            return dee_dd_bitrates.get("dd_10")
        elif channels == DolbyDigitalChannels.STEREO:
            return dee_dd_bitrates.get("dd_20")
        elif channels == DolbyDigitalChannels.SURROUND:
            return dee_dd_bitrates.get("dd_51")

    @staticmethod
    def _get_temp_dir(file_input: Path, temp_dir: Path):
        if temp_dir:
            if len(file_input.name) + len(temp_dir) < 259:
                raise PathTooLongError(
                    "Path provided with input file exceeds path length for DEE."
                )
            temp_directory = Path(temp_dir)
            temp_directory.mkdir(exist_ok=True)

        else:
            temp_directory = Path(tempfile.mkdtemp(prefix="dee_temp_"))

        return temp_directory

    # @staticmethod
    # def _get_stereo_mix(stereo_mix: object):
    #     if stereo_mix == StereoDownmix.STANDARD:
    #         mix = "standard"
    #     elif stereo_mix == StereoDownmix.DPLII:
    #         mix = ""

    # @staticmethod
    # def _get_progress_mode(progress_mode: object):
    #     if progress_mode == ProgressMode.DEBUG:
    #         mode = ""

    @staticmethod
    def _get_down_mix_config(channels: DolbyDigitalChannels):
        # TODO this also can be "off", NOT SURE IF NEEDED
        # return "off"?
        if channels == DolbyDigitalChannels.MONO:
            return "mono"
        elif channels == DolbyDigitalChannels.STEREO:
            return "stereo"
        elif channels == DolbyDigitalChannels.SURROUND:
            return "5.1"

    @staticmethod
    def _generate_ffmpeg_cmd(
        ffmpeg_path: Path,
        file_input: Path,
        track_index: int,
        sample_rate: int,
        channels: DolbyDigitalChannels,
        stereo_down_mix: StereoDownmix,
        output_dir: Path,
        wav_file_name: str,
    ):
        # Work out if we need to do a complex or simple resample
        # check for dplii
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

        # base ffmpeg command
        ffmpeg_cmd = [
            str(ffmpeg_path),
            "-y",
            "-drc_scale",
            "0",
            "-i",
            str(Path(file_input)),
            "-map",
            f"0:{track_index}",
            "-c",
            f"pcm_s{str(bits_per_sample)}le",
            *(audio_filter_args),
            "-rf64",
            "always",
            "-hide_banner",
            "-v",
            "-stats",
            str(Path(output_dir / wav_file_name)),
        ]
        return ffmpeg_cmd
