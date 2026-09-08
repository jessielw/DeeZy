import logging
from collections.abc import Callable
from subprocess import PIPE, STDOUT, Popen

from rich.console import Console
from rich.live import Live
from rich.spinner import Spinner

from deezy.utils.logger import logger
from deezy.utils.progress import ProgressData, ProgressHandler

# FFMPEG only ever explains a failure in the output it already streamed past, so
# a bounded tail of it is kept to put a reason in the raised error
MAX_CAPTURED_LINES = 50


def _prepare_ffmpeg_command(cmd: list, duration: float | None) -> list:
    """Prepare FFMPEG command with appropriate options for progress tracking."""
    # make a copy to avoid modifying the original command list
    cmd = cmd.copy()

    # inject verbosity level based on logging level
    logger_level = logger.getEffectiveLevel()
    inject = cmd.index("-v") + 1
    if logger_level == logging.DEBUG:
        cmd.insert(inject, "info")
    else:
        cmd.insert(inject, "quiet")

    # add progress options before input if we have duration for accurate tracking
    if duration:
        input_index = cmd.index("-i")
        cmd.insert(input_index, "-progress")
        cmd.insert(input_index + 1, "pipe:1")
        cmd.insert(input_index + 2, "-nostats")

    return cmd


def _create_progress_parser(duration: float) -> Callable:
    """Create a progress parser for FFMPEG -progress output."""

    def parse_progress_output(line: str) -> ProgressData | None:
        if line.startswith("out_time_us="):
            try:
                current_us = int(line.split("=", 1)[1])
                current_seconds = current_us / 1_000_000
                duration_seconds = duration / 1000  # duration is in milliseconds
                progress_percent = min(
                    100.0, (current_seconds / duration_seconds) * 100
                )

                # format time nicely
                minutes = int(current_seconds // 60)
                seconds = current_seconds % 60
                if minutes > 0:
                    time_str = f"{minutes}m{seconds:.0f}s"
                else:
                    time_str = f"{seconds:.1f}s"

                return ProgressData(progress_percent, f"{time_str}")
            except (ValueError, ZeroDivisionError):
                pass
        return

    return parse_progress_output


def _process_with_progress_bar(
    proc: Popen, handler: ProgressHandler, step_label: str, duration: float, sink: list
) -> None:
    """Handle FFMPEG process with progress bar when duration is known."""
    parser = _create_progress_parser(duration)
    last_percent = 0.0

    with handler.progress_context(step_label) as (progress, task_id):
        if proc.stdout:
            for line in proc.stdout:
                line = line.strip()
                if progress_data := parser(line):
                    last_percent = progress_data.value
                    if progress and task_id is not None:
                        progress.update(task_id, completed=progress_data.value)
                        logger.debug(f"{step_label} {progress_data.formatted}")
                    else:
                        logger.info(f"{step_label} {progress_data.value:.1f}%")
                elif line.startswith("progress=end"):
                    logger.debug("FFMPEG progress completed")
                else:
                    logger.debug(line)
                    _capture(sink, line)

        # ensure completion
        handler.ensure_completion(last_percent, step_label, progress, task_id)


def _capture(sink: list, line: str) -> None:
    """Keep a bounded tail of FFMPEG output for error reporting."""
    if line:
        sink.append(line)
        del sink[:-MAX_CAPTURED_LINES]


def _process_with_spinner(
    proc: Popen, handler: ProgressHandler, step_label: str, sink: list
) -> None:
    """Handle FFMPEG process with loading spinner when duration is unknown."""

    if handler.should_use_bars:
        # use rich spinner for interactive terminals
        console = Console()
        spinner = Spinner("dots", text=f"{step_label} processing...")

        with Live(spinner, console=console, refresh_per_second=10, transient=False):
            if proc.stdout:
                for line in proc.stdout:
                    line = line.strip()
                    logger.debug(line)
                    _capture(sink, line)

        # show completion message
        console.print(f"✓ {step_label} completed")
    else:
        # simple text output for non-interactive environments
        logger.info(f"{step_label} processing...")

        if proc.stdout:
            for line in proc.stdout:
                line = line.strip()
                logger.debug(line)
                _capture(sink, line)

        logger.info(f"{step_label} completed")


def process_ffmpeg_job(
    cmd: list,
    steps: bool,
    duration: float | None,
    step_info: dict | None = None,
    no_progress_bars: bool = False,
) -> bool:
    """Processes file with FFMPEG while generating progress based on available information.

    When duration is provided, uses time-based progress tracking for accurate percentage.
    When duration is None, uses loading spinner instead of fake progress.

    Args:
        cmd (list): Base FFMPEG command list.
        steps (bool): True or False, to disable updating encode steps.
        duration (Union[float, None]): Can be None or duration in milliseconds.
            If None, spinner loading indicator is used instead.
        step_info (dict | None): Optional step context with 'current', 'total', 'name' keys.
        no_progress_bars (bool): Disable progress bars.
    """
    # prepare command with appropriate options
    prepared_cmd = _prepare_ffmpeg_command(cmd, duration)

    # setup progress handler
    handler = ProgressHandler(logger.getEffectiveLevel(), no_progress_bars, step_info)

    # determine task description
    if steps:
        step_label = handler.get_step_label(
            "FFMPEG", default_current=1, default_total=3
        )
    else:
        step_label = "FFMPEG"

    # execute FFMPEG with appropriate progress handling
    output_tail: list[str] = []
    with Popen(prepared_cmd, stdout=PIPE, stderr=STDOUT, text=True) as proc:
        if duration:
            _process_with_progress_bar(proc, handler, step_label, duration, output_tail)
        else:
            _process_with_spinner(proc, handler, step_label, output_tail)

        # check return code
        return_code = proc.poll()
        if return_code is None:
            return_code = proc.wait()

        if return_code != 0:
            detail = "\n".join(f"  {line}" for line in output_tail)
            raise ValueError(
                f"FFMPEG error (exit code {return_code}). Please re-run in debug mode."
                + (f"\n{detail}" if detail else "")
            )

    return True
