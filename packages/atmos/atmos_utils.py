from argparse import ArgumentTypeError
from typing import Union
import xmltodict
from packages.atmos.xml_base import xml_audio_base_atmos
from packages.shared.shared_utils import save_xml
from packages.shared.progress import process_ffmpeg
from pathlib import Path
import shutil
from subprocess import run, Popen, STDOUT, PIPE
import concurrent.futures


def create_temp_dir(dir_path: Path, temp_folder: str):
    """Creates a temporary directory deleting the old one if it already exists.

    Args:
        input_file (Path): Input file path to create temp directory beside it.
        temp_folder (str): Temp folder name.

    Returns:
        Path: Temporary directory
    """
    temp_dir = Path(dir_path / temp_folder)
    if temp_dir.exists():
        shutil.rmtree(path=temp_dir)

    temp_dir.mkdir()
    return temp_dir


def demux_true_hd(
    input_file: Path, temp_dir: Path, mkvextract: Path, mkv_track_num: int
):
    """We utilize mkvextract.exe to extract the THD/MLP file to the temporary directory.

    Args:
        input_file (Path): Path to the input file.
        temp_dir (Path): Temporary directory where files will be processed.
        mkvextract (Path): Full path to mkvextract.
        mkv_track_num (int): mkvextract's "tracks" number (FFMPEG base tracks including video).

    Returns:
        Path: Full path to the extracted thd/mlp
    """
    # generate name
    output_name = Path(temp_dir / "extracted_thd.mlp")

    # extract truehd file
    extract_true_hd_track = run(
        [
            mkvextract,
            str(input_file),
            "tracks",
            f"{str(mkv_track_num)}:{str(output_name)}",
        ]
    )

    # check for valid output
    if extract_true_hd_track.returncode == 0 and output_name.is_file():
        return output_name


def confirm_thd_track(thd_file: Path):
    """Checks binary for proper TrueHD bytes, raise an error if it's not correct.

    Args:
        thd_file (Path): Path to TrueHD/MLP file
    """
    with Path(thd_file).open("rb") as f:
        first_bytes = f.read(10)
        truehd_sync_word = 0xF8726FBA.to_bytes(4, "big")

        if truehd_sync_word not in first_bytes:
            raise ArgumentTypeError("Source file must be in untouched TrueHD format")


class AtmosDecodeMulti:
    """
    A class for decoding multiple atmos channels using subprocess.
    After this is complete, you can check to ensure .error is None.

    Args:
        subprocess_jobs_list (list): A list of subprocess jobs to be run.

    Attributes:
        error (bool): Indicates if an error has occurred in any of the subprocess jobs.
        completed_jobs (int): The number of completed subprocess jobs.
        total_jobs (int): The total number of subprocess jobs.
    """

    def __init__(self, subprocess_jobs_list: list):
        self.error = False
        self.completed_jobs = 0
        self.total_jobs = len(subprocess_jobs_list)

        print(f"Decoding {self.total_jobs} atmos channels.")

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.total_jobs
        ) as executor:
            future_to_job = {
                executor.submit(self.run_job, job): job for job in subprocess_jobs_list
            }
            for future in concurrent.futures.as_completed(future_to_job):
                job = future_to_job[future]
                if future.exception() is not None:
                    self.error = True
                    print(f"Job {job} failed with exception: {future.exception()}")

    def run_job(self, job):
        while True:
            line = job.stdout.readline()
            if not line:
                break

            if "ERROR" in line:
                self.error = True
                break

            # can print output of "line" here if we want

        if not self.error:
            self.completed_jobs += 1
            print(f"Decoding job {self.completed_jobs} of {self.total_jobs} completed.")

        return job.poll()


def atmos_decode_job_single(jobs_list: list):
    """Decode Atmos audio channels from a list of subprocess jobs.

    Args:
        jobs_list (list): A list of subprocess jobs representing Atmos audio channels to be decoded.

    Returns:
        bool: True if an error occurred during decoding, False otherwise.
    """
    for job_num, job in enumerate(jobs_list, start=1):
        print(f"Decoding channel {job_num} of {len(jobs_list)}")
        with Popen(job, stdout=PIPE, stderr=STDOUT, universal_newlines=True) as proc:
            for line in proc.stdout:
                if "ERROR" in line:
                    print(f"Error occurred while decoding channel {job_num}")
                    return True

    return False


