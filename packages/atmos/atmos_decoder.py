from pathlib import Path, PosixPath
from typing import Union
from argparse import ArgumentTypeError
from packages.atmos import atmos_channels
from packages.atmos.atmos_utils import create_temp_dir, demux_true_hd, confirm_thd_track, AtmosDecodeMulti, atmos_decode_job_single
from packages.shared.shared_utils import check_disk_space
from subprocess import PIPE, STDOUT, Popen, run
import shutil
import concurrent.futures



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
    
    


# def atmos_decode_job_multi(subprocess_jobs_list: list): 
#     def handle_output(pipe):
#         for line in iter(pipe.readline, b''):
#             # Do something with the output
#             print(line.strip())
    
#     # Iterate over the subprocesses and read their output in real-time
#     for job in subprocess_jobs_list:
#         handle_output(job.stdout)

#     # Wait for the subprocesses to complete
#     for job in subprocess_jobs_list:
#         job.wait()
        

            

def generate_atmos_decode_jobs(gst_launch_exe: Path, temp_dir: Path, demuxed_thd: Path, channel_id: int, channel_names: list, atmos_decode_speed: str):    
    jobs_list = []
    output_wav_s_list = []
    for channel_count, channel_name in enumerate(channel_names): 
        # generate wav name
        output_wav_s = Path(temp_dir / f'{str(channel_count)}_{channel_name}').with_suffix(".wav")
         # generate command
        command = generate_truehd_decode_command(Path(gst_launch_exe), Path(demuxed_thd), Path(output_wav_s), channel_count, channel_id)

        # depending on atmos decode speed we'll either append only the command or subprocess objects
        if atmos_decode_speed == "single":
            jobs_list.append(command)
        elif atmos_decode_speed == "multi":
            jobs_list.append(Popen(command, stdout=PIPE, stderr=STDOUT, universal_newlines=True))
            
        # add output wav's to a list to keep track of them
        output_wav_s_list.append(output_wav_s)
    
    # send the list to to the function for processing the list
    if atmos_decode_speed == "single":
        decode_error = atmos_decode_job_single(jobs_list=jobs_list)
    elif atmos_decode_speed == "multi":
        decode_error = AtmosDecodeMulti(subprocess_jobs_list=jobs_list).error  
        
    # check to ensure no error happened during decode and return wav list
    if not decode_error:
        return output_wav_s_list
    else:
        return None
        


def atmos_decode(gst_launch: Path,
                 mkvextract: Path,
                 ffmpeg: Path,
                 input_file: Path,
                 track_number: int,
                 atmos_decode_speed: str):
    # check for free space
    check_disk_space(drive_path=Path(input_file), free_space=50)
    
    # create temp directory
    # temp_dir = create_temp_dir(dir_path=Path(input_file).parent, temp_folder="atmos_temp")
    temp_dir = Path(r"C:\Users\jlw_4\OneDrive\Desktop\Luca.2021.UHD.BluRay.2160p.TrueHD.Atmos.7.1.DV.HEVC.HYBRID.REMUX-FraMeSToR\atmos_temp")
    
    # demux true hd atmos track
    # demuxed_thd = demux_true_hd(input_file=Path(input_file), temp_dir=temp_dir, mkvextract=Path(mkvextract), mkv_track_num=track_number)
    # if not demuxed_thd:
    #     raise ArgumentTypeError("There was an error extracting the TrueHD/MLP track.")
    # demuxed_thd = Path(r"C:\Users\jlw_4\OneDrive\Desktop\Luca.2021.UHD.BluRay.2160p.TrueHD.Atmos.7.1.DV.HEVC.HYBRID.REMUX-FraMeSToR\Luca.2021.UHD.BluRay.2160p.TrueHD.Atmos.7.1.DV.HEVC.HYBRID.REMUX-FraMeSToR.mkv")
    demuxed_thd = Path(r"C:\Users\jlw_4\OneDrive\Desktop\Luca.2021.UHD.BluRay.2160p.TrueHD.Atmos.7.1.DV.HEVC.HYBRID.REMUX-FraMeSToR\atmos_temp\extracted_thd.mlp")
    # check to ensure valid truehd
    confirm_thd_track(thd_file=demuxed_thd)
    
    # get needed channel layout (since we're only looking to support 5.1.4 for now it'll be hard coded)
    channel_id = atmos_channels["5.1.4"]["id"]
    channel_names = atmos_channels["5.1.4"]["names"]
    
    # decode
    decode_job = generate_atmos_decode_jobs(gst_launch_exe=Path(gst_launch), temp_dir=temp_dir, demuxed_thd=demuxed_thd, channel_id=channel_id, channel_names=channel_names, atmos_decode_speed=atmos_decode_speed)
    
    if decode_job:
        pass
        # generate combined wav
        # generate_w64 = combine_all_wav_s("ffmpeg", temp_dir, output_wav_s_list)
        
        # generate atmos audio file
        # generate_atmos_audio_file = create_atmos_audio("ffmpeg", r"C:\Users\jlw_4\OneDrive\Desktop\Luca.2021.UHD.BluRay.2160p.TrueHD.Atmos.7.1.DV.HEVC.HYBRID.REMUX-FraMeSToR\atmos_temp\combined_wav.w64")
        
        # create atmos mezz files
        # create_mezz_files(temp_dir, r"C:\Users\jlw_4\OneDrive\Desktop\Luca.2021.UHD.BluRay.2160p.TrueHD.Atmos.7.1.DV.HEVC.HYBRID.REMUX-FraMeSToR\atmos_temp\combined_wav.atmos.audio", "FAKEFPS_FIX")
