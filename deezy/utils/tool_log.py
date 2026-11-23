"""What a job's tools print, kept beside the output on request (--keep-logs)."""

from pathlib import Path
import threading

from deezy.utils.paths import long_path_str

LOG_SUFFIX = ".log"


def log_path(output: Path) -> Path:
    """Where a job's kept log goes: beside its output, named after it."""
    return output.with_name(f"{output.name}{LOG_SUFFIX}")


class ToolLog:
    """
    The command lines a job runs and every line its tools print, each tagged
    with its tool, in the order they were printed. Progress ticks are left
    out. Safe across threads: a pipe job's FFmpeg, and truehdd's output, are
    read on threads of their own.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._lines: list[str] = []

    def command(self, line: str) -> None:
        """A command line, as it starts."""
        with self._lock:
            self._lines.append(f"$ {line}")

    def add(self, tool: str, line: str) -> None:
        """A line ``tool`` printed."""
        if line:
            with self._lock:
                self._lines.append(f"[{tool}] {line}")

    @property
    def lines(self) -> list[str]:
        with self._lock:
            return list(self._lines)

    def write(self, path: Path) -> None:
        """Write the log to ``path``, replacing what is there."""
        text = "\n".join(self.lines) + "\n"
        Path(long_path_str(path)).write_text(text, encoding="utf-8")
