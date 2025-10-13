import re
import sys
from pathlib import Path

from unidecode import unidecode


class PrintSameLine:
    """Class to correctly print on same line"""

    __slots__ = ("last_message",)

    def __init__(self) -> None:
        self.last_message = ""

    def print_msg(self, msg: str) -> None:
        """Print message in current line"""
        print(" " * len(self.last_message), end="\r", flush=True)
        print(msg, end="\r", flush=True)
        self.last_message = msg

    def clear(self) -> None:
        """Clear the current progress line"""
        print(" " * len(self.last_message), end="\r", flush=True)
        self.last_message = ""


def clean_string(s: str) -> str:
    """Clean strings to remove any special characters/non word characters and return it."""
    s = unidecode(s)
    return re.sub(r"[^A-Za-z0-9]", "", s)


def get_working_dir() -> tuple[Path, bool]:
    """
    Used to determine the correct working directory automatically.
    This way we can utilize files/relative paths easily.

    Returns:
        (tuple[Path, bool]): Current working directory, True if executable False if script.
    """
    # we're in a pyinstaller bundle
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys.executable).parent, True

    # we're running from a *.py file
    else:
        return Path.cwd(), False


WORKING_DIRECTORY, IS_BUNDLED = get_working_dir()
