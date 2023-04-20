import sys
import argparse
from pathlib import Path
from pymediainfo import MediaInfo
from packages import _exit_application, exit_fail
from packages.shared.shared_utils import (
    _get_working_dir,
    _validate_track_index,
    _validate_bitrate_with_channels_and_format,
    _generate_output_filename,
    FindDependencies,
    _parse_input_s,
    _validate_media_file_s,
)
from packages.shared.progress import _process_ffmpeg, _process_dee, _display_banner
from packages.shared._version import program_name, __version__
from packages.dd_ddp.ddp_utils import _generate_xml_dd
from packages.atmos.atmos_utils import _generate_xml_atmos
from packages.atmos.atmos_decoder import _atmos_decode


def _process_input(
    ffmpeg_path: Path,
    mkvextract_path: Path,
    dee_path: Path,
    gst_launch_path: Path,
    args: argparse.ArgumentParser.parse_args,
    banner: bool,
):
    # display banner to console if enabled
    if banner:
        _display_banner()

    # validate correct bitrate
    try:
        _validate_bitrate_with_channels_and_format(arguments=args)
    except ValueError as e:
        _exit_application(e, exit_fail)

    # Check that the input file exists
    if not Path(args.input).exists():
        _exit_application(f"Input file not found: {args.input}", exit_fail)

    # Parse file with MediaInfo
    media_info_source = MediaInfo.parse(args.input)

    # attempt to get FPS from video track if it's present
    fps = "not_indicated"
    for mi_track in media_info_source.tracks:
        if mi_track.track_type == "Video":
            fps = mi_track.frame_rate

    # parse track for information
    # +1 because the first track is always "general"
    try:
        track_info = media_info_source.tracks[args.track_index + 1]
    except IndexError:
        _exit_application(
            f"Selected track #{args.track_index} does not exist.",
            exit_fail,
        )

    if track_info.track_type != "Audio":
        _exit_application(
            f"Selected track #{args.track_index} ({track_info.track_type}) is not an audio track.",
            exit_fail,
        )

    # get track duration and convert to a float if not None
    # we need duration to calculate percentage for FFMPEG
    duration = track_info.duration
    if duration:
        duration = float(duration)

    # get sampling rate
    try:
        sample_rate = track_info.sampling_rate
    except AttributeError:
        sample_rate = sys.maxsize

    if not sample_rate:
        sample_rate = sys.maxsize

    # get channel(s)
    channels = track_info.channel_s

    # get bit depth
    try:
        bits_per_sample = track_info.bit_depth
    except AttributeError:
        bits_per_sample = sys.maxsize

    if bits_per_sample == None:
        bits_per_sample = sys.maxsize

    if bits_per_sample not in [16, 24, 32]:
        if bits_per_sample < 16:
            bits_per_sample = 16
        elif bits_per_sample > 24:
            bits_per_sample = 32
        else:
            bits_per_sample = 24

    # Work out if we need to do a complex or simple resample
    resample = False
    if sample_rate != 48000:
        bits_per_sample = 32
        sample_rate = 48000
        resample = True

    if resample:
        channel_swap = ""
        if args.encoder != "atmos":
            if (
                channels == 2
                and args.stereo_down_mix == "dplii"
                and args.encoder == "dd"
            ):
                channel_swap = "aresample=matrix_encoding=dplii,"
            elif channels == 8:
                channel_swap = (
                    "pan=7.1|c0=c0|c1=c1|c2=c2|c3=c3|c4=c6|c5=c7|c6=c4|c7=c5,"
                )

        resample_args = [
            "-af",
            f"{channel_swap}aresample=resampler=soxr",
            "-ar",
            str(sample_rate),
            "-precision",
            "28",
            "-cutoff",
            "1",
            "-dither_scale",
            "0",
        ]
    else:
        resample_args = []

    if (
        channels == 2
        and not resample_args
        and args.stereo_down_mix == "dplii"
        and args.encoder == "dd"
    ):
        channel_swap_args = ["-af", "aresample=matrix_encoding=dplii"]
    elif channels == 8 and not resample_args and args.encoder != "atmos":
        channel_swap_args = [
            "-af",
            "pan=7.1|c0=c0|c1=c1|c2=c2|c3=c3|c4=c6|c5=c7|c6=c4|c7=c5",
        ]
    else:
        channel_swap_args = []

    # Work out if we need to do down-mix
    if args.encoder != "atmos":
        if args.channels > channels:
            _exit_application("Up-mixing is not supported.", exit_fail)
        elif args.channels == channels:
            down_mix_config = "off"
        elif args.channels == 1:
            down_mix_config = "mono"
        elif args.channels == 2:
            if args.stereo_down_mix == "dplii" and args.encoder == "dd":
                down_mix_config = "off"
            else:
                down_mix_config = "stereo"
        elif args.channels == 6:
            down_mix_config = "5.1"
        elif args.channels == 8:
            down_mix_config = "7.1"
        else:
            _exit_application("Unsupported channel count.", exit_fail)

    # if no output is specified we'll create one automatically and set it
    if not args.output:
        auto_output = _generate_output_filename(
            media_info=media_info_source,
            file_input=Path(args.input),
            track_index=args.track_index,
            encoder=args.encoder,
        )
        setattr(args, "output", str(auto_output))

    # Create the directory for the output file if it doesn't exist
    output_dir = Path(args.output).parent
    if not output_dir.exists():
        output_dir.mkdir(exist_ok=True)

    # Define .wav and .ac3/.ec3 file names (not full path)
    wav_file_name = str(Path(Path(args.output).name).with_suffix(".wav"))
    output_file_name = str(Path(args.output).name)

    # generate xml file and return path
    if args.encoder == "dd":
        try:
            update_xml = _generate_xml_dd(
                down_mix_config=down_mix_config,
                stereo_down_mix=args.stereo_down_mix,
                bitrate=str(args.bitrate),
                dd_format=args.encoder,
                channels=args.channels,
                normalize=False,
                wav_file_name=wav_file_name,
                output_file_name=output_file_name,
                output_dir=output_dir,
                fps=fps,
            )
        except ValueError as e:
            _exit_application(e, exit_fail)

    elif args.encoder == "ddp":
        try:
            update_xml = _generate_xml_dd(
                down_mix_config=down_mix_config,
                stereo_down_mix=args.stereo_down_mix,
                bitrate=str(args.bitrate),
                dd_format=args.encoder,
                channels=args.channels,
                normalize=args.normalize,
                wav_file_name=wav_file_name,
                output_file_name=output_file_name,
                output_dir=output_dir,
                fps=fps,
            )
        except ValueError as e:
            _exit_application(e, exit_fail)

    # if format is set to "atmos"
    elif args.encoder == "atmos":
        # ensure input file has atmos
        if "Atmos" in track_info.commercial_name:
            # decode atmos
            try:
                decode_atmos = _atmos_decode(
                    gst_launch=gst_launch_path,
                    mkvextract=mkvextract_path,
                    ffmpeg=ffmpeg_path,
                    input_file=Path(args.input),
                    track_number=args.track_index,
                    atmos_decode_workers=args.atmos_decode_workers,
                    source_fps=fps,
                    duration=duration,
                    progress_mode=args.progress_mode,
                    atmos_channel_config=args.channels,
                )
            except ValueError as e:
                _exit_application(e, exit_fail)

            # pass decoded atmos mezz file path to xml function
            if decode_atmos:
                update_xml = _generate_xml_atmos(
                    bitrate=str(args.bitrate),
                    atmos_mezz_file_name=Path(decode_atmos).name,
                    atmos_mezz_file_dir=Path(decode_atmos).parent,
                    output_file_name=output_file_name,
                    output_dir=output_dir,
                    fps=fps,
                )

            # if decoded atmos returned None
            else:
                _exit_application("Source Atmos data is corrupt/invalid.", exit_fail)

        # if no atmos was detected in input file
        else:
            _exit_application("Source does not contain Atmos data.", exit_fail)

    # if we're using 2.0, send "-ac 2" to ffmpeg for dplii resample
    if args.channels == 2 and args.stereo_down_mix == "dplii" and args.encoder == "dd":
        ffmpeg_ac = ["-ac", "2"]
    elif args.encoder == "atmos":
        atmos_channels = str(track_info.format_additionalfeatures).split("-")[0]
        ffmpeg_ac = ["-ac", atmos_channels]
    else:
        ffmpeg_ac = []

    # Call ffmpeg to generate the wav file
    ffmpeg_cmd = [
        str(ffmpeg_path),
        "-y",
        "-drc_scale",
        "0",
        "-i",
        str(Path(args.input)),
        "-map",
        f"0:{str(args.track_index)}",
        *(ffmpeg_ac),
        "-c",
        f"pcm_s{str(bits_per_sample)}le",
        *(channel_swap_args),
        *(resample_args),
        "-rf64",
        "always",
        "-hide_banner",
        "-v",
        "-stats",
        str(Path(output_dir / wav_file_name)),
    ]
    
    try:
        _process_ffmpeg(
            cmd=ffmpeg_cmd, progress_mode=args.progress_mode, steps=True, duration=duration
        )
    except ValueError as e:
        _exit_application(e, exit_fail)

    # Call dee to generate the encode file
    dee_cm = [
        str(dee_path),
        "--progress-interval",
        "500",
        "--diagnostics-interval",
        "90000",
        "--verbose",
        "-x",
        str(update_xml),
        "--disable-xml-validation",
    ]
    
    try:
        _process_dee(
            cmd=dee_cm, progress_mode=args.progress_mode, encoder_format=args.encoder
        )
    except ValueError as e:
        _exit_application(e, exit_fail)

    # Clean up temp files
    if not args.keep_temp:
        Path(update_xml).unlink()
        Path(output_dir / wav_file_name).unlink()

    # print success message
    _exit_application(f"Success: {Path(args.output).name}")


