import re
from subprocess import PIPE, Popen, STDOUT

from deezy.enums.shared import ProgressMode
from deezy.utils.utils import PrintSameLine


def process_dee_job(cmd: list, progress_mode: ProgressMode) -> bool:
    """Processes file with DEE while generating progress depending on progress_mode.

    Args:
        cmd (list): Base DEE cmd list
        progress_mode (ProgressMode): Options are ProgressMode.STANDARD or ProgressMode.DEBUG
    """

    # inject verbosity level into cmd list depending on progress_mode
    inject = cmd.index("--verbose") + 1
    if progress_mode == ProgressMode.STANDARD:
        cmd.insert(inject, "info")
    elif progress_mode == ProgressMode.DEBUG:
        cmd.insert(inject, "debug")

    # variable to update to print step 3
    last_number = 0

    with Popen(cmd, stdout=PIPE, stderr=STDOUT, universal_newlines=True) as proc:
        if progress_mode == ProgressMode.STANDARD:
            print("---- Step 2 of 3 ---- [DEE measure]")

        # initiate print on same line
        print_same_line = PrintSameLine()

        if proc.stdout:
            for line in proc.stdout:
                # check for all dee errors
                if "ERROR " in line:
                    raise ValueError(f"There was a DEE error: {line}")

                # If progress mode is quiet let's clean up progress output
                if progress_mode == ProgressMode.STANDARD:
                    # We need to wait for 'Stage progress' to prevent any errors
                    if "Stage progress" in line:
                        progress = _filter_dee_progress(line)

                        # If last number is greater than progress, this means we have already hit 100% on step 2
                        # So we can print the start of step 3
                        if progress:
                            if last_number > progress:
                                print("\n---- Step 3 of 3 ---- [DEE encode]")

                            # update progress but break when 100% is met to prevent printing 100% multiple times
                            if progress < 100.0:
                                print_same_line.print_msg(str(progress) + "%")
                            elif progress == 100.0 and last_number < 100.0:
                                print_same_line.print_msg(str(progress) + "%")

                            # update last number
                            last_number = progress
                else:
                    print(line.strip())

    if proc.returncode != 0:
        raise ValueError("There was an DEE error. Please re-run in debug mode.")
    else:
        return True


def _filter_dee_progress(line: str) -> float | None:
    """Filters dee's total progress output

    Args:
        line (str): Dee's cli output

    Returns:
        float: Progress output
    """
    get_progress = re.search(r"Stage\sprogress:\s(.+),", line)
    if get_progress:
        return float(get_progress.group(1))
