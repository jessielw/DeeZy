import re
from subprocess import PIPE, Popen, STDOUT
from typing import Union

from deezy.enums.shared import ProgressMode
from deezy.utils.utils import PrintSameLine


def process_ffmpeg_job(
    cmd: list,
    progress_mode: ProgressMode,
    steps: bool,
    duration: Union[float, None],
    step_info: dict | None = None,
):
    """Processes file with FFMPEG while generating progress depending on progress_mode.

    Args:
        cmd (list): Base FFMPEG command list
        progress_mode (ProgressMode): Options are ProgressMode.STANDARD or ProgressMode.DEBUG
        steps (bool): True or False, to disable updating encode steps
        duration (Union[float, None]): Can be None or duration in milliseconds
        step_info (dict | None): Optional step context with 'current', 'total', 'name' keys
        If set to None the generic FFMPEG output will be displayed
        If duration is passed then we can calculate the total progress for FFMPEG
    """
    # inject verbosity level into cmd list depending on progress_mode
    inject = cmd.index("-v") + 1
    if progress_mode is ProgressMode.STANDARD:
        cmd.insert(inject, "quiet")
    elif progress_mode is ProgressMode.DEBUG:
        cmd.insert(inject, "info")

    with Popen(cmd, stdout=PIPE, stderr=STDOUT, text=True) as proc:
        if progress_mode is ProgressMode.STANDARD and steps:
            if step_info:
                step_name = step_info.get("name", "FFMPEG")
                current = step_info.get("current", 1)
                total = step_info.get("total", 3)
                print(f"---- Step {current} of {total} ---- [{step_name}]")
            else:
                print("---- Step 1 of 3 ---- [FFMPEG]")

        # initiate print on same line
        print_same_line = PrintSameLine()

        if proc.stdout:
            for line in proc.stdout:
                # some audio formats actually do not have a "duration" in their raw containers,
                # if this is the case we will default ffmpeg to it's generic output string.
                if duration and progress_mode is ProgressMode.STANDARD:
                    # we need to wait for size= to prevent any errors
                    if "size=" in line:
                        percentage = convert_ffmpeg_to_percent(line, duration)
                        # update progress but break when 100% is met to prevent printing 100% multiple times
                        if percentage:
                            if percentage != "100.0%":
                                print_same_line.print_msg(percentage)
                            else:
                                # clear the progress line when we hit 100%
                                print_same_line.clear()
                                break
                else:
                    print(line.strip())

    if proc.returncode != 0:
        raise ValueError("There was an FFMPEG error. Please re-run in debug mode.")
    else:
        return True


def convert_ffmpeg_to_percent(line: str, duration: float) -> str | None:
    """
    Detect the format of 'HH:MM:SS' that FFMPEG provides, and convert it to milliseconds.
    This will allow us to generate an overall percentage based on the audio track's duration from the input.

    Args:
        line (str): FFMPEG generic output string
        duration (float): Source's audio track duration (ms)

    Returns:
        str: Formatted %
    """
    # sometimes FFMPEG can start at a negative (-) value, this will prevent
    # progress from breaking
    if "time=-" in line:
        return "0%"

    # once the time is not a negative value actual calculate progress
    else:
        time = re.search(r"(\d\d):(\d\d):(\d\d)", line.strip())
        if time:
            total_ms = (
                int(time.group(1)) * 3600000
                + int(time.group(2)) * 60000
                + int(time.group(3)) * 1000
            )
            progress = float(total_ms) / float(duration)
            percent = "{:.1%}".format(min(1.0, progress))
            return percent
