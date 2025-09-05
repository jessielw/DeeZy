from cli import cli_parser
from deezy.utils.utils import get_working_dir


if __name__ == "__main__":
    base_wd = get_working_dir()
    cli_parser(base_wd)
