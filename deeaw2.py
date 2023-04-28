from cli import cli_parser
from audio_encoder.utils.utils import _get_working_dir


if __name__ == "__main__":
    base_wd = _get_working_dir()
    cli_parser(base_wd)