def generate_truehd_decode_command(
    gst_launch_exe: Path,
    input_file: Path,
    output_wav_s: Path,
    current_channel_id: int,
    total_channel_s: int,
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
        "--gst-plugin-path",
        f'{str(Path(gst_launch_exe.parent.absolute() / "gst-plugins"))}',
        "filesrc",
        f"location={str(input_file.as_posix())}",
        "!",
        "dlbtruehdparse",
        "align-major-sync=false",
        "!",
        "dlbaudiodecbin",
        "truehddec-presentation=16",
        f"out-ch-config={total_channel_s}",
        "!",
        "deinterleave",
        "name=d",
        f"d.src_{str(current_channel_id)}",
        "!",
        "wavenc",
        "!",
        "filesink",
        f"location={str(output_wav_s.as_posix())}",
    ]


def generate_atmos_decode_jobs(
    gst_launch_exe: Path,
    temp_dir: Path,
    demuxed_thd: Path,
    channel_id: int,
    channel_names: list,
    atmos_decode_speed: str,
):
    """
    Generates list of decode jobs based on channel layout count. If speed is set to single or multi it appends
    the jobs differently and sends them to different functions to be handled.

    Args:
        gst_launch_exe (Path): Path to gst_launch_exe
        temp_dir (Path): Path to temp_dir
        demuxed_thd (Path): Path to demuxed_thd
        channel_id (int): Channel ID
        channel_names (list): List of channel names
        atmos_decode_speed (str): Can be single or multi

    Returns:
        list: Returns list with full paths to the decoded wav files
    """
    jobs_list = []
    output_wav_s_list = []
    for channel_count, channel_name in enumerate(channel_names):
        # generate wav name
        output_wav_s = Path(
            temp_dir / f"{str(channel_count)}_{channel_name}"
        ).with_suffix(".wav")
        # generate command
        command = generate_truehd_decode_command(
            Path(gst_launch_exe),
            Path(demuxed_thd),
            Path(output_wav_s),
            channel_count,
            channel_id,
        )

        # depending on atmos decode speed we'll either append only the command or subprocess objects
        if atmos_decode_speed == "single":
            jobs_list.append(command)
        elif atmos_decode_speed == "multi":
            jobs_list.append(
                Popen(command, stdout=PIPE, stderr=STDOUT, universal_newlines=True)
            )

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


def create_atmos_audio_file(
    ffmpeg: Path,
    temp_dir: Path,
    output_wav_s_list: list,
    progress_mode: str,
    duration: any,
    volume: float = 2.5,
):
    """
    This function combines all the mono wav files to a single file while retaining atmos.
    Atmos audio files are actually just CAF (Core Audio Files) with a different extension.
    Currently it's hard coded for 10 channel joins only.

    Since the conversion to PCM can make audio quiet, we also boost the volume by 250%.
    (Conversion is volume * 100 = result%).

    Args:
        ffmpeg (Path): Path to FFMPEG
        temp_dir (Path): Path to temp_dir
        output_wav_s_list (list): List of wav files to join
        progress_mode (str): Set's the designed progress output mode
        duration (any): Needed to convert progress to percent
        volume (float): This boosts the volume of the PCM file (volume * 100 = x%)

    Returns:
        Path: Path to combined w64 file
    """
    # atmos audio file path
    atmos_file_path = Path(temp_dir / Path("combined_wav.atmos.audio"))

    # append -i to all of the inputs
    inputs = [["-i", output_wav] for output_wav in output_wav_s_list]

    # create the command
    combine_cmd = [
        str(ffmpeg),
        "-y",
        *[item for sublist in inputs for item in sublist],
        "-c",
        "pcm_s24le",
        "-f",
        "caf",
        "-filter_complex",
        f"join=inputs=10:channel_layout=5.1+TFL+TFR+TBL+TBR:map=0.0-FL|1.0-FR|2.0-FC|3.0-LFE|4.0-BL|5.0-BR|6.0-TBL|7.0-TBR|8.0-TFL|9.0-TFR,volume={volume}",
        "-hide_banner",
        "-v",
        "-stats",
        str(atmos_file_path),
    ]

    print("Combining channels")
    combine_job = process_ffmpeg(
        cmd=combine_cmd, progress_mode=progress_mode, steps=False, duration=duration
    )
    if combine_job == 0 and atmos_file_path.is_file():
        # clean up single channel files
        # print("Deleting channel files")
        # for channel_file in output_wav_s_list:
        #     Path(channel_file).unlink()

        # return path to atmos audio file
        return atmos_file_path


