import logging
from subprocess import PIPE, Popen, STDOUT

from deezy.utils.logger import logger
from deezy.utils.progress import DEEProgressHandler


def process_dee_job(
    cmd: list, step_info: dict | None = None, no_progress_bars: bool = False
) -> bool:
    """Processes file with DEE while generating progress depending on progress_mode.

    Args:
        cmd (list): Base DEE cmd list.
        step_info (dict | None): Optional step context with 'current', 'total', 'name' keys.
        no_progress_bars (bool): Disable progress bars.
    """
    # inject verbosity level into cmd list depending on logging level
    logger_level = logger.getEffectiveLevel()
    inject = cmd.index("--verbose") + 1
    if logger_level == logging.DEBUG:
        cmd.insert(inject, "debug")
    else:
        cmd.insert(inject, "info")

    # setup DEE progress handler
    handler = DEEProgressHandler(logger_level, no_progress_bars, step_info)

    with Popen(cmd, stdout=PIPE, stderr=STDOUT, universal_newlines=True) as proc:
        measure_done = False
        last_measure = 0.0
        last_encode = 0.0
        encode_task_id = None

        with handler.dee_progress_context() as (progress, measure_task_id, _):
            if proc.stdout:
                for line in proc.stdout:
                    logger.debug(line.strip())
                    if "ERROR " in line:
                        raise ValueError(f"There was a DEE error: {line}")

                    progress_data, is_encode = handler.parse_dee_line(line)
                    if progress_data:
                        if is_encode:
                            # handle encode phase
                            if (
                                progress
                                and encode_task_id is None
                                and measure_task_id is not None
                            ):
                                # complete measure and start encode
                                progress.update(measure_task_id, completed=100)
                                progress.refresh()
                                measure_done = True
                                encode_task_id = progress.add_task(
                                    handler.encode_task_desc, total=100
                                )

                            if progress and encode_task_id is not None:
                                progress.update(
                                    encode_task_id, completed=progress_data.value
                                )
                                logger.debug(
                                    f"{handler.encode_task_desc} {progress_data.formatted}"
                                )
                            else:
                                print(
                                    f"{handler.encode_task_desc} {progress_data.formatted}"
                                )
                                logger.debug(
                                    f"{handler.encode_task_desc} {progress_data.formatted}"
                                )

                            last_encode = progress_data.value
                        else:
                            # Handle measure phase
                            if not measure_done:
                                if progress and measure_task_id is not None:
                                    progress.update(
                                        measure_task_id, completed=progress_data.value
                                    )
                                    logger.debug(
                                        f"{handler.measure_task_desc} {progress_data.formatted}"
                                    )
                                else:
                                    print(
                                        f"{handler.measure_task_desc} {progress_data.formatted}"
                                    )
                                    logger.debug(
                                        f"{handler.measure_task_desc} {progress_data.formatted}"
                                    )

                                last_measure = progress_data.value
                                if progress_data.value == 100.0:
                                    measure_done = True

            # ensure completion for both phases
            if progress:
                # progress bars handle completion automatically
                if encode_task_id is None and last_measure == 100.0:
                    encode_task_id = progress.add_task(
                        handler.encode_task_desc, total=100
                    )
                    progress.update(encode_task_id, completed=100)
                    progress.refresh()
                elif encode_task_id is not None and last_encode < 100.0:
                    progress.update(encode_task_id, completed=100)
                    progress.refresh()
            else:
                # raw mode completion
                handler.ensure_completion(last_measure, handler.measure_task_desc)
                handler.ensure_completion(last_encode, handler.encode_task_desc)

    if proc.wait() != 0:
        raise ValueError("There was a DEE error. Please re-run in debug mode.")
    return True
