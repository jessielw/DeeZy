import sys
import argparse
from argparse import ArgumentTypeError
from pathlib import Path
from pymediainfo import MediaInfo
from packages.shared.shared_utils import (
    get_working_dir,
    validate_track_index,
    validate_channels_with_format,
    validate_bitrate_with_channels_and_format,
)
from packages.shared._version import program_name, __version__
from packages.dd_ddp.ddp_utils import generate_xml_dd
from packages.atmos.atmos_utils import generate_xml_atmos
from packages.atmos.atmos_decoder import atmos_decode
from packages.shared.progress import process_ffmpeg, process_dee, display_banner


def auto_fallback(
    reason: str,
    ffmpeg_path: Path,
    mkvextract_path: Path,
    dee_path: Path,
    gst_launch_path: Path,
    args: argparse.ArgumentParser.parse_args,
    track_info: object,
):
    """Falls back to hardcoded settings, currently only for Atmos

    Args:
        reason (str): String of the reason why we're falling back to print to console
        ffmpeg_path (Path): Path to ffmpeg
        mkvextract_path (Path): Path to mkvextract
        dee_path (Path): Path to DEE
        gst_launch_path (Path): Path to gst_launch
        args (argparse.ArgumentParser.parse_args): Parsed args object
        track_info (object): Track input mediainfo object
    """
    if track_info.channel_s >= 8:
        setattr(args, "channels", 8)
        setattr(args, "bitrate", "768")
        setattr(args, "format", "ddp")
        channel_string = "7.1"
    elif track_info.channel_s == 6:
        setattr(args, "channels", 6)
        setattr(args, "bitrate", "640")
        setattr(args, "format", "dd")
        channel_string = "5.1"
    elif track_info.channel_s < 6:
        setattr(args, "channels", 2)
        setattr(args, "bitrate", "448")
        setattr(args, "format", "dd")
        setattr(args, "stereo-down-mix", "dplii")
        channel_string = "2.0 DDPLII"

    print(
        f"Falling back to {str(args.format).upper()} {channel_string} {args.bitrate}Kbps... Reason: {reason}"
    )
    process_input(ffmpeg_path, mkvextract_path, dee_path, gst_launch_path, args)


def process_input(ffmpeg_path, mkvextract_path, dee_path, gst_launch_path, args):
    # display banner to console
    display_banner()

    # validate correct bitrate, channel count and format
    validate_channels_with_format(arguments=args)
    validate_bitrate_with_channels_and_format(arguments=args)

    # Check that the input file exists
    if not Path(args.input).exists():
        raise ArgumentTypeError(f"Input file not found: {args.input}")

    # Parse file with MediaInfo
    media_info_source = MediaInfo.parse(args.input)

    # attempt to get FPS from video track if it's present
    fps = "not_indicated"
    for mi_track in media_info_source.tracks:
        if mi_track.track_type == "Video":
            fps = mi_track.frame_rate

    # parse track for information
    # +1 because the first track is always "general"
    track_info = media_info_source.tracks[args.track_index + 1]

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

    if sample_rate == None:
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
        if args.format != "atmos":
            if (
                channels == 2
                and args.stereo_down_mix == "dplii"
                and args.format == "dd"
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
        and args.format == "dd"
    ):
        channel_swap_args = ["-af", "aresample=matrix_encoding=dplii"]
    elif channels == 8 and not resample_args and args.format != "atmos":
        channel_swap_args = [
            "-af",
            "pan=7.1|c0=c0|c1=c1|c2=c2|c3=c3|c4=c6|c5=c7|c6=c4|c7=c5",
        ]
    else:
        channel_swap_args = []

    # Work out if we need to do down-mix
    if args.format != "atmos":
        if args.channels > channels:
            raise ArgumentTypeError("Up-mixing is not supported.")
        elif args.channels == channels:
            down_mix_config = "off"
        elif args.channels == 1:
            down_mix_config = "mono"
        elif args.channels == 2:
            if args.stereo_down_mix == "dplii" and args.format == "dd":
                down_mix_config = "off"
            else:
                down_mix_config = "stereo"
        elif args.channels == 6:
            down_mix_config = "5.1"
        elif args.channels == 8:
            down_mix_config = "7.1"
        else:
            raise ArgumentTypeError("Unsupported channel count")

    # Create the directory for the output file if it doesn't exist
    output_dir = Path(args.output).parent
    if not output_dir.exists():
        output_dir.mkdir(exist_ok=True)

    # Define .wav and .ac3/.ec3 file names (not full path)
    wav_file_name = str(Path(Path(args.output).name).with_suffix(".wav"))
    output_file_name = str(Path(args.output).name)

    # generate xml file and return path
    if args.format == "dd" or args.format == "ddp":
        update_xml = generate_xml_dd(
            down_mix_config=down_mix_config,
            stereo_down_mix=args.stereo_down_mix,
            bitrate=str(args.bitrate),
            dd_format=args.format,
            channels=args.channels,
            normalize=args.normalize,
            wav_file_name=wav_file_name,
            output_file_name=output_file_name,
            output_dir=output_dir,
            fps=fps,
        )

    # if format is set to "atmos"
    elif args.format == "atmos":
        # ensure input file has atmos
        if "Atmos" in track_info.commercial_name:
            # decode atmos
            decode_atmos = atmos_decode(
                gst_launch=gst_launch_path,
                mkvextract=mkvextract_path,
                ffmpeg=ffmpeg_path,
                input_file=Path(args.input),
                track_number=args.track_index,
                atmos_decode_speed=args.atmos_decode_speed,
                source_fps=fps,
                duration=duration,
                progress_mode=args.progress_mode,
            )

            # pass decoded atmos mezz file path to xml function
            if decode_atmos:
                update_xml = generate_xml_atmos(
                    bitrate=str(args.bitrate),
                    atmos_mezz_file_name=Path(decode_atmos).name,
                    atmos_mezz_file_dir=Path(decode_atmos).parent,
                    output_file_name=output_file_name,
                    output_dir=output_dir,
                    fps=fps,
                )

            # if decoded atmos returned None
            else:
                if args.atmos_fall_back:
                    auto_fallback(
                        reason="Source Atmos data is corrupt/invalid",
                        ffmpeg_path=ffmpeg_path,
                        mkvextract_path=mkvextract_path,
                        dee_path=dee_path,
                        gst_launch_path=gst_launch_path,
                        args=args,
                        track_info=track_info,
                    )
                    return
                else:
                    raise ArgumentTypeError("Source Atmos data is corrupt/invalid")

        # if no atmos was detected in input file
        else:
            if args.atmos_fall_back:
                auto_fallback(
                    reason="Source Atmos data is corrupt/invalid",
                    ffmpeg_path=ffmpeg_path,
                    mkvextract_path=mkvextract_path,
                    dee_path=dee_path,
                    gst_launch_path=gst_launch_path,
                    args=args,
                    track_info=track_info,
                )
                return
            else:
                raise ArgumentTypeError("Source Atmos data is corrupt/invalid")

    # if we're using 2.0, send "-ac 2" to ffmpeg for dplii resample
    if args.channels == 2 and args.stereo_down_mix == "dplii" and args.format == "dd":
        ffmpeg_ac = ["-ac", "2"]
    elif args.format == "atmos":
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
    process_ffmpeg(
        cmd=ffmpeg_cmd, progress_mode=args.progress_mode, steps=True, duration=duration
    )

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
    process_dee(dee_cm, args.progress_mode)

    # Clean up temp files
    if not args.keep_temp:
        Path(update_xml).unlink()
        Path(output_dir / wav_file_name).unlink()


