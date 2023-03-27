import argparse
import os
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
import sys
from pymediainfo import MediaInfo


def validate_channels(value: int):
    """Ensure we are utilizing the correct amount of channels"""
    
    # TODO: This might only be used if we set a bhdstudio switch or something? 
    # Since dee can handle ddp and even greater channels, if we're wanting to expand on this? 
    valid_channels = [1, 2, 6]
    if value not in valid_channels:
        raise argparse.ArgumentTypeError(
            f'Invalid number of channels. Valid options: {valid_channels}')
        

def process_job(cmd: list):
    """Process jobs"""
    
    # TODO: Handle total progress from output here?
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True) as proc:
        for line in proc.stdout:
            print(line.strip())


def main():
    # Define paths to ffmpeg and dee
    # TODO: Consider adding switch to accept FFMPEG path insted of bundling? 
    ffmpeg_path = Path(Path.cwd() / 'apps/ffmpeg/ffmpeg.exe')
    dee_path = Path(Path.cwd() / 'apps/dee/dee.exe')

    # Check that the required paths exist
    for exe_path in [ffmpeg_path, dee_path]:
        if not Path(exe_path).is_file():
            raise ValueError(f'{str(Path(exe_path).name)} path not found')

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

    # Parse file with MediaInfo
    media_info_source = MediaInfo.parse(args.input)
    
    # get selected track information (appending 1 to the track assuming there is video)
    # TODO: Add logic to correctly parse this and append the correct number depending on type of input
    track_info = media_info_source.tracks[args.track_index + 1]
    
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
    output_dir = Path(args.output).parent
    if not output_dir.exists():
        output_dir.mkdir(exist_ok=True)
        
    # strip spaces from output name since xml/dee.exe has issues with spacing
    stripped_file_output = str(Path(args.output).name).replace(" ", "")

    # Create wav_filepath for the intermediate file
    wav_file_path = os.path.splitext(args.input)[0] + ".wav"

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
    xml_input_file_path.text = str(output_dir)

    xml_output = xml_root.find("output/ac3")
    xml_output_file_name = xml_output.find("file_name")
    xml_output_file_name.text = os.path.basename(stripped_file_output)
    xml_output_file_path = xml_output.find("storage/local/path")
    xml_output_file_path.text = str(output_dir)

    xml_temp = xml_root.find("misc/temp_dir")
    xml_temp_path = xml_temp.find("path")
    xml_temp_path.text = str(output_dir)

    # Save out the updated template
    updated_template_file = Path(output_dir / Path(Path(args.input).name).with_suffix(".xml"))
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
        *(resample_args),
        '-rf64', 'always',
        wav_file_path
    ]
    process_job(ffmpeg_cmd)

    # Call dee to generate the encode file
    dee_cm = [
        str(dee_path),
        '--progress-interval', '500',
        '--diagnostics-interval', '90000',
        '-x', updated_template_file,
        '--disable-xml-validation'
    ]
    process_job(dee_cm)
    
    # Clean up temp files
    # TODO: Add an optional switch?
    os.remove(updated_template_file)
    os.remove(wav_file_path)
    
    # rename output file to what ever original defined output was
    # TODO: Add an optional switch?
    Path(output_dir / stripped_file_output).replace(Path(args.output))
    
    # TODO: Get rid of os module in favor of pathlib
    # TODO: Add script to build program for us in repo


if __name__ == '__main__':
    # check if we're running via script or bundled
    if Path(sys.argv[0]).suffix == ".exe":
        os.chdir(os.path.dirname(sys.executable))
        
    # start main
    main()
