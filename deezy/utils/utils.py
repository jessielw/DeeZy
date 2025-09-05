from pathlib import Path
import sys


class PrintSameLine:
    """Class to correctly print on same line"""

    __slots__ = ("last_message",)

    def __init__(self) -> None:
        self.last_message = ""

    def print_msg(self, msg: str) -> None:
        print(" " * len(self.last_message), end="\r", flush=True)
        print(msg, end="\r", flush=True)
        self.last_message = msg


def get_working_dir() -> Path:
    """
    Used to determine the correct working directory automatically.
    This way we can utilize files/relative paths easily.

    Returns:
        (Path): Current working directory
    """
    # we're in a pyinstaller bundle
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys.executable).parent

    # we're running from a *.py file
    else:
        return Path.cwd()
