import argparse
import json
import os
import subprocess
import xml.etree.ElementTree as ET


def validate_channels(value):
    valid_channels = [1, 2, 6]
    if value not in valid_channels:
        raise argparse.ArgumentTypeError(
            f'Invalid number of channels. Valid options: {valid_channels}')


def main():
    # Get the absolute path to the "runtime" folder
    dirname = os.path.dirname(__file__)
    runtime_folder = os.path.join(dirname, 'runtime')

    # Load the configuration file
    with open(os.path.join(runtime_folder, 'config.json')) as f:
        config = json.load(f)

    # Convert the relative paths to absolute paths
    config['ffmpeg_path'] = os.path.abspath(os.path.join(dirname, config['ffmpeg_path']))
    config['ffprobe_path'] = os.path.abspath(os.path.join(dirname, config['ffprobe_path']))
    config['dee_path'] = os.path.abspath(os.path.join(dirname, config['dee_path']))

    # Check that the required paths exist
    for key, value in config.items():
        if not os.path.exists(value):
            raise ValueError(f'{key} path not found: {value}')

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
    ffprobe_cmd = [
        config["ffprobe_path"],
        "-v", "quiet",
        "-select_streams", f"a:{args.track_index}",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        args.input
    ]

    info_string = subprocess.check_output(ffprobe_cmd, encoding='utf-8')
    info = json.loads(info_string)

    # Extract info from the result
    sample_rate = int(info["streams"][0].get("sample_rate"))
    channels = int(info["streams"][0].get("channels"))
    duration = float(info["streams"][0].get("duration", -1))
    bits_per_sample = int(info["streams"][0].get(
        "bits_per_sample", info["streams"][0].get("bits_per_raw_sample", 32)))

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
    wav_file_path = os.path.splitext(args.input)[0] + ".wav"

    # Get the path to the template.xml file
    template_path = os.path.join(os.path.dirname(
        __file__), 'runtime', 'template.xml')
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
    xml_input_file_name.text = os.path.basename(wav_file_path)
    xml_input_file_path = xml_input.find("storage/local/path")
    xml_input_file_path.text = os.path.dirname(wav_file_path)

    xml_output = xml_root.find("output/ac3")
    xml_output_file_name = xml_output.find("file_name")
    xml_output_file_name.text = os.path.basename(args.output)
    xml_output_file_path = xml_output.find("storage/local/path")
    xml_output_file_path.text = os.path.dirname(args.output)

    xml_temp = xml_root.find("misc/temp_dir")
    xml_temp_path = xml_temp.find("path")
    xml_temp_path.text = os.path.dirname(args.output)

    # Save out the updated template
    updated_template_file = os.path.splitext(args.input)[0] + '.xml'
    if os.path.exists(updated_template_file):
        os.remove(updated_template_file)
    xml_dee_config.write(updated_template_file)

    # Call ffmpeg to generate the wav file
    ffmpeg_cmd = [
        config['ffmpeg_path'],
        '-y',
        '-drc_scale', '0',
        '-i', args.input,
        '-c', f'pcm_s{bits_per_sample}le',
        *(resample_args),
        '-rf64', 'always',
        wav_file_path
    ]

    with subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True) as proc:
        for line in proc.stdout:
            print(line.strip())

    # Call dee to generate the encode file
    dee_cm = [
        config['dee_path'],
        '--progress-interval', '500',
        '--diagnostics-interval', '90000',
        '-x', updated_template_file,
        '--disable-xml-validation'
    ]

    with subprocess.Popen(dee_cm, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True) as proc:
        for line in proc.stdout:
            print(line.strip())

    # Clean up temp files
    os.remove(updated_template_file)
    os.remove(wav_file_path)


if __name__ == '__main__':
    main()
