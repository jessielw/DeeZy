import logging
from subprocess import PIPE, STDOUT, Popen

from deezy.utils.logger import logger
from deezy.utils.progress import DEEProgressHandler


def _parse_dee_execution_summary(output_lines: list) -> str | None:
    """Parse DEE output to extract execution summary and errors."""
    summary_start = False
    summary_lines = []
    error_lines = []
    time_elapsed = None

    for line in output_lines:
        line = line.strip()

        # look for execution summary section
        if "--- Execution summary starts here ---" in line:
            summary_start = True
            continue
        elif "Time elapsed:" in line and summary_start:
            time_elapsed = line
            break
        elif summary_start:
            summary_lines.append(line)
            if line.startswith("ERROR:"):
                error_lines.append(line)

    # only build error message if there are actual errors in the summary
    if error_lines:
        error_msg = "DEE execution failed:\n"
        for error_line in error_lines:
            error_msg += f"  {error_line}\n"

        # add timing information if available
        if time_elapsed:
            error_msg += f"  ({time_elapsed})"

        return error_msg.rstrip()

    return


def _process_dee_progress_line(line: str, handler, progress_state: dict) -> None:
    """Process a single line from DEE output for progress tracking."""
    progress_data, is_encode = handler.parse_dee_line(line)
    if not progress_data:
        return

    if is_encode:
        # handle encode phase - normalize progress to start from 0%
        if progress_state["encode_start_value"] is None:
            # first encode progress line - record the starting value
            progress_state["encode_start_value"] = progress_data.value
            # mark measure phase as complete when encode starts
            if not progress_state["measure_done"]:
                progress_state["measure_done"] = True
                # in no-progress-bars mode, explicitly show measure completion
                if progress_state["progress"] is None:
                    logger.info(f"{handler.measure_task_desc} 100.0%")

        # normalize encode progress to 0-100% range
        if progress_state["encode_start_value"] is not None:
            normalized_progress = (
                (progress_data.value - progress_state["encode_start_value"])
                / (100 - progress_state["encode_start_value"])
            ) * 100
            normalized_progress = max(
                0, min(100, normalized_progress)
            )  # clamp to 0-100
        else:
            normalized_progress = progress_data.value

        if (
            progress_state["progress"]
            and progress_state["encode_task_id"] is None
            and progress_state["measure_task_id"] is not None
        ):
            # complete measure and start encode
            progress_state["progress"].update(
                progress_state["measure_task_id"], completed=100
            )
            progress_state["progress"].refresh()
            progress_state["encode_task_id"] = progress_state["progress"].add_task(
                handler.encode_task_desc, total=100
            )
            # attach custom dialnorm to encode task if provided
            handler.attach_custom_dialnorm_to_encode(
                progress_state["progress"], progress_state["encode_task_id"]
            )

        if progress_state["progress"] and progress_state["encode_task_id"] is not None:
            progress_state["progress"].update(
                progress_state["encode_task_id"], completed=normalized_progress
            )
            logger.debug(f"{handler.encode_task_desc} {normalized_progress:.1f}%")
        else:
            # fallback for when rich progress is disabled
            logger.info(f"{handler.encode_task_desc} {normalized_progress:.1f}%")

        progress_state["last_encode"] = normalized_progress
    else:
        # handle measure phase
        if not progress_state["measure_done"]:
            if (
                progress_state["progress"]
                and progress_state["measure_task_id"] is not None
            ):
                progress_state["progress"].update(
                    progress_state["measure_task_id"], completed=progress_data.value
                )
                logger.debug(f"{handler.measure_task_desc} {progress_data.formatted}")
            else:
                # fallback for when rich progress is disabled
                logger.info(f"{handler.measure_task_desc} {progress_data.formatted}")

            progress_state["last_measure"] = progress_data.value
            if progress_data.value == 100.0:
                progress_state["measure_done"] = True


