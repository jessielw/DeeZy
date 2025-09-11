import sys

from cli import cli_parser
from deezy.utils.utils import get_working_dir


if __name__ == "__main__":
    # force line buffering for wrapper-friendly output
    # this ensures real-time progress when DeeZy is called by other tools
    sys.stdout = open(sys.stdout.fileno(), "w", 1, encoding="utf-8")
    sys.stderr = open(sys.stderr.fileno(), "w", 1, encoding="utf-8")

    base_wd = get_working_dir()
    cli_parser(base_wd)
