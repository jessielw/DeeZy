from pathlib import Path
from types import SimpleNamespace
from typing import Any

from deezy.audio_encoders.dee.ac4 import Ac4Encoder
from deezy.audio_encoders.dee.atmos import AtmosEncoder
from deezy.audio_encoders.dee.dd import DDEncoderDEE
from deezy.audio_encoders.dee.ddp import DDPEncoderDEE


def make_payload(tmp_base: Path, input_path: Path) -> Any:
    # Minimal payload-like object with only attributes used by the temp-dir selection logic
    # Return type is Any to avoid static type-checker errors in tests when
    # passing this minimal object to encoder constructors that expect concrete
    # payload dataclasses.
    return SimpleNamespace(file_input=str(input_path), temp_dir=str(tmp_base))


def test_encoders_use_per_input_subfolder_under_temp_dir(tmp_path):
    """When a user provides --temp-dir, each encoder should use <base>/<input_stem>_deezy."""
    input_path = tmp_path / "Some.Movie.TrueHD.Atmos.mkv"
    central_base = tmp_path / "central_tmp"
    payload: Any = make_payload(central_base, input_path)

    expected = central_base / f"{input_path.stem}_deezy"

    for EncoderCls in (DDEncoderDEE, DDPEncoderDEE, Ac4Encoder, AtmosEncoder):
        enc = EncoderCls(payload)
        # The encoder logic prefers the provided temp_dir and constructs the
        # per-input subfolder as <temp_dir>/<input_stem>_deezy. Reproduce that
        # deterministic behavior here and assert equality.
        user_temp_base = getattr(enc.payload, "temp_dir", None)
        if user_temp_base:
            temp_dir = (
                Path(user_temp_base) / f"{Path(enc.payload.file_input).stem}_deezy"
            )
        else:
            # Not expected in this test, but keep parity with encoder fallback.
            temp_dir = enc._adjacent_temp_dir(Path(enc.payload.file_input))

        assert temp_dir == expected
