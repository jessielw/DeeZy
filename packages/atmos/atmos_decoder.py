from pathlib import Path, PosixPath
from typing import Union
from argparse import ArgumentTypeError
from packages.atmos import atmos_channels
from subprocess import PIPE, STDOUT, Popen, run
import shutil


def _check_disk_space(input_file: Path):
    """
    Check for input file's free space, rounding to nearest whole number.
    If there isn't at least 50 GB of space free, raise an ArgumentTypeError.

    Args:
        input_file (Path): Input file path
    """
    
    # get free space in bytes
    free_space_cwd = shutil.disk_usage(Path(input_file)).free
    
    # convert to GB's
    free_space_gb = round(free_space_cwd / (1024 ** 3))
    
    # check to ensure at least 50 GB's is free
    if free_space_gb < 50:
        raise ArgumentTypeError("There isn't enough free space to decode Dolby Atmos")


def create_temp_dir(input_file):
    """
    Create a temporary directory for handling atmos files, 
    deleting old ones if they already exist.

    Args:
        input_file (Path): Input file path to create temp directory beside it.

    Returns:
        Path: Temporary directory
    """
    temp_dir = Path(Path(input_file).parent / "atmos_temp")
    if temp_dir.exists():
        shutil.rmtree(path=temp_dir)

    temp_dir.mkdir()
    return temp_dir


def generate_truehd_decode_command(
            gst_launch_exe: Path,
            input_file: Path,
            output_wav_s: Path,
            current_channel_id: int,
            total_channel_s: int
    ):
    """
    Creates the decoding command needed to decode atmos. 
    It utilizes Dolby Reference Players plugins with gstreamer to decode.
    Gstreamer is very picky when it comes to the file paths, so we need
    to use Path().as_posix() for both "location" commands.  
    
    For "d.src_" we're subtracting 1 from the channel because we need to start at 0.

    Args:
        gst_launch_exe (Path): Full path to gst-launch-1.0.exe
        input_file (Path): Input path to the THD/MLP Atmos file
        output_wav_s (Path): Location where we will put the split WAV files
        current_channel_id (int): Current channel out of the total channels
        total_channel_s (int): Total channels to decode to

    Returns:
        list: Full command to be executed buy subprocess
    """
    return [
        str(Path(gst_launch_exe).absolute()),
        '--gst-plugin-path', f'{str(Path(gst_launch_exe.parent.absolute() / "gst-plugins"))}',
        'filesrc', f'location={str(input_file.as_posix())}', '!',
        'dlbtruehdparse', 'align-major-sync=false', '!',
        'dlbaudiodecbin', 'truehddec-presentation=16', f'out-ch-config={total_channel_s}', '!',
        'deinterleave', 'name=d', f'd.src_{str(current_channel_id)}', '!',
        'wavenc', '!', 'filesink', f'location={str(output_wav_s.as_posix())}'
    ]


def demux_true_hd(input_file: Path, temp_dir: Path, mkv_track_num: int):
    """We utilize mkvextract.exe to extract the THD/MLP file to the temporary directory.

    Args:
        input_file (Path): Path to the input file
        temp_dir (Path): Temporary directory where files will be processed
        mkv_track_num (int): mkvextract's "tracks" number (FFMPEG base tracks including video)

    Returns:
        Path: Full path to the extracted thd/mlp file
    """
    # generate name
    output_name = Path(temp_dir / "extracted_thd.mlp")
    
    # extract truehd file
    extract_true_hd_track = run(["apps/mkvextract/mkvextract.exe", str(input_file), "tracks", f'{str(mkv_track_num)}:{str(output_name)}'])
    
    # check for valid output
    if extract_true_hd_track.returncode == 0 and output_name.is_file():
        return output_name


def check_for_thd(input_file: Path): 
    with Path(input_file).open('rb') as f:
        first_bytes = f.read(10)
        truehd_sync_word = 0xF8726FBA.to_bytes(4, 'big')
        
        if truehd_sync_word not in first_bytes:
            # TODO Maybe fall back?
            raise ArgumentTypeError('Source file must be in untouched TrueHD format')
        
        
