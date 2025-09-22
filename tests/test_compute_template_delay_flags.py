from types import SimpleNamespace
from typing import cast

from pymediainfo import Track

from deezy.audio_encoders.dee.base import BaseDeeAudioEncoder
from deezy.enums.shared import DeeDelay, DeeDelayModes
from deezy.track_info.audio_track_info import AudioTrackInfo


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


def make_track(is_elementary: bool) -> AudioTrackInfo:
    # Provide a minimal Track-like object so static type checks are happy
    fake_track = cast(Track, SimpleNamespace())
    return AudioTrackInfo(mi_track=fake_track, channels=2, is_elementary=is_elementary)


def test_elementary_parse_true_delay_present():
    enc = DummyEncoder()
    track = make_track(is_elementary=True)
    delay = make_delay(present=True)
    ignore_delay, delay_was_stripped = enc.compute_template_delay_flags(
        track, delay, payload_parse_elementary_delay=True
    )
    # user requested parse -> we should NOT ignore delay; stripped flag follows delay.is_delay()
    assert ignore_delay is False
    assert delay_was_stripped is True


def test_elementary_parse_false_delay_present():
    enc = DummyEncoder()
    track = make_track(is_elementary=True)
    delay = make_delay(present=True)
    ignore_delay, delay_was_stripped = enc.compute_template_delay_flags(
        track, delay, payload_parse_elementary_delay=False
    )
    # user did not request parse and track is elementary and delay exists -> ignore_delay True
    assert ignore_delay is True
    assert delay_was_stripped is True


def test_non_elementary_delay_present():
    enc = DummyEncoder()
    track = make_track(is_elementary=False)
    delay = make_delay(present=True)
    ignore_delay, delay_was_stripped = enc.compute_template_delay_flags(
        track, delay, payload_parse_elementary_delay=False
    )
    # non-elementary track means we should not ignore delay
    assert ignore_delay is False
    assert delay_was_stripped is True


def test_elementary_no_delay():
    enc = DummyEncoder()
    track = make_track(is_elementary=True)
    delay = make_delay(present=False)
    ignore_delay, delay_was_stripped = enc.compute_template_delay_flags(
        track, delay, payload_parse_elementary_delay=False
    )
    # no delay detected -> ignore_delay False, stripped False
    assert ignore_delay is False
    assert delay_was_stripped is False
