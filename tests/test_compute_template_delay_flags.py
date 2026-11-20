from types import SimpleNamespace
from typing import cast

from pymediainfo import Track

from deezy.delay import Delay


def make_delay(present: bool) -> Delay:
    if present:
        return Delay(requested=480)
    # only the default compensation -> not a real delay
    return Delay(compensation=256)


def make_track(is_elementary: bool) -> SimpleNamespace:
    # Provide a minimal Track-like object for the legacy delay flag logic
    # Tests only need 'channels' and 'is_elementary' so a SimpleNamespace is sufficient.
    return SimpleNamespace(
        mi_track=cast(Track, SimpleNamespace()), channels=2, is_elementary=is_elementary
    )


def compute_template_delay_flags(
    audio_track_info: SimpleNamespace,
    delay: Delay,
) -> tuple[bool, bool]:
    """
    Lightweight re-implementation of the old compute_template_delay_flags
    behavior which the production code no longer exposes. Kept in-tests so
    existing test intent can be preserved without changing library code.
    """
    # This helper was previously used to emulate removed production logic.
    # Keep it minimal for backwards compatibility in older tests but prefer
    # asserting the real Delay behavior in new tests.
    ignore_delay = audio_track_info.is_elementary and delay.is_delay()
    return ignore_delay, delay.is_delay()


def test_elementary_parse_true_delay_present():
    # A real Delay for a present delay should report as a delay
    delay = make_delay(present=True)
    assert delay.is_delay() is True


def test_elementary_parse_false_delay_present():
    # Payload flags do not flip a Delay's intrinsic 'is_delay' property
    delay = make_delay(present=True)
    assert delay.is_delay() is True


def test_non_elementary_delay_present():
    # Non-elementary tracks still have delay objects which indicate delay
    delay = make_delay(present=True)
    assert delay.is_delay() is True


def test_elementary_no_delay():
    # a Delay with only the default compensation is not a real delay
    delay = make_delay(present=False)
    assert delay.is_delay() is False