def _main(base_wd: Path):
    # define tools
    try:
        tools = FindDependencies(base_wd=base_wd)
    except FileNotFoundError as e:
        _exit_application(e, exit_fail)
    ffmpeg_path = Path(tools.ffmpeg)
    mkvextract_path = Path(tools.mkvextract)
    dee_path = Path(tools.dee)
    gst_launch_path = Path(tools.gst_launch)

    # Top-level parser
    parser = argparse.ArgumentParser(
        usage="%(prog)s encoder [encoder commands] optional commands"
    )

    # global optional commands
    parser.add_argument(
        "-t",
        "--track-index",
        type=_validate_track_index,
        default=0,
        help="The index of the audio track to use.",
    )
    parser.add_argument(
        "-b", "--bitrate", type=int, required=False, help="The bitrate in Kbps."
    )
    parser.add_argument(
        "-d", "--delay", type=int, default=0, help="The delay in milliseconds."
    )
    parser.add_argument(
        "-k",
        "--keep-temp",
        action="store_true",
        help="Keeps the temp files after finishing (usually a wav and an xml for DEE).",
    )
    parser.add_argument(
        "-p",
        "--progress-mode",
        choices=["standard", "debug"],
        default="standard",
        help="Sets progress output mode verbosity.",
    )
    parser.add_argument("-i", "--input", required=True, type=str, nargs="*", default=[], help="Input file(s) path(s).")
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        help=(
            "The output file path. If not specified we will attempt to automatically "
            "add Delay/Language string to output file name."
        ),
    )

    # version command
    parser.add_argument(
        "-v", "--version", action="version", version=f"{program_name} {__version__}"
    )

    # initiate subparsers
    subparsers = parser.add_subparsers(dest="encoder", help="Choose encoder")

    # dd subparser
    dd_parser = subparsers.add_parser("dd", help="Subset of exclusive DD commands")
    # dd subparser commands
    dd_parser.add_argument(
        "-c",
        "--channels",
        choices=[1, 2, 6],
        type=int,
        help="The number of channels.",
    )
    dd_parser.add_argument(
        "-s",
        "--stereo-down-mix",
        choices=["standard", "dplii"],
        type=str,
        default="standard",
        help="Down mix method for stereo.",
    )

    # ddp subparser
    ddp_parser = subparsers.add_parser("ddp", help="Subset of exclusive DD commands")
    # ddp subparser commands
    ddp_parser.add_argument(
        "-c",
        "--channels",
        choices=[1, 2, 6, 8],
        type=int,
        help="The number of channels.",
    )
    ddp_parser.add_argument(
        "-s",
        "--stereo-down-mix",
        choices=["standard", "dplii"],
        type=str,
        default="standard",
        help="Down mix method for stereo.",
    )
    ddp_parser.add_argument(
        "-n",
        "--normalize",
        action="store_true",
        help="Normalize audio for DDP.",
    )

    # atmos subparser
    atmos_parser = subparsers.add_parser(
        "atmos", help="Subset of exclusive Atmos commands"
    )
    # atmos subparser commands
    atmos_parser.add_argument(
        "-w",
        "--atmos-decode-workers",
        choices=list(range(1, 21)),
        type=int,
        default=4,
        help="Number of concurrent Atmos decode threads to process each channel",
    )
    atmos_parser.add_argument(
        "-c",
        "--channels",
        choices=["5.1.4", "7.1.4"],
        type=str,
        default="5.1.4",
        help="Desired Atmos channel configuration.",
    )

    # parse the arguments
    args = parser.parse_args()
    
    # parse input(s)
    try:
        parsed_inputs = _parse_input_s(args.input)
    except FileNotFoundError as e:
        _exit_application(e, exit_fail)
        

    # _process_input(
    #     ffmpeg_path=ffmpeg_path,
    #     mkvextract_path=mkvextract_path,
    #     dee_path=dee_path,
    #     gst_launch_path=gst_launch_path,
    #     args=args,
    #     banner=True,
    # )


if __name__ == "__main__":
    _main(base_wd=_get_working_dir())
