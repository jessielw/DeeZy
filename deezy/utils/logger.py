import logging
from pathlib import Path


class LoggerManager:
    """
    Manages the Deezy logger, allowing dynamic changes to log level and file output.
    """

    def __init__(self, name: str = "deezy") -> None:
        self.logger = logging.getLogger(name)
        self.logger.propagate = False
        self._file_handler: logging.FileHandler | None = None
        self._console_handler: logging.Handler | None = None
        self._ensure_console_handler()

    def _ensure_console_handler(self) -> None:
        if not any(isinstance(h, logging.StreamHandler) for h in self.logger.handlers):
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(logging.Formatter("%(message)s"))
            self.logger.addHandler(console_handler)
            self._console_handler = console_handler

    def set_level(self, level: int | str) -> None:
        self.logger.setLevel(level)
        for handler in self.logger.handlers:
            handler.setLevel(level)

    def set_file(self, write_path: Path | None) -> None:
        # remove existing file handler if present
        if self._file_handler:
            self.logger.removeHandler(self._file_handler)
            self._file_handler.close()
            self._file_handler = None
        # add new file handler if path is given
        if write_path:
            file_handler = logging.FileHandler(write_path, mode="w", encoding="utf-8")
            file_handler.setFormatter(logging.Formatter("%(message)s"))
            file_handler.setLevel(self.logger.level)
            self.logger.addHandler(file_handler)
            self._file_handler = file_handler

    def get_logger(self):
        return self.logger


# singleton instance for use throughout the codebase
logger_manager = LoggerManager()
logger = logger_manager.get_logger()
