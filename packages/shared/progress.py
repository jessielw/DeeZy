from subprocess import Popen, PIPE, STDOUT
from packages.shared._version import program_name, __version__, developed_by
from packages.shared.shared_utils import PrintSameLine
from typing import Union
from re import search


def _display_banner():
    """Generate and display the banner"""
    print(f"{program_name} {__version__}\nDeveloped by: {developed_by}\n")


def _convert_ffmpeg_to_percent(line: str, duration: float):
    """
    Detect the format of 'HH:MM:SS' that FFMPEG provides, and convert it to milliseconds.
    This will allow us to generate an overall percentage based on the audio track's duration from the input.

    Args:
        line (str): FFMPEG generic output string
        duration (float): Source's audio track duration (ms)

    Returns:
        str: Formatted %
    """
    time = search(r"(\d\d):(\d\d):(\d\d)", line.strip())
    if time:
        total_ms = (
            int(time.group(1)) * 3600000
            + int(time.group(2)) * 60000
            + int(time.group(3)) * 1000
        )
        progress = float(total_ms) / float(duration)
        percent = "{:.1%}".format(min(1.0, progress))
        return percent


def _process_ffmpeg(
    cmd: list, progress_mode: str, steps: bool, duration: Union[float, None]
):
    """Processes file with FFMPEG while generating progress depending on progress_mode.

    Args:
        cmd (list): Base FFMPEG command list
        progress_mode (str): Options are "standard" or "debug"
        steps (bool): True or False, to disable updating encode steps
        duration (Union[float, None]): Can be None or duration in milliseconds
        If set to None the generic FFMPEG output will be displayed
        If duration is passed then we can calculate the total progress for FFMPEG
    """
    # inject verbosity level into cmd list depending on progress_mode
    inject = cmd.index("-v") + 1
    if progress_mode == "standard":
        cmd.insert(inject, "quiet")
    elif progress_mode == "debug":
        cmd.insert(inject, "info")

    with Popen(cmd, stdout=PIPE, stderr=STDOUT, universal_newlines=True) as proc:
        if progress_mode == "standard" and steps:
            print("---- Step 1 of 3 ---- [FFMPEG]")

        # initiate print on same line
        print_same_line = PrintSameLine()

        for line in proc.stdout:
            # Some audio formats actually do not have a "duration" in their raw containers,
            # if this is the case we will default ffmpeg to it's generic output string.
            if duration and progress_mode == "standard":
                # we need to wait for size= to prevent any errors
                if "size=" in line:
                    percentage = _convert_ffmpeg_to_percent(line, duration)

                    # update progress but break when 100% is met to prevent printing 100% multiple times
                    if percentage != "100.0%":
                        print_same_line.print_msg(percentage)
                    else:
                        print_same_line.print_msg("100.0%\n")
                        break
            else:
                print(line.strip())

    if proc.returncode != 0:
        raise ValueError("There was an FFMPEG error. Please re-run in debug mode.")
    else:
        return True


def _filter_dee_progress(line: str):
    """Filters dee's total progress output

    Args:
        line (str): Dee's cli output

    Returns:
        float: Progress output
    """
    get_progress = search(r"Stage\sprogress:\s(.+),", line)
    if get_progress:
        return float(get_progress.group(1))


def _process_dee(cmd: list, progress_mode: str, encoder_format: str):
    """Processes file with DEE while generating progress depending on progress_mode.

    Args:
        cmd (list): Base DEE cmd list
        progress_mode (str): Options are "standard" or "debug"
        encoder_format (str): Encoding format setting
    """

    # inject verbosity level into cmd list depending on progress_mode
    inject = cmd.index("--verbose") + 1
    if progress_mode == "standard":
        cmd.insert(inject, "info")
    elif progress_mode == "debug":
        cmd.insert(inject, "debug")

    # variable to update to print step 3
    last_number = 0

    with Popen(cmd, stdout=PIPE, stderr=STDOUT, universal_newlines=True) as proc:
        if progress_mode == "standard" and encoder_format != "atmos":
            print("---- Step 2 of 3 ---- [DEE measure]")
        else:
            print("\n---- Step 2 of 2 ---- [DEE encode]")

        # initiate print on same line
        print_same_line = PrintSameLine()

        for line in proc.stdout:
            # check for all dee errors
            if "ERROR " in line:
                raise ValueError(f"There was a DEE error: {line}")

            # If progress mode is quiet let's clean up progress output
            if progress_mode == "standard":
                # We need to wait for size= to prevent any errors
                if "Stage progress" in line:
                    progress = _filter_dee_progress(line)

                    # If last number is greater than progress, this means we have already hit 100% on step 2
                    # So we can print the start of step 3
                    if last_number > progress:
                        print("\n---- Step 3 of 3 ---- [DEE encode]")

                    # update progress but break when 100% is met to prevent printing 100% multiple times
                    if progress < 100.0:
                        print_same_line.print_msg(str(progress) + "%")
                    elif progress == 100.0 and last_number < 100.0:
                        print_same_line.print_msg(str(progress) + "%")

                    # update last number
                    last_number = progress
                pass
            else:
                print(line.strip())

    if proc.returncode != 0:
        raise ValueError("There was an DEE error. Please re-run in debug mode.")
    else:
        return True