def create_mezz_files(
    temp_dir: Path, atmos_audio_file: Path, template_dir: Path, fps: str
):
    """
    Copies template files over to the temp directory, renaming them, and modifying the
    main mezz file with needed information.

    Args:
        temp_dir (Path): Path to temp_directory
        atmos_audio_file (Path): Path to atmos_audio_file
        template_dir (Path): Path to template_dir
        fps (str): Can be one of (not_indicated, 23.976, 24, 25, 29.97, 30, 48, 50, 59.94, 60)

    Returns:
        Path: Main mezz file
    """
    # base name
    base_name = Path(Path(atmos_audio_file).name).with_suffix("")

    # copy and rename templates
    for template in template_dir.glob("*.*"):
        if "output.atmos" in template.name:
            copied_template_name = template.name.replace("output.atmos", str(base_name))
            shutil.copy(src=Path(template), dst=Path(temp_dir) / copied_template_name)

    # define main mezz file
    main_mezz = Path(Path(atmos_audio_file).parent) / Path(
        str(base_name) + "audio"
    ).with_suffix(".atmos")

    # read template into memory, replacing values, and then write new file with the updated values
    with open(main_mezz, "rt") as atmos_in, open(
        main_mezz.with_suffix(".new"), "wt"
    ) as atmos_out:
        mezz_to_memory = atmos_in.read()
        mezz_to_memory = (
            mezz_to_memory.replace(
                "metadata: output.atmos.metadata",
                f'metadata: {str(base_name.with_suffix(""))}.atmos.metadata',
            )
            .replace(
                "audio: output.atmos.audio",
                f'audio: {str(base_name.with_suffix(""))}.atmos.audio',
            )
            .replace("fps: 29.97", f"fps: {str(fps)}")
        )
        atmos_out.write(mezz_to_memory)

    # delete empty template and rename the new file to the original file name
    main_mezz.unlink()
    main_mezz.with_suffix(".new").replace(main_mezz)

    # return mezz file location
    if main_mezz.is_file():
        return main_mezz


def generate_xml_atmos(
    bitrate: int,
    atmos_mezz_file_name: str,
    atmos_mezz_file_dir: Union[Path, str],
    output_file_name: str,
    output_dir: Union[Path, str],
    fps: str,
):
    """Handles the parsing/creation of XML file for DEE encoding (atmos)
    Args:
        bitrate (int): Bitrate options are (Stream: [384, 448, 576, 640, 768] BluRay: [1024, 1152, 1280, 1408, 1512, 1536, 1664])
        atmos_mezz_file_name (str): File name only
        atmos_mezz_file_dir Union[Path, str]: Directory to atmos file
        output_file_name (str): File name only
        output_dir (Union[Path, str]): File path only
        fps (str): Can be one of (not_indicated, 23.976, 24, 25, 29.97, 30, 48, 50, 59.94, 60)

    Returns:
        Path: Returns the correct path to the created template file
    """
    # Update the xml template values
    xml_base = xmltodict.parse(xml_audio_base_atmos)

    # xml atmos filename/path
    xml_base["job_config"]["input"]["audio"]["atmos_mezz"][
        "file_name"
    ] = f'"{atmos_mezz_file_name}"'
    xml_base["job_config"]["input"]["audio"]["atmos_mezz"]["storage"]["local"][
        "path"
    ] = f'"{str(atmos_mezz_file_dir)}"'

    # xml ec3 filename/path
    xml_base["job_config"]["output"]["ec3"]["file_name"] = f'"{output_file_name}"'
    xml_base["job_config"]["output"]["ec3"]["storage"]["local"][
        "path"
    ] = f'"{str(output_dir)}"'

    # update fps sections
    xml_base["job_config"]["input"]["audio"]["atmos_mezz"]["timecode_frame_rate"] = fps
    xml_base["job_config"]["filter"]["audio"]["encode_to_atmos_ddp"][
        "timecode_frame_rate"
    ] = fps

    # xml bitrate config
    xml_base["job_config"]["filter"]["audio"]["encode_to_atmos_ddp"]["data_rate"] = str(
        bitrate
    )

    # xml temp path config
    xml_base["job_config"]["misc"]["temp_dir"]["path"] = f'"{str(output_dir)}"'

    # create XML and return path to XML
    updated_template_file = save_xml(
        output_dir=output_dir, output_file_name=output_file_name, xml_base=xml_base
    )

    return updated_template_file
