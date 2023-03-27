import argparse
import json
import os
import sys
import subprocess
import xml.etree.ElementTree as ET
from pymediainfo import MediaInfo
from pathlib import Path
import threading


if Path(sys.argv[0]).suffix == ".exe":
    os.chdir(os.path.dirname(sys.executable))


def validate_channels(value):
    valid_channels = [1, 2, 6]
    if value not in valid_channels:
        raise argparse.ArgumentTypeError(
            f'Invalid number of channels. Valid options: {valid_channels}')


def main():
    # Convert the relative paths to absolute paths
    ffmpeg_path = Path(Path.cwd() / 'apps/ffmpeg/ffmpeg.exe')
    dee_path = Path(Path.cwd() / 'apps/dee/dee.exe')

    # Check that the required paths exist
    # for key, value in config.items():
    #     if not os.path.exists(value):
    #         raise ValueError(f'{key} path not found: {value}')

    # Parse the command line arguments
    parser = argparse.ArgumentParser(description='A command line tool.')
    parser.add_argument('-i', '--input', type=str,
                        required=True, help='The input file path.')
    parser.add_argument('-o', '--output', type=str,
                        required=True, help='The output file path.')
    parser.add_argument('-c', '--channels', type=int,
                        required=True, help='The number of channels. Valid options: 1, 2, 6.')
    parser.add_argument('-b', '--bitrate', type=int,
                        required=True, help='The bitrate in Kbps.')
    parser.add_argument('-t', '--track-index', type=int,
                        default=0, help='The index of the audio track to use.')
    parser.add_argument('-d', '--delay', type=int, default=0,
                        help='The delay in milliseconds.')
    args = parser.parse_args()
    
    validate_channels(args.channels)

    # Check that the input file exists
    if not os.path.exists(args.input):
        raise ValueError(f'Input file not found: {args.input}')

    # Call ffprobe to get information about the audio stream
    # ffprobe_cmd = [
    #     config["ffprobe_path"],
    #     "-v", "quiet",
    #     "-select_streams", f"a:{args.track_index}",
    #     "-print_format", "json",
    #     "-show_format",
    #     "-show_streams",
    #     args.input
    # ]

    # info_string = subprocess.check_output(ffprobe_cmd, encoding='utf-8')
    # info = json.loads(info_string)
    
    #
    media_info_source = MediaInfo.parse(args.input)
    track_info = media_info_source.tracks[args.track_index + 1]
    # print(track_info)
    #

    # Extract info from the result
    try:
        sample_rate = track_info.sampling_rate
    except AttributeError:
        sample_rate = None    
    
    channels = track_info.channel_s
    
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
        matrix_encoding_arg = f'[a:{args.track_index}]aresample=matrix_encoding=dplii'

    resample_args = []
    if resample:
        resample_args = [
            '-filter_complex', f'[a:{args.track_index}]aresample=resampler=soxr',
            matrix_encoding_arg,
            '-ar', sample_rate,
            '-precision', '28',
            '-cutoff', '1',
            '-dither_scale', '0']
    else:
        resample_args = ['-filter_complex', matrix_encoding_arg]

    # Work out if we need to do downmix
    downmix_config = 'off'
    if args.channels > channels:
        raise ValueError("Upmixing is not supported.")
    elif args.channels == 1:
        downmix_config = "mono"
    elif args.channels == 2:
        downmix_config = "stereo"
    elif args.channels == 6:
        downmix_config = "5.1"

    # Create the directory for the output file if it doesn't exist
    output_dir = os.path.dirname(args.output)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        output = os.path.abspath(args.output)

    # Create wav_filepath for the intermediate file
    # wav_file_path = os.path.splitext(args.input)[0] + ".wav"
    # print(args.input)
    
    base_dir = Path(args.output).parent
    
    wav_file_path = Path(base_dir / "testing123.wav")
    # print(wav_file_path)
    # exit()
    
    # real_wave = wav_file_path.replace(".wav_fake", ".wav")
    # Path(Path(wav_file_path).parent / "testing").mkdir(exist_ok=True)

    # Get the path to the template.xml file
    template_path = Path(Path.cwd() / 'runtime/template.xml')
    # Load the contents of the template.xml file into the dee_config variable
    xml_dee_config = ET.parse(template_path)
    xml_root = xml_dee_config.getroot()

    # Update the template values
    xml_pcm_to_ddp = xml_root.find("filter/audio/pcm_to_ddp")
    xml_downmix_config_elem = xml_pcm_to_ddp.find("downmix_config")
    xml_downmix_config_elem.text = downmix_config
    xml_downmix_config_elem = xml_pcm_to_ddp.find("data_rate")
    xml_downmix_config_elem.text = str(args.bitrate)

    xml_input = xml_root.find("input/audio/wav")
    xml_input_file_name = xml_input.find("file_name")
    xml_input_file_name.text = os.path.basename(Path(wav_file_path))
    xml_input_file_path = xml_input.find("storage/local/path")
    xml_input_file_path.text = os.path.dirname(Path(wav_file_path))

    xml_output = xml_root.find("output/ac3")
    xml_output_file_name = xml_output.find("file_name")
    xml_output_file_name.text = os.path.basename(Path(base_dir / Path(args.output)))
    xml_output_file_path = xml_output.find("storage/local/path")
    xml_output_file_path.text = str(base_dir)

    xml_temp = xml_root.find("misc/temp_dir")
    xml_temp_path = xml_temp.find("path")
    xml_temp_path.text = str(base_dir)

    # Save out the updated template
    updated_template_file = Path(base_dir / Path(Path(args.input).name).with_suffix(".xml"))
    if os.path.exists(updated_template_file):
        os.remove(updated_template_file)
    xml_dee_config.write(updated_template_file)

    # Call ffmpeg to generate the wav file
    ffmpeg_cmd = [
        str(ffmpeg_path),
        '-y',
        '-drc_scale', '0',
        '-i', args.input,
        '-c', f'pcm_s{bits_per_sample}le',
        # *(resample_args),
        '-rf64', 'always',
        # '-f', 'wav',
        "-v", "info",
        "-hide_banner",
        wav_file_path
    ]
    # print(ffmpeg_cmd)
    # exit()

    # blah2 = 1
    with subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True) as f:
        # print(ffmpeg_cmd)
        for line in f.stdout:
            pass
            # print(line)
    
    # t1 = threading.Threadsubprocess.run(ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # print(ffmpeg_cmd)
    # subprocess.call(ffmpeg_cmd)
    # print("passed!")
    # new_dir = Path(Path(wav_file_path).parent / "testing")
    # Path(wav_file_path).replace(new_dir / Path(real_wave).name)
    # full_new_path = Path(new_dir / Path(real_wave).name)
    
    # print(full_new_path)
    
    # Call dee to generate the encode file
    dee_cm = [
        str(dee_path),
        '--progress-interval', '500',
        '--diagnostics-interval', '90000',
        '-x', updated_template_file,
        '--disable-xml-validation'
    ]

    # print(dee_cm)
    # exit()
    with subprocess.Popen(dee_cm, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True) as d:
        print(dee_cm)
        for line in d.stdout:
            pass
            # blah = line
    
    # subprocess.call(dee_cm)
    
    # Clean up temp files
    # os.remove(updated_template_file)
    # os.remove(Path(real_wave))
    Path(base_dir / "testing123.ac3").replace(args.output)


if __name__ == '__main__':
    main()