def combine_all_wav_s(ffmpeg, temp_dir, output_wav_s_list):
    output_w64 = Path(temp_dir / 'combined_wav').with_suffix('.w64')
    combine_cmd = [str(ffmpeg), 
                   "-i", output_wav_s_list[0], 
                   "-i", output_wav_s_list[1], 
                   "-i", output_wav_s_list[2],  
                   "-i", output_wav_s_list[3],  
                   "-i", output_wav_s_list[4],  
                   "-i", output_wav_s_list[5],  
                   "-i", output_wav_s_list[6],
                   "-i", output_wav_s_list[7], 
                   "-i", output_wav_s_list[8], 
                   "-i", output_wav_s_list[9], 
                   "-c", "pcm_s24le", "-filter_complex", 
                   "join=inputs=10:channel_layout=5.1+TFL+TFR+TBL+TBR:map=0.0-FL|1.0-FR|2.0-FC|3.0-LFE|4.0-BL|5.0-BR|6.0-TBL|7.0-TBR|8.0-TFL|9.0-TFR",
                   str(output_w64)]
    
    print("Combining channels")
    combine_job = run(combine_cmd)
    if combine_job.returncode == 0 and output_w64.is_file():
        
        # clean up single channel files
        print("Deleting channel files")
        for channel_file in output_wav_s_list:
            Path(channel_file).unlink()
        
        # return path to w64 file
        return output_w64
    
    
def create_atmos_audio(ffmpeg, w64_path):
    # atmos audio file path
    atmos_file_path = Path(Path(w64_path).parent / Path(str(Path(w64_path).name) + ".atmos")).with_suffix(".audio")
    
    # cmd
    print("Creating atmos audio file")
    cmd = [str(ffmpeg), "-i", str(w64_path), "-c:a", "copy", "-f", "caf", str(atmos_file_path)]
    
    # generate CAF atmos audio
    job = run(cmd)
    
    if job.returncode == 0 and atmos_file_path.is_file():
        
        # delete w64
        print("Deleting w64 file")
        Path(w64_path).unlink()
        
        # return path to atmos file
        return atmos_file_path
    
    
def create_mezz_files(temp_dir, atmos_audio_file, fps: str = "not_indicated"):
    mezz_templates = Path(r"E:\programming\BHDStudio-DEEWrapper\apps\drp\channel_layouts\5.1.4").glob("*.*")
    
    # base name
    base_name = Path(Path(atmos_audio_file).name).with_suffix("")
    
    # copy and rename templates
    for template in mezz_templates:
        if "output.atmos" in template.name:
            copied_template_name = template.name.replace("output.atmos", str(base_name))
            shutil.copy(src=Path(template), dst=Path(temp_dir) / copied_template_name)
            
    # define main mezz file
    main_mezz = Path(Path(atmos_audio_file).parent) / Path(str(base_name) + "audio").with_suffix(".atmos")
    
    # read template into memory, replacing values, and then write new file with the updated values
    with open(main_mezz, 'rt') as atmos_in, open(main_mezz.with_suffix('.new'), 'wt') as atmos_out:
        mezz_to_memory = atmos_in.read()
        mezz_to_memory = mezz_to_memory.replace('metadata: output.atmos.metadata', f'metadata: {str(base_name.with_suffix(""))}.atmos.metadata').replace('audio: output.atmos.audio', f'audio: {str(base_name.with_suffix(""))}.atmos.audio').replace('fps: 29.97', f'fps: {str(fps)}')
        atmos_out.write(mezz_to_memory)

    # delete empty template and rename the new file to the original file name
    main_mezz.unlink()
    main_mezz.with_suffix('.new').replace(main_mezz)

    # return mezz file location
    if main_mezz.is_file():
        return main_mezz
    


