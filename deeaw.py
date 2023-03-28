import argparse
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from pymediainfo import MediaInfo


def validate_channels(value: int):
    """Ensure we are utilizing the correct amount of channels"""

    valid_channels = [1, 2, 6]
    if value not in valid_channels:
        raise argparse.ArgumentTypeError(
            f"Invalid number of channels. Valid options: {valid_channels}"
        )


def determine_track_index(media_info: object, track_index: int):
    """
    Detects count of video streams and adds them to the total track index.
    This way we can dynamically detect the correct track index all the time.

    Args:
        media_info (object): pymediainfo object
        track_index (int): track index from args

    Returns:
        (int): Returns integer of index needed to send to FFMPEG via -map 0:[int]
    """

    # detect count of video streams from source
    num_video_streams = media_info.general_tracks[0].count_of_video_streams

    # add the number of video streams to the track index and return the value
    if num_video_streams and int(num_video_streams) >= 1:
        track_index += int(num_video_streams)

    return track_index


def process_job(cmd: list):
    """Process jobs"""

    # TODO: Handle total progress from output here?
    with subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True
    ) as proc:
        for line in proc.stdout:
            print(line.strip())


def main():
    # Define paths to ffmpeg and dee
    # TODO: Consider adding switch to accept FFMPEG path instead of bundling?
    ffmpeg_path = Path(Path.cwd() / "apps/ffmpeg/ffmpeg.exe")
    dee_path = Path(Path.cwd() / "apps/dee/dee.exe")

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
        type=int,
        required=True,
        help="The number of channels. Valid options: 1, 2, 6.",
    )
    parser.add_argument(
        "-b", "--bitrate", type=int, required=True, help="The bitrate in Kbps."
    )
    parser.add_argument(
        "-t",
        "--track-index",
        type=int,
        default=0,
        help="The index of the audio track to use.",
    )
    parser.add_argument(
        "-d", "--delay", type=int, default=0, help="The delay in milliseconds."
    )
    args = parser.parse_args()

    # validate channels
    validate_channels(args.channels)

    # Check that the input file exists
    if not Path(args.input).exists():
        raise ValueError(f"Input file not found: {args.input}")

    # Parse file with MediaInfo
    media_info_source = MediaInfo.parse(args.input)

    # get track index
    get_track_index = determine_track_index(
        media_info=media_info_source, track_index=int(args.track_index)
    )
    
    # parse track for information
    track_info = media_info_source.tracks[get_track_index]

    # get sampling rate
    # TODO: Ensure we are dealing with this properly in the event it's missing
    try:
        sample_rate = track_info.sampling_rate
    except AttributeError:
        sample_rate = None

    # get channel(s)
    channels = track_info.channel_s

    # get bit depth
    # TODO: Ensure we are dealing with this properly in the event it's missing
    try:
        bits_per_sample = track_info.bit_depth
    except AttributeError:
        bits_per_sample = None

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
    if args.channels == 2:
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
    else:
        resample_args = ["-filter_complex", matrix_encoding_arg]

    # Work out if we need to do down-mix
    down_mix_config = "off"
    if args.channels > channels:
        raise ValueError("Up-mixing is not supported.")
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
    cleaned_output_file_name = str(Path(args.output).name).replace(" ", "_")

    # Create wav_filepath for the intermediate file
    extensions = "".join(Path(args).output.suffixes)
    wav_file_name = cleaned_output_file_name.replace(extensions, ".wav")

    # Get the path to the template.xml file
    template_path = Path(Path.cwd() / "runtime/template.xml")
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
    xml_input_file_name.text = wav_file_name
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
    updated_template_file = Path(
        output_dir / cleaned_output_file_name.replace(extensions, ".xml")
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
        wav_file_name,
    ]
    process_job(ffmpeg_cmd)

    # Call dee to generate the encode file
    dee_cm = [
        str(dee_path),
        "--progress-interval",
        "500",
        "--diagnostics-interval",
        "90000",
        "-x",
        updated_template_file,
        "--disable-xml-validation",
    ]
    process_job(dee_cm)

    # Clean up temp files
    # TODO: Add an optional switch?
    Path(updated_template_file).unlink()
    Path(wav_file_name).unlink()

    # rename output file to whatever original defined output was
    # TODO: Add an optional switch?
    Path(output_dir / cleaned_output_file_name).replace(Path(args.output))


if __name__ == "__main__":
    # check if we're running via script or bundled
    # TODO: Clarify why we need this?
    if Path(sys.argv[0]).suffix == ".exe":
        os.chdir(Path(sys.executable).parent)

    # start main
    main()

    # testing
    # media_info_source = MediaInfo.parse(
    #     r"C:\Users\jlw_4\OneDrive\Desktop\test\Hollywood.Chainsaw.Hookers.1988.88FILMS.BluRay.1080p.DTS-HD.MA.5.1.AVC.REMUX-GHOSTFACE_track5_[eng]_DELAY 0ms.ac3"
    # )
    # test = determine_track_index(media_info_source, 1)
    # print(test)
