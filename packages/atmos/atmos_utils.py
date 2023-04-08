from argparse import ArgumentTypeError
from typing import Union
import xmltodict
from packages.atmos.xml_base import xml_audio_base_atmos
from packages.shared.shared_utils import save_xml
from pathlib import Path
import shutil
from subprocess import run, Popen, STDOUT, PIPE
import concurrent.futures


def generate_xml_atmos(
    bitrate: str,
    normalize: bool,
    wav_file_name: str,
    output_file_name: str,
    output_dir: Union[Path, str],
):
    """Handles the parsing/creation of XML file for DEE encoding (atmos)
    Args:
        bitrate (str): Bitrate in the format of '448'
        normalize: (bool): True or False, if set to True we will normalize loudness
        wav_file_name (str): File name only
        output_file_name (str): File name only
        output_dir (Union[Path, str]): File path only
    Returns:
        Path: Returns the correct path to the created template file
    """
    # Update the xml template values
    xml_base = xmltodict.parse(xml_audio_base_atmos)

    # xml wav filename/path
    xml_base["job_config"]["input"]["audio"]["wav"]["file_name"] = f'"{wav_file_name}"'
    xml_base["job_config"]["input"]["audio"]["wav"]["storage"]["local"][
        "path"
    ] = f'"{str(output_dir)}"'

    # xml eac3 filename/path
    xml_base["job_config"]["output"]["ec3"]["file_name"] = f'"{output_file_name}"'
    xml_base["job_config"]["output"]["ec3"]["storage"]["local"][
        "path"
    ] = f'"{str(output_dir)}"'

    # xml temp path config
    xml_base["job_config"]["misc"]["temp_dir"]["path"] = f'"{str(output_dir)}"'

    # # xml down mix config
    # xml_base["job_config"]["filter"]["audio"]["pcm_to_ddp"][
    #     "downmix_config"
    # ] = down_mix_config

    # if channels == 1:
    #     downmix_mode = "not_indicated"
    # elif channels == 2:
    #     if stereo_down_mix == "standard":
    #         downmix_mode = "ltrt"
    #     elif stereo_down_mix == "dplii":
    #         downmix_mode = "ltrt-pl2"
    # elif channels >= 6:
    #     downmix_mode = "loro"
    # xml_base["job_config"]["filter"]["audio"]["pcm_to_ddp"]["downmix"][
    #     "preferred_downmix_mode"
    # ] = downmix_mode

    # xml bitrate config
    xml_base["job_config"]["filter"]["audio"]["encode_to_atmos_ddp"]["data_rate"] = str(
        bitrate
    )

    # if normalize is true, set template to normalize audio
    if normalize:
        # Remove measure_only, add measure_and_correct, with default preset of atsc_a85
        del xml_base["job_config"]["filter"]["audio"]["pcm_to_ddp"]["loudness"][
            "measure_only"
        ]
        xml_base["job_config"]["filter"]["audio"]["pcm_to_ddp"]["loudness"][
            "measure_and_correct"
        ] = {}
        xml_base["job_config"]["filter"]["audio"]["pcm_to_ddp"]["loudness"][
            "measure_and_correct"
        ]["preset"] = "atsc_a85"

    # create XML and return path to XML
    updated_template_file = save_xml(
        output_dir=output_dir, output_file_name=output_file_name, xml_base=xml_base
    )

    return updated_template_file


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
