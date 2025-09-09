import logging
from subprocess import PIPE, Popen, STDOUT

from deezy.utils.logger import logger
from deezy.utils.progress import ProgressHandler, create_ffmpeg_parser


def process_ffmpeg_job(
    cmd: list,
    steps: bool,
    duration: float | None,
    step_info: dict | None = None,
    no_progress_bars: bool = False,
):
    """Processes file with FFMPEG while generating progress depending on progress_mode.

    Args:
        cmd (list): Base FFMPEG command list.
        steps (bool): True or False, to disable updating encode steps.
        duration (Union[float, None]): Can be None or duration in milliseconds.
        step_info (dict | None): Optional step context with 'current', 'total', 'name' keys.
        no_progress_bars (bool): Disable progress bars.
    """
    # inject verbosity level into cmd list depending on logging level
    logger_level = logger.getEffectiveLevel()
    inject = cmd.index("-v") + 1
    if logger_level == logging.DEBUG:
        cmd.insert(inject, "info")
    else:
        cmd.insert(inject, "quiet")

    # Setup progress handler
    handler = ProgressHandler(logger_level, no_progress_bars, step_info)

    # Determine task description
    if steps:
        step_label = handler.get_step_label(
            "FFMPEG", default_current=1, default_total=3
        )
    else:
        step_label = "FFMPEG"

    with Popen(cmd, stdout=PIPE, stderr=STDOUT, text=True) as proc:
        if duration:
            parser = create_ffmpeg_parser(duration)
            last_percent = 0.0

            with handler.progress_context(step_label) as (progress, task_id):
                if proc.stdout:
                    for line in proc.stdout:
                        if "size=" in line:
                            if progress_data := handler.handle_progress_line(
                                line, step_label, parser, progress, task_id
                            ):
                                last_percent = progress_data.value
                                if progress_data.value >= 100.0:
                                    break
                        else:
                            logger.debug(line.strip())

                # Ensure completion
                handler.ensure_completion(last_percent, step_label, progress, task_id)
        else:
            # no duration, just log lines
            if proc.stdout:
                for line in proc.stdout:
                    logger.debug(line.strip())

    if proc.wait() != 0:
        raise ValueError("There was an FFMPEG error. Please re-run in debug mode.")
    return True