def main(base_wd: Path):
    # Define paths to ffmpeg, dee, and mkvextract
    # TODO: Consider adding switch to accept FFMPEG/mkvextract path instead of bundling?
    ffmpeg_path = Path(base_wd / "apps/ffmpeg/ffmpeg.exe")
    mkvextract_path = Path(base_wd / "apps/mkvextract/mkvextract.exe")
    dee_path = Path(base_wd / "apps/dee/dee.exe")
    gst_launch_path = Path(base_wd / "apps/drp/gst-launch-1.0.exe")

    # Check that the required paths exist
    for exe_path in [ffmpeg_path, dee_path, mkvextract_path, gst_launch_path]:
        if not Path(exe_path).is_file():
            raise ValueError(f"{str(Path(exe_path).name)} path not found")

    # Parse the command line arguments
    parser = argparse.ArgumentParser(description="A command line tool.")
    parser.add_argument(
        "-i", "--input", type=str, required=True, help="The input file path."
    )
    parser.add_argument(
        "-o", "--output", type=str, required=True, help="The output file path."
    )
    parser.add_argument(
        "-c",
        "--channels",
        choices=[1, 2, 6, 8],
        type=int,
        help="The number of channels.",
    )
    parser.add_argument(
        "-s",
        "--stereo-down-mix",
        choices=["standard", "dplii"],
        type=str,
        default="standard",
        help="Down mix method for stereo.",
    )
    parser.add_argument(
        "-b", "--bitrate", type=int, required=True, help="The bitrate in Kbps."
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["dd", "ddp", "atmos"],
        type=str,
        default="dd",
        help="The file format.",
    )
    parser.add_argument(
        "-a",
        "--atmos-decode-speed",
        choices=["single", "multi"],
        type=str,
        default="multi",
        help="Decode 1 atmos at a time or all at once.",
    )
    parser.add_argument(
        "-r",
        "--atmos-fall-back",
        action="store_true",
        help="In the event Atmos data is invalid, automatically fall back to the next best potential settings",
    )
    parser.add_argument(
        "-t",
        "--track-index",
        type=validate_track_index,
        default=0,
        help="The index of the audio track to use.",
    )
    parser.add_argument(
        "-d", "--delay", type=int, default=0, help="The delay in milliseconds."
    )
    parser.add_argument(
        "-n",
        "--normalize",
        action="store_true",
        help="Normalize audio for DDP.",
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
    parser.add_argument(
        "-v", "--version", action="version", version=f"{program_name} {__version__}"
    )
    args = parser.parse_args()

    process_input(
        ffmpeg_path=ffmpeg_path,
        mkvextract_path=mkvextract_path,
        dee_path=dee_path,
        gst_launch_path=gst_launch_path,
        args=args,
    )


if __name__ == "__main__":
    main(base_wd=get_working_dir())
