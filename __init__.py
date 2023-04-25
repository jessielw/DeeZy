from audio_encoder import _main
from audio_encoder.utils.utils import _get_working_dir

if __name__ == "__main__":
    base_wd = _get_working_dir()
    _main(base_wd)