def process_dee_job(
    cmd: list,
    step_info: dict | None = None,
    no_progress_bars: bool = False,
    custom_dialnorm: int = 0,
) -> bool:
    """Processes file with DEE while generating progress and enhanced error reporting.

    Args:
        cmd (list): Base DEE cmd list.
        step_info (dict | None): Optional step context with 'current', 'total', 'name' keys.
        no_progress_bars (bool): Disable progress bars.
        custom_dialnorm (int): If user supplies custom dialnorm (0 is off).
    """
    # inject verbosity level into cmd list depending on logging level
    logger_level = logger.getEffectiveLevel()
    inject = cmd.index("--verbose") + 1
    if logger_level == logging.DEBUG:
        cmd.insert(inject, "debug")
    else:
        cmd.insert(inject, "info")

    # setup DEE progress handler
    handler = DEEProgressHandler(
        logger_level, no_progress_bars, step_info, custom_dialnorm
    )

    # collect all output for error parsing
    output_lines = []

    with Popen(cmd, stdout=PIPE, stderr=STDOUT, universal_newlines=True) as proc:
        progress_state = {
            "measure_done": False,
            "last_measure": 0.0,
            "last_encode": 0.0,
            "encode_task_id": None,
            "measure_task_id": None,
            "progress": None,
            "encode_start_value": None,
        }

        with handler.dee_progress_context() as (progress, measure_task_id, _):
            progress_state["progress"] = progress
            progress_state["measure_task_id"] = measure_task_id

            if proc.stdout:
                for line in proc.stdout:
                    line_stripped = line.strip()
                    output_lines.append(line_stripped)
                    logger.debug(line_stripped)

                    # process progress information
                    _process_dee_progress_line(line_stripped, handler, progress_state)
                    # ensure the measured dialnorm (if parsed) is appended to the progress
                    # task fields so the trailing DialnormColumn can render it. This call is idempotent.
                    try:
                        handler.append_measured_dialnorm(
                            progress_state.get("progress"),
                            progress_state.get("measure_task_id"),
                        )
                    except Exception:
                        # don't allow UI update failures to break DEE processing
                        logger.debug(
                            "Failed to append measured dialnorm to progress UI"
                        )

            # ensure completion for both phases
            if progress_state["progress"]:
                # progress bars handle completion automatically
                if (
                    progress_state["encode_task_id"] is None
                    and progress_state["last_measure"] == 100.0
                ):
                    progress_state["encode_task_id"] = progress_state[
                        "progress"
                    ].add_task(handler.encode_task_desc, total=100)
                    progress_state["progress"].update(
                        progress_state["encode_task_id"], completed=100
                    )
                    # attach custom dialnorm to encode task if provided
                    handler.attach_custom_dialnorm_to_encode(
                        progress_state["progress"], progress_state["encode_task_id"]
                    )
                    progress_state["progress"].refresh()
                elif (
                    progress_state["encode_task_id"] is not None
                    and progress_state["last_encode"] < 100.0
                ):
                    progress_state["progress"].update(
                        progress_state["encode_task_id"], completed=100
                    )
                    progress_state["progress"].refresh()
            else:
                # raw mode completion - ensure both phases show 100%
                if progress_state["measure_done"]:
                    # if measure completed, show it as 100%
                    handler.ensure_completion(100.0, handler.measure_task_desc)
                else:
                    # if measure didn't complete, show its last value
                    handler.ensure_completion(
                        progress_state["last_measure"], handler.measure_task_desc
                    )
                handler.ensure_completion(
                    progress_state["last_encode"], handler.encode_task_desc
                )

    return_code = proc.wait()
    if return_code != 0:
        # parse the output for detailed error information
        error_message = _parse_dee_execution_summary(output_lines)
        if error_message:
            raise ValueError(error_message)
        else:
            raise ValueError(
                f"DEE execution failed with exit code {return_code}. Please re-run in debug mode."
            )

    return True
