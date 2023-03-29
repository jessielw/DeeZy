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
    process_job,
)
from packages._version import program_name, __version__


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

    matrix_encoding_arg = ""
    if args.channels == 1 or args.channels == 2:
        matrix_encoding_arg = f"[a:{args.track_index}]aresample=matrix_encoding=dplii"

    resample_args = []
    if resample:
        resample_args = [
            "-filter_complex",
            f"[a:{args.track_index}]aresample=resampler=soxr",
            matrix_encoding_arg,
            "-ar",
            sample_rate,
            "-precision",
            "28",
            "-cutoff",
            "1",
            "-dither_scale",
            "0",
        ]
    elif args.channels == 1 or args.channels == 2:
        resample_args = ["-filter_complex", matrix_encoding_arg]
    else:
        resample_args = []

    # Work out if we need to do down-mix
    if args.channels > channels:
        raise ValueError("Up-mixing is not supported.")
    elif args.channels == channels:
        down_mix_config = "off"
    elif args.channels == 1:
        down_mix_config = "mono"
    elif args.channels == 2:
        down_mix_config = "stereo"
    elif args.channels == 6:
        down_mix_config = "5.1"

    # Create the directory for the output file if it doesn't exist
    output_dir = Path(args.output).parent
    if not output_dir.exists():
        output_dir.mkdir(exist_ok=True)

    # clean spaces from output name since xml/dee.exe has issues with spacing
    cleaned_output_file_name = sub(r"\s+", "_", str(Path(args.output).name))

    # Create wav file name for the intermediate file
    wav_file_name = Path(cleaned_output_file_name).with_suffix(".wav")

    # Get the path to the template.xml file
    template_path = Path(base_wd / "runtime/template.xml")
    # Load the contents of the template.xml file into the dee_config variable
    xml_dee_config = ET.parse(template_path)
    xml_root = xml_dee_config.getroot()

    # Update the template values
    xml_pcm_to_ddp = xml_root.find("filter/audio/pcm_to_ddp")
    xml_down_mix_config_elem = xml_pcm_to_ddp.find("downmix_config")
    xml_down_mix_config_elem.text = down_mix_config
    xml_down_mix_config_elem = xml_pcm_to_ddp.find("data_rate")
    xml_down_mix_config_elem.text = str(args.bitrate)

    xml_input = xml_root.find("input/audio/wav")
    xml_input_file_name = xml_input.find("file_name")
    xml_input_file_name.text = str(wav_file_name)
    xml_input_file_path = xml_input.find("storage/local/path")
    xml_input_file_path.text = str(output_dir)

    xml_output = xml_root.find("output/ac3")
    xml_output_file_name = xml_output.find("file_name")
    xml_output_file_name.text = cleaned_output_file_name
    xml_output_file_path = xml_output.find("storage/local/path")
    xml_output_file_path.text = str(output_dir)

    xml_temp = xml_root.find("misc/temp_dir")
    xml_temp_path = xml_temp.find("path")
    xml_temp_path.text = str(output_dir)

    # Save out the updated template
    updated_template_file = Path(output_dir / cleaned_output_file_name).with_suffix(
        ".xml"
    )

    if updated_template_file.exists():
        updated_template_file.unlink()
    xml_dee_config.write(str(updated_template_file))

    # Call ffmpeg to generate the wav file
    ffmpeg_cmd = [
        str(ffmpeg_path),
        "-y",
        "-drc_scale",
        "0",
        "-i",
        args.input,
        "-c",
        f"pcm_s{bits_per_sample}le",
        *(resample_args),
        "-rf64",
        "always",
        "-hide_banner",
        "-v",
        "quiet",
        "-stats",
        str(Path(output_dir / wav_file_name)),
    ]
    process_job(ffmpeg_cmd, banner=True)

    # Call dee to generate the encode file
    dee_cm = [
        str(dee_path),
        "--progress-interval",
        "500",
        "--diagnostics-interval",
        "90000",
        "--verbose",
        "info",
        "-x",
        str(updated_template_file),
        "--disable-xml-validation",
    ]
    process_job(dee_cm, banner=False)

    # Clean up temp files
    if not args.keep_temp:
        Path(updated_template_file).unlink()
        Path(output_dir / wav_file_name).unlink()

    # rename output file to whatever original defined output was
    Path(output_dir / cleaned_output_file_name).replace(Path(args.output))


if __name__ == "__main__":
    main(base_wd=get_working_dir())
