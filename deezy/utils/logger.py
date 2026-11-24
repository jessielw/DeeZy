from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
import logging
from pathlib import Path
import sys
import uuid


class _LiveStderrHandler(logging.StreamHandler):
    """Console handler that always writes to the *current* sys.stderr.

    rich swaps sys.stderr while a live progress display runs; resolving it on
    every emit lets log lines print above the bars instead of tearing them.
    """

    @property
    def stream(self):
        return sys.stderr

    @stream.setter
    def stream(self, _value) -> None:
        pass


class _JobLogHandler(logging.Handler):
    """Route log records to the file for the current job."""

    def __init__(self) -> None:
        super().__init__()
        self.target: ContextVar[logging.FileHandler | None] = ContextVar(
            "job_log", default=None
        )

    def emit(self, record: logging.LogRecord) -> None:
        if (handler := self.target.get()) is not None:
            handler.handle(record)


class LoggerManager:
    """
    Manages the Deezy logger, allowing dynamic changes to log level and file output.
    Supports worker prefixes for parallel processing.
    """

    def __init__(self, name: str = "deezy") -> None:
        self.logger = logging.getLogger(name)
        self.logger.propagate = False
        self._console_handler: logging.Handler | None = None
        self._worker_prefix: ContextVar[str | None] = ContextVar(
            "worker_prefix", default=None
        )
        self._ensure_console_handler()
        self._job_log = _JobLogHandler()
        self.logger.addHandler(self._job_log)

    def _ensure_console_handler(self) -> None:
        if not any(isinstance(h, logging.StreamHandler) for h in self.logger.handlers):
            console_handler = _LiveStderrHandler()
            console_handler.setFormatter(WorkerFormatter())
            self.logger.addHandler(console_handler)
            self._console_handler = console_handler

    def set_level(self, level: int | str) -> None:
        self.logger.setLevel(level)
        for handler in self.logger.handlers:
            handler.setLevel(level)

    @contextmanager
    def file_log(self, path: Path | None) -> Iterator[Path | None]:
        """Attach a file to the current job for the duration of the job."""
        if path is None:
            yield None
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                handler = logging.FileHandler(path, mode="x", encoding="utf-8")
            except FileExistsError:
                path = path.with_name(
                    f"{path.stem}.{uuid.uuid4().hex[:12]}{path.suffix}"
                )
                handler = logging.FileHandler(path, mode="x", encoding="utf-8")
        except OSError as e:
            self.logger.warning(f"Could not open the job log at {path}: {e}")
            yield None
            return

        handler.setFormatter(WorkerFormatter())
        token = self._job_log.target.set(handler)
        try:
            yield path
        except Exception as e:
            # The CLI reports the error after the worker has closed its log.
            handler.handle(
                self.logger.makeRecord(
                    self.logger.name,
                    logging.ERROR,
                    __file__,
                    0,
                    "Job ended: %s",
                    (e,),
                    None,
                )
            )
            raise
        finally:
            self._job_log.target.reset(token)
            handler.close()

    def set_worker_prefix(self, prefix: str | None) -> None:
        """Set worker prefix for current thread."""
        self._worker_prefix.set(prefix)

    def get_worker_prefix(self) -> str | None:
        """Get worker prefix for current thread."""
        return self._worker_prefix.get()

    def get_logger(self):
        return self.logger


class WorkerFormatter(logging.Formatter):
    """Custom formatter that adds worker prefixes."""

    def format(self, record):
        prefix = logger_manager.get_worker_prefix()
        message = record.getMessage()
        if prefix:
            return f"{prefix}: {message}"
        return message


# singleton instance for use throughout the codebase
logger_manager = LoggerManager()
logger = logger_manager.get_logger()
