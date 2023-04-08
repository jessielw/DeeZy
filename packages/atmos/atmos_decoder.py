from pathlib import Path
from argparse import ArgumentTypeError
from packages.atmos import atmos_channels
from packages.atmos.atmos_utils import (
    create_temp_dir,
    demux_true_hd,
    confirm_thd_track,
    create_atmos_audio_file,
    create_mezz_files,
    generate_atmos_decode_jobs,
)
from packages.shared.shared_utils import check_disk_space


def atmos_decode(
    gst_launch: Path,
    mkvextract: Path,
    ffmpeg: Path,
    input_file: Path,
    track_number: int,
    atmos_decode_speed: str,
    source_fps: str,
    duration: any,
    progress_mode: str,
):
    """_summary_

    Args:
        gst_launch (Path): Path to gst_launch executable
        mkvextract (Path): Path to mkvextract executable
        ffmpeg (Path): Path to ffmpeg executable
        input_file (Path): Path to thd/mlp input file
        track_number (int): Base "tracks" number (ffmpeg 0:x)
        atmos_decode_speed (str): Single threaded or multithreaded decoding process
        source_fps (str): FPS of input file
        duration (any): Duration of input file
        progress_mode (str): CLI progress mode

    Returns:
        Path: Path to main mezz file
    """
    # check for free space
    check_disk_space(drive_path=Path(input_file), free_space=50)

    # # create temp directory
    temp_dir = create_temp_dir(
        dir_path=Path(input_file).parent, temp_folder="atmos_temp"
    )

    # demux true hd atmos track
    demuxed_thd = demux_true_hd(
        input_file=Path(input_file),
        temp_dir=temp_dir,
        mkvextract=Path(mkvextract),
        mkv_track_num=track_number,
    )
    if not demuxed_thd:
        raise ArgumentTypeError("There was an error extracting the TrueHD/MLP track.")

    # check to ensure valid truehd
    confirm_thd_track(thd_file=demuxed_thd)

    # get needed channel layout (since we're only looking to support 5.1.4 for now it'll be hard coded)
    channel_id = atmos_channels["5.1.4"]["id"]
    channel_names = atmos_channels["5.1.4"]["names"]

    # decode
    decode_job = generate_atmos_decode_jobs(
        gst_launch_exe=Path(gst_launch),
        temp_dir=temp_dir,
        demuxed_thd=demuxed_thd,
        channel_id=channel_id,
        channel_names=channel_names,
        atmos_decode_speed=atmos_decode_speed,
    )

    if decode_job:
        # generate atmos audio file
        generate_atmos_audio_file = create_atmos_audio_file(
            ffmpeg=ffmpeg,
            temp_dir=temp_dir,
            output_wav_s_list=decode_job,
            progress_mode=progress_mode,
            duration=duration,
        )

        # create atmos mezz files (currently just hard coded channel layout)
        create_mezz_files(
            temp_dir=temp_dir,
            atmos_audio_file=Path(generate_atmos_audio_file),
            template_dir=Path(Path(gst_launch).parent / "channel_layouts" / "5.1.4"),
            fps=source_fps,
        )

        # if mezz files are created successfully return them for DEE
        if create_mezz_files:
            return create_mezz_files
