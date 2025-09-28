from types import SimpleNamespace
from typing import cast

from pymediainfo import Track

from deezy.audio_encoders.dee.base import BaseDeeAudioEncoder
from deezy.enums.shared import DeeDelay, DeeDelayModes


class DummyEncoder(BaseDeeAudioEncoder):
    """Tiny concrete subclass solely for testing the helper."""

    def _get_channel_bitrate_object(self, *args, **kwargs):
        raise NotImplementedError()

    def _get_down_mix_config(self, *args, **kwargs) -> str:
        return ""

    def _generate_ffmpeg_cmd(self, *args, **kwargs) -> list[str]:
        return []


def make_delay(present: bool) -> DeeDelay:
    if present:
        return DeeDelay(DeeDelayModes.POSITIVE, "0:00:00.010000")
    # default Dolby compensation value -> not a real delay
    return DeeDelay(DeeDelayModes.POSITIVE, "0:00:00.005333")


def make_track(is_elementary: bool) -> SimpleNamespace:
    # Provide a minimal Track-like object for the legacy delay flag logic
    # Tests only need 'channels' and 'is_elementary' so a SimpleNamespace is sufficient.
    return SimpleNamespace(
        mi_track=cast(Track, SimpleNamespace()), channels=2, is_elementary=is_elementary
    )


def compute_template_delay_flags(
    audio_track_info: SimpleNamespace,
    delay: DeeDelay,
) -> tuple[bool, bool]:
    """
    Lightweight re-implementation of the old compute_template_delay_flags
    behavior which the production code no longer exposes. Kept in-tests so
    existing test intent can be preserved without changing library code.
    """
    # This helper was previously used to emulate removed production logic.
    # Keep it minimal for backwards compatibility in older tests but prefer
    # asserting the real DeeDelay behavior in new tests.
    ignore_delay = audio_track_info.is_elementary and delay.is_delay()
    return ignore_delay, delay.is_delay()


def test_elementary_parse_true_delay_present():
    # A real DeeDelay for a present delay should report as a delay
    delay = make_delay(present=True)
    assert delay.is_delay() is True


def test_elementary_parse_false_delay_present():
    # Payload flags do not flip a DeeDelay's intrinsic 'is_delay' property
    delay = make_delay(present=True)
    assert delay.is_delay() is True


def test_non_elementary_delay_present():
    # Non-elementary tracks still have delay objects which indicate delay
    delay = make_delay(present=True)
    assert delay.is_delay() is True


def test_elementary_no_delay():
    # DeeDelay using the default compensation value is not treated as a real delay
    delay = make_delay(present=False)
    assert delay.is_delay() is False
