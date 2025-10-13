from pathlib import Path

from deezy.audio_encoders.dee.base import BaseDeeAudioEncoder
from deezy.payloads.shared import ChannelBitrates
from tests.utils.payload_helpers import generate_dummy_core_payload


class DummyEncoder(BaseDeeAudioEncoder):
    # implement abstract methods minimally for testing
    @staticmethod
    def _get_channel_bitrate_object(desired_channels, source_channels):
        return ChannelBitrates(default=64000, choices=(64000,))

    @staticmethod
    def _get_down_mix_config(*args, **kwargs) -> str:
        return "off"

    def _generate_ffmpeg_cmd(self, *args, **kwargs) -> list[str]:
        return []


def test_per_track_dir_stable(tmp_path: Path):
    enc = DummyEncoder(generate_dummy_core_payload())
    file_input = tmp_path / "movie.mkv"
    file_input.write_text("x")
    base = tmp_path / "base"

    d1 = enc._get_temp_dir(file_input, base, track_label="t0", keep_temp=True)
    d2 = enc._get_temp_dir(file_input, base, track_label="t0", keep_temp=True)

    assert d1.exists()
    assert d1 == d2


def test_per_run_dir_unique(tmp_path: Path):
    enc = DummyEncoder(generate_dummy_core_payload())
    file_input = tmp_path / "movie.mkv"
    file_input.write_text("x")
    base = tmp_path / "base"

    d1 = enc._get_temp_dir(file_input, base, track_label="t0", keep_temp=False)
    d2 = enc._get_temp_dir(file_input, base, track_label="t0", keep_temp=False)

    assert d1.exists() and d2.exists()
    assert d1 != d2


def test_cleanup_respects_keep_flag(tmp_path: Path):
    enc = DummyEncoder(generate_dummy_core_payload())
    file_input = tmp_path / "movie.mkv"
    file_input.write_text("x")
    base = tmp_path / "base"

    # per-run dir should be removed
    d = enc._get_temp_dir(file_input, base, track_label="t0", keep_temp=False)
    assert d.exists()
    enc._clean_temp(d, keep_temp=False)
    assert not d.exists()

    # per-track dir should remain
    d2 = enc._get_temp_dir(file_input, base, track_label="t0", keep_temp=True)
    assert d2.exists()
    enc._clean_temp(d2, keep_temp=True)
    assert d2.exists()
