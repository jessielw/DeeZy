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
    rename_thd_mlp,
)
from packages.shared.shared_utils import check_disk_space


def atmos_decode(
    gst_launch: Path,
    mkvextract: Path,
    ffmpeg: Path,
    input_file: Path,
    track_number: int,
    atmos_decode_workers: int,
    source_fps: str,
    duration: any,
    progress_mode: str,
    atmos_channel_config: str,
):
    """_summary_

    Args:
        gst_launch (Path): Path to gst_launch executable
        mkvextract (Path): Path to mkvextract executable
        ffmpeg (Path): Path to ffmpeg executable
        input_file (Path): Path to thd/mlp input file
        track_number (int): Base "tracks" number (ffmpeg 0:x)
        atmos_decode_workers (int): Desired amount of decode jobs to do at one time
        source_fps (str): FPS of input file
        duration (any): Duration of input file
        progress_mode (str): CLI progress mode
        atmos_channel_config (str): Desired Atmos channel configuration

    Returns:
        Path: Path to main mezz file
    """
    # check for free space
    check_disk_space(drive_path=Path(input_file), free_space=50)

    # # create temp directory
    temp_dir = create_temp_dir(
        dir_path=Path(input_file).parent,
        temp_folder=f"{str(Path(Path(input_file).name).with_suffix(''))}_atmos",
    )

    # demux truehd atmos track if it's in a supported matroska container
    if input_file.suffix in (".mkv", ".mka"):
        demuxed_thd = demux_true_hd(
            input_file=Path(input_file),
            temp_dir=temp_dir,
            mkvextract=Path(mkvextract),
            mkv_track_num=track_number,
        )

    # if truehd track is already in it's raw format
    elif input_file.suffix in (".mlp", ".thd"):
        demuxed_thd = rename_thd_mlp(thd_file=Path(input_file))

    # check for any other potential containers
    else:
        raise ArgumentTypeError("Unknown input type for TrueHD")

    # raise error if demuxed_thd does not exist
    if not demuxed_thd:
        raise ArgumentTypeError(
            "There was an error extracting/parsing the TrueHD/MLP track."
        )

    # check to ensure valid truehd
    confirm_thd_track(thd_file=demuxed_thd)

    # get needed channel layout
    channel_id = atmos_channels[atmos_channel_config]["id"]
    channel_names = atmos_channels[atmos_channel_config]["names"]

    # decode
    decode_job = generate_atmos_decode_jobs(
        gst_launch_exe=Path(gst_launch),
        temp_dir=temp_dir,
        demuxed_thd=demuxed_thd,
        channel_id=channel_id,
        channel_names=channel_names,
        atmos_decode_workers=atmos_decode_workers,
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
        mezz_file = create_mezz_files(
            temp_dir=temp_dir,
            atmos_audio_file=Path(generate_atmos_audio_file),
            template_dir=Path(
                Path(gst_launch).parent / "channel_layouts" / atmos_channel_config
            ),
            fps=source_fps,
        )

        # if mezz files are created successfully return them for DEE
        if mezz_file:
            return mezz_file
    else:
        return False
