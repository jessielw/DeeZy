import sys
import argparse
import xml.etree.ElementTree as ET
from re import sub
from pathlib import Path
from pymediainfo import MediaInfo
from packages.utils import (
    get_working_dir,
    validate_track_index,
    validate_channels,
    validate_bitrate,
)
from packages._version import program_name, __version__
from packages.xml import generate_xml
from packages.progress import process_ffmpeg, process_dee, display_banner


def main(base_wd: Path):
    # Define paths to ffmpeg and dee
    # TODO: Consider adding switch to accept FFMPEG path instead of bundling?
    ffmpeg_path = Path(base_wd / "apps/ffmpeg/ffmpeg.exe")
    dee_path = Path(base_wd / "apps/dee/dee.exe")

    # Check that the required paths exist
    for exe_path in [ffmpeg_path, dee_path]:
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
        type=validate_channels,
        required=True,
        help="The number of channels. Valid options: 1, 2, 6.",
    )
    parser.add_argument(
        "-b", "--bitrate", type=int, required=True, help="The bitrate in Kbps."
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
        "-k",
        "--keep-temp",
        type=bool,
        default=False,
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

    # validate correct bitrate for channels input
    validate_bitrate(arg_parser=parser, arguments=args)

    # Check that the input file exists
    if not Path(args.input).exists():
        raise ValueError(f"Input file not found: {args.input}")

    # Parse file with MediaInfo
    media_info_source = MediaInfo.parse(args.input)

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
        resample_args = [
            "-af",
            "aresample=resampler=soxr",
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

    # Work out if we need to do down-mix
    # We only set preferred mode for 2 (stereo) to dplii
    preferred_down_mix_mode = "not_indicated"
    if args.channels > channels:
        raise ValueError("Up-mixing is not supported.")
    elif args.channels == channels:
        down_mix_config = "off"
    elif args.channels == 1:
        down_mix_config = "mono"
    elif args.channels == 2:
        down_mix_config = "stereo"
        preferred_down_mix_mode = "ltrt-pl2"
    elif args.channels == 6:
        down_mix_config = "5.1"

    # Create the directory for the output file if it doesn't exist
    output_dir = Path(args.output).parent
    if not output_dir.exists():
        output_dir.mkdir(exist_ok=True)

    # Define .wav and .ac3 file names (not full path)
    wav_file_name = str(Path(Path(args.output).name).with_suffix(".wav"))
    ac3_file_name = str(Path(Path(args.output).name).with_suffix(".ac3"))

    # generate xml file and return path
    update_xml = generate_xml(
        down_mix_config=down_mix_config,
        preferred_down_mix_mode=preferred_down_mix_mode,
        bitrate=str(args.bitrate),
        wav_file_name=wav_file_name,
        ac3_file_name=ac3_file_name,
        output_dir=output_dir,
    )

    # display banner to console
    display_banner()

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
        "-c",
        f"pcm_s{str(bits_per_sample)}le",
        *(resample_args),
        "-rf64",
        "always",
        "-hide_banner",
        "-v",
        "-stats",
        str(Path(output_dir / wav_file_name)),
    ]
    process_ffmpeg(ffmpeg_cmd, args.progress_mode, duration)

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


if __name__ == "__main__":
    main(base_wd=get_working_dir())