def atmos_decode(gst_launch_exe, input_file, ffmpeg_thd_track):
    # check for free space
    _check_disk_space(input_file)
    
    # create temp directory
    # temp_dir = create_temp_dir(input_file)
    temp_dir = Path(r"C:\Users\jlw_4\OneDrive\Desktop\Luca.2021.UHD.BluRay.2160p.TrueHD.Atmos.7.1.DV.HEVC.HYBRID.REMUX-FraMeSToR\atmos_temp")
    
    # demux true hd atmos track
    # demuxed_thd = demux_true_hd(input_file, temp_dir, ffmpeg_thd_track)
    # if not demuxed_thd:
    #     #TODO We need to fall back or something here?
    #     pass
    
    demuxed_thd = Path(r"C:\Users\jlw_4\OneDrive\Desktop\Luca.2021.UHD.BluRay.2160p.TrueHD.Atmos.7.1.DV.HEVC.HYBRID.REMUX-FraMeSToR\atmos_temp\extracted_thd.mlp")
    
    # check to ensure valid truehd
    check_for_thd(demuxed_thd)
    
    # get needed channel layout (since we're only looking to support 5.1.4 for now it'll be hard coded)
    channel_layout = atmos_channels["5.1.4"]
    channel_id = channel_layout["id"]
    channel_names = channel_layout["names"]

    # define an error variable incase we need to break from the loop
    error = False
    
    # define progress variable
    progress_var = ""
    
    # create a list of output_wav files
    output_wav_s_list = []
    
    # process the channels 1 by 1
    # processes = []
    # for channel_count, channel_name in enumerate(channel_names):
        
    #     # generate wav name
    #     output_wav_s = Path(temp_dir / f'{str(channel_count)}_{channel_name}').with_suffix(".wav")

    #     # generate command
    #     command = generate_truehd_decode_command(Path(gst_launch_exe), Path(demuxed_thd), Path(output_wav_s), channel_count, channel_id)

        
    #     # temp
    #     processes.append(Popen(command))
    #     output_wav_s_list.append(output_wav_s)
    #     #
    # for process in processes:
    #     process.wait()
    
    # print(processes)
    # print("\n\n\n")
    # print(output_wav_s_list)
        
        # # decode
        # with Popen(command, stdout=PIPE, stderr=STDOUT, universal_newlines=True) as proc:
        #     for line in proc.stdout:
        #         print(line)
                
        #         # if there are any errors we need to break from this and fall back
        #         if "ERROR" in line:
        #             error = True
        #             break
                
        #         # if no errors are detected decode the channels 1 by 1 updating progress for each channel
        #         else:
        #             generate_progress = f"Decoding channel {str(channel_count)} of {str(len(channel_names))}"
        #             if progress_var != generate_progress:
        #                 progress_var = generate_progress
        #                 print(generate_progress)
        
        # if there was any errors detected, break from the for loop and fall back
        # if error:
        #     #TODO we need to fall back here?
        #     break
        
        # if there was no error add wav files to list to be used later
        # else:
        #     output_wav_s_list.append(output_wav_s)
    
    # testing list, delete later
    # output_wav_s_list = []
    # for x in Path(r"C:\Users\jlw_4\OneDrive\Desktop\Luca.2021.UHD.BluRay.2160p.TrueHD.Atmos.7.1.DV.HEVC.HYBRID.REMUX-FraMeSToR").glob("*.wav"):
    #     output_wav_s_list.append(x)
        
    # print(output_wav_s_list)
        
    if not error:
        # generate combined wav
        # generate_w64 = combine_all_wav_s("ffmpeg", temp_dir, output_wav_s_list)
        
        # generate atmos audio file
        # generate_atmos_audio_file = create_atmos_audio("ffmpeg", r"C:\Users\jlw_4\OneDrive\Desktop\Luca.2021.UHD.BluRay.2160p.TrueHD.Atmos.7.1.DV.HEVC.HYBRID.REMUX-FraMeSToR\atmos_temp\combined_wav.w64")
        
        # create atmos mezz files
        create_mezz_files(temp_dir, r"C:\Users\jlw_4\OneDrive\Desktop\Luca.2021.UHD.BluRay.2160p.TrueHD.Atmos.7.1.DV.HEVC.HYBRID.REMUX-FraMeSToR\atmos_temp\combined_wav.atmos.audio", "FAKEFPS_FIX")
