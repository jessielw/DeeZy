from pathlib import Path
import sys


def get_working_dir():
    """
    Used to determine the correct working directory automatically.
    This way we can utilize files/relative paths easily.

    Returns:
        (Path): Current working directory
    """
    # we're in a pyinstaller.exe bundle
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys.executable).parent

    # we're running from a *.py file
    else:
        return Path.cwd()


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
