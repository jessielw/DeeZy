import logging
import re
import sys
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from rich.progress import (
    BarColumn,
    Progress,
    ProgressColumn,
    SpinnerColumn,
    TaskID,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.text import Text

from deezy.utils.logger import logger, logger_manager


@dataclass(slots=True)
class ProgressData:
    """Container for progress information"""

    value: float
    formatted: str


class ProgressHandler:
    """
    Handles progress display logic for processors.

    Automatically detects the appropriate progress display method:
    - Rich progress bars for interactive terminals
    - Simple text output for non-interactive environments, CI/CD, or when wrapped by other tools

    Environment variables that disable rich progress:
    - NO_COLOR: Standard env var to disable colored output
    - DEEZY_NO_PROGRESS: DeeZy-specific flag to force simple text progress
    - CI, GITHUB_ACTIONS, GITLAB_CI, etc.: Automatically detected CI environments

    For wrapper applications, set DEEZY_NO_PROGRESS=1 to ensure clean text output.
    """

    __slots__ = ("logger_level", "no_progress_bars", "step_info", "should_use_bars")

    def __init__(
        self, logger_level: int, no_progress_bars: bool, step_info: dict | None = None
    ) -> None:
        self.logger_level = logger_level
        self.no_progress_bars = no_progress_bars
        self.step_info = step_info
        self.should_use_bars = self._should_show_rich_progress()

    def _should_show_rich_progress(self) -> bool:
        """Determine if rich progress bars should be used"""
        # user explicitly disabled progress bars
        if self.no_progress_bars:
            return False

        # debug mode should use simple text output
        if self.logger_level <= logging.DEBUG:
            return False

        # check if stdout is connected to a terminal (TTY)
        if not sys.stdout.isatty():
            return False

        # all checks passed, use rich progress bars
        return True

    def get_step_label(
        self, base_name: str, default_current: int = 1, default_total: int = 3
    ) -> str:
        """Generate step label from step_info or defaults"""
        # Only include worker prefix in labels for rich progress bars
        # For plain text, the logger manager handles the prefix automatically
        worker_prefix = (
            logger_manager.get_worker_prefix() if self.should_use_bars else None
        )

        if self.step_info:
            name = self.step_info.get("name", base_name)
            current = self.step_info.get("current", default_current)
            total = self.step_info.get("total", default_total)
            base_label = f"{name} ({current} of {total})"
        else:
            base_label = f"{base_name} ({default_current} of {default_total})"

        if worker_prefix:
            return f"{worker_prefix}: {base_label}".ljust(30)
        return base_label.ljust(20)

    @contextmanager
    def progress_context(
        self, task_desc: str
    ) -> Generator[tuple[Progress, TaskID] | tuple[None, None], Any, None]:
        """Context manager for progress bars"""
        if self.should_use_bars:
            with Progress(
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                TimeRemainingColumn(),
                SpinnerColumn(),
                transient=False,
            ) as progress:
                task_id = progress.add_task(task_desc, total=100)
                yield progress, task_id
        else:
            yield None, None

    def handle_progress_line(
        self,
        line: str,
        step_label: str,
        parser_func: Callable[[str], ProgressData | None],
        progress=None,
        task_id=None,
    ) -> ProgressData | None:
        """Generic progress line handler"""
        if progress_data := parser_func(line):
            if progress and task_id is not None:
                progress.update(task_id, completed=progress_data.value)
                logger.debug(f"{step_label} {progress_data.formatted}")
            else:
                logger.info(f"{step_label} {progress_data.formatted}")
                logger.debug(f"{step_label} {progress_data.formatted}")
            return progress_data
        return None

    def ensure_completion(
        self, last_progress: float, step_label: str, progress=None, task_id=None
    ) -> None:
        """Ensure final 100% is displayed/updated"""
        if last_progress < 100.0:
            if progress and task_id is not None:
                progress.update(task_id, completed=100)
                progress.refresh()
            else:
                logger.info(f"{step_label} 100.0%")
                logger.debug(f"{step_label} 100.0%")


def create_ffmpeg_parser(duration: float) -> Callable[[str], ProgressData | None]:
    """Creates FFMPEG progress parser for given duration"""

    def parse_ffmpeg_progress(line: str) -> ProgressData | None:
        if "time=-" in line:
            return ProgressData(0.0, "0.0%")

        time_match = re.search(r"(\d\d):(\d\d):(\d\d)", line.strip())
        if time_match:
            total_ms = (
                int(time_match.group(1)) * 3600000
                + int(time_match.group(2)) * 60000
                + int(time_match.group(3)) * 1000
            )
            progress_ratio = float(total_ms) / float(duration)
            percent_value = min(100.0, progress_ratio * 100.0)
            percent_formatted = "{:.1%}".format(min(1.0, progress_ratio))
            return ProgressData(percent_value, percent_formatted)
        return None

    return parse_ffmpeg_progress


def create_dee_parser() -> Callable[[str], ProgressData | None]:
    """Creates DEE progress parser"""

    def parse_dee_progress(line: str) -> ProgressData | None:
        match = re.search(r"Stage progress: ([\d.]+)", line)
        if match:
            value = float(match.group(1))
            return ProgressData(value, f"{value}%")
        return None

    return parse_dee_progress


class DEEProgressHandler(ProgressHandler):
    """Specialized progress handler for DEE's two-phase encoding"""

    __slots__ = (
        "measure_task_desc",
        "encode_task_desc",
        "_measured_dialnorm",
        "_dialnorm_appended",
        "_custom_dialnorm",
    )

    def __init__(
        self,
        logger_level: int,
        no_progress_bars: bool,
        step_info: dict | None = None,
        custom_dialnorm: int = 0,
    ) -> None:
        super().__init__(logger_level, no_progress_bars, step_info)
        self._measured_dialnorm: str | None = None
        self._dialnorm_appended: bool = False

        # If user provided custom dialnorm (non-zero negative), format and store it
        self._custom_dialnorm: str | None = None
        try:
            if custom_dialnorm and custom_dialnorm != 0 and custom_dialnorm < 0:
                self._custom_dialnorm = f"({float(custom_dialnorm):.1f} dB)"
        except Exception:
            pass

        self.measure_task_desc = self.get_step_label(
            "DEE measure", default_current=2, default_total=3
        )

        # Only include worker prefix in encode task desc for rich progress bars
        # For plain text, the logger manager handles the prefix
        worker_prefix = (
            logger_manager.get_worker_prefix() if self.should_use_bars else None
        )

        if step_info:
            current = step_info.get("current", 2) + 1
            total = step_info.get("total", 3)
            base_desc = f"DEE encode ({current} of {total})"
        else:
            base_desc = "DEE encode (3 of 3)"

        if worker_prefix:
            self.encode_task_desc = f"{worker_prefix}: {base_desc}"
        else:
            self.encode_task_desc = base_desc

    def parse_dee_line(self, line: str) -> tuple[ProgressData | None, bool]:
        """Parse DEE line and return (progress_data, is_encode)"""
        # only detect measured dialnorm if user didn't provide a custom one
        if (
            not self._custom_dialnorm
            and not self._measured_dialnorm
            and "measured_loudness=" in line
        ):
            self._measured_dialnorm = line.split("measured_loudness=")[-1].rstrip(
                ".\n "
            )

        if "Stage progress" not in line:
            return None, False

        is_encode = False
        progress_data = None

        # check for step type first
        match = re.search(r"Step: (\w+),.*?Stage progress: ([\d.]+)", line)
        if match:
            step_type = match.group(1)
            value = float(match.group(2))
            if step_type == "encoding":
                is_encode = True
            progress_data = ProgressData(value, f"{value}%")
        else:
            # fallback to basic parsing
            match = re.search(r"Stage progress: ([\d.]+)", line)
            if match:
                value = float(match.group(1))
                progress_data = ProgressData(value, f"{value}%")

        return progress_data, is_encode

    def get_formatted_dialnorm(self) -> str | None:
        """Return a compact formatted dialnorm string like '(-24 dB)' if available."""
        if not self._measured_dialnorm:
            return None
        # accept formats with units or trailing text; extract numeric value
        m = re.search(r"([+-]?\d+(?:\.\d+)?)", self._measured_dialnorm)
        if not m:
            return None
        try:
            val = float(m.group(1))
        except Exception:
            return None
        # format with two decimal places
        return f"({val:.2f} dB)"

    def append_measured_dialnorm(self, progress=None, task_id=None) -> bool:
        """Append the measured dialnorm to the measure task's progress field or log it.

        Returns True if the dialnorm was appended, False otherwise. This method
        is idempotent and will only append once per handler instance.
        """
        if self._dialnorm_appended or self._custom_dialnorm:
            return False

        loud = self.get_formatted_dialnorm()
        if not loud:
            return False

        try:
            if progress and task_id is not None:
                try:
                    progress.update(task_id, dialnorm=loud)
                    progress.refresh()
                except Exception:
                    logger.info(f"{self.measure_task_desc} {loud}")
            else:
                logger.info(f"{self.measure_task_desc} {loud}")
        except Exception:
            logger.info(f"{self.measure_task_desc} {loud}")

        self._dialnorm_appended = True
        return True

    def attach_custom_dialnorm_to_encode(self, progress, encode_task_id) -> bool:
        """Attach custom dialnorm to the encode task field if it was provided.

        Returns True if attached, False otherwise.
        """
        if not self._custom_dialnorm or not progress or encode_task_id is None:
            return False

        try:
            progress.update(encode_task_id, dialnorm=self._custom_dialnorm)
            return True
        except Exception:
            return False

    @contextmanager
    def dee_progress_context(
        self,
    ) -> Generator[tuple[Progress, TaskID, None] | tuple[None, None, None], Any, None]:
        """Context manager for DEE's two-phase progress"""
        if self.should_use_bars:

            class DialnormColumn(ProgressColumn):
                """Render a trailing dialnorm value from task.fields safely."""

                def render(self, task) -> Text:
                    try:
                        val = task.fields.get("dialnorm")
                        return Text(str(val)) if val else Text("")
                    except Exception:
                        return Text("")

            with Progress(
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                TimeRemainingColumn(),
                SpinnerColumn(),
                DialnormColumn(),
                transient=False,
            ) as progress:
                measure_task_id = progress.add_task(self.measure_task_desc, total=100)
                yield progress, measure_task_id, None  # encode_task_id starts as None
        else:
            yield None, None, None
