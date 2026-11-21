from fractions import Fraction
import math
from pathlib import Path

import pytest

from deezy.dee.spec import get_format
from deezy.delay import (
    Delay,
    compensation,
    parse_delay,
    parse_fps,
    seconds_arg,
    to_samples,
)
from deezy.exceptions import InvalidDelayError
from deezy.track_info.utils import (
    clean_title,
    parse_delay_from_file,
    strip_delay_from_file_string_and_cleanse,
)


@pytest.mark.parametrize(
    ("text", "ms"),
    [
        ("10ms", 10),
        ("-10ms", -10),
        ("+10ms", 10),
        ("-10.5ms", Fraction(-21, 2)),
        ("10.25MS", Fraction(41, 4)),
        (".5ms", Fraction(1, 2)),
        ("2s", 2000),
        ("-1.25s", -1250),
        ("0ms", 0),
        (" 15ms ", 15),
    ],
)
def test_delays_are_read_exactly(text, ms):
    assert parse_delay(text) == Fraction(ms) / 1000


@pytest.mark.parametrize(
    "text",
    ["10", "ms", "abc", "10 ms", "1.2.3ms", "--5ms", "5msx", "-5m", "", "3@", "@24"],
)
def test_malformed_delays_are_refused(text):
    with pytest.raises(InvalidDelayError):
        parse_delay(text)


@pytest.mark.parametrize(
    ("text", "fps"),
    [
        ("24", Fraction(24)),
        ("25", Fraction(25)),
        ("23.976", Fraction(24000, 1001)),
        ("29.97", Fraction(30000, 1001)),
        ("59.94", Fraction(60000, 1001)),
        ("24000/1001", Fraction(24000, 1001)),
        ("NTSC", Fraction(30000, 1001)),
        ("pal", Fraction(25)),
        ("film", Fraction(24)),
        ("ntsc-film", Fraction(24000, 1001)),
        # not near an NTSC rate, so taken as written
        ("12.5", Fraction(25, 2)),
    ],
)
def test_frame_rates(text, fps):
    assert parse_fps(text) == fps


@pytest.mark.parametrize("text", ["0", "24/0", "0/1001", "abc", "-24", ""])
def test_bad_frame_rates_are_refused(text):
    with pytest.raises(InvalidDelayError, match="frame rate"):
        parse_fps(text)


@pytest.mark.parametrize(
    ("text", "samples"),
    [
        ("1@24", 2000),
        ("-3@24", -6000),
        ("1@23.976", 2002),
        ("1@24000/1001", 2002),
        ("2@pal", 3840),
        # 1601.6 samples
        ("1@ntsc", 1602),
    ],
)
def test_frame_delays_in_samples(text, samples):
    assert Delay.parse(text).requested == samples


@pytest.mark.parametrize(
    ("seconds", "samples"),
    [
        (Fraction(1, 96000), 1),
        (Fraction(-1, 96000), -1),
        (Fraction(1, 96001), 0),
        (Fraction(10010, 1000000), 480),
        (Fraction(0), 0),
    ],
)
def test_seconds_round_to_the_nearest_sample(seconds, samples):
    assert to_samples(seconds) == samples


def test_a_decimal_delay_reaches_dee_intact():
    # 10.5 ms is 504 samples, less the 256 samples DEE adds
    delay = Delay.parse("10.5ms").compensated(256)
    assert delay.offset == 248
    assert delay.dee_args() == ["--start", "0", "--add-silence", "0.005167:0"]


def test_a_negative_decimal_delay_trims_the_start():
    delay = Delay.parse("-1.5s").compensated(256)
    assert delay.dee_args() == ["--start", f"{(72000 + 256) / 48000:.6f}"]


SAMPLES = [1, 3, 9, 256, 288, 1710, 1744, 4544, 4800, 7172, 96256, 960222]


@pytest.mark.parametrize("samples", SAMPLES)
def test_start_seconds_round_to_the_sample(samples):
    # DEE rounds --start to the nearest sample
    assert round(Fraction(seconds_arg(samples)) * 48000) == samples


@pytest.mark.parametrize("samples", SAMPLES)
def test_silence_seconds_truncate_to_the_sample(samples):
    # and truncates --add-silence
    assert math.floor(Fraction(seconds_arg(samples, truncated=True)) * 48000) == samples


def test_a_delay_that_six_decimals_would_round_down():
    # 1@24 less 256 is 1744 samples, 0.0363333 s: 0.036333 would truncate to 1743
    delay = Delay.parse("1@24").compensated(256)
    assert delay.dee_args() == ["--start", "0", "--add-silence", "0.036334:0"]


def test_ms_and_is_delay():
    assert Delay.parse("-10.5ms").ms == -10.5
    assert Delay.parse("1@24").is_delay()
    assert not Delay.parse("0s").compensated(256).is_delay()


@pytest.mark.parametrize(
    ("name", "channel_change", "samples"),
    [
        ("dd", False, 256),
        ("dd", True, 288),
        ("ddp", True, 288),
        ("ddp-bluray", False, 256),
        ("ddp-atmos", False, 256),
        ("ac4-ims", False, 256),
    ],
)
def test_compensation_per_format(name, channel_change, samples):
    assert compensation(get_format(name), channel_change=channel_change) == samples


@pytest.mark.parametrize(
    ("mode", "bitrate", "channel_change", "samples"),
    [
        ("aaclc", 192, False, 1600),
        ("aaclc", 192, True, 1632),
        ("aaclc", 64, False, 1710),
        ("heaac", 64, True, 4312),
        ("heaacv2", 56, False, 7172),
    ],
)
def test_aac_compensation_follows_the_rate(mode, bitrate, channel_change, samples):
    spec = get_format("aac")
    assert (
        compensation(spec, channel_change=channel_change, mode=mode, bitrate=bitrate)
        == samples
    )


@pytest.mark.parametrize(
    ("name", "delay"),
    [
        ("Movie DELAY -10.5ms.ac3", "-10.5ms"),
        ("Movie delay 12ms.ec3", "12ms"),
        ("Movie DELAY 1.25s.thd", "1.25s"),
    ],
)
def test_delays_in_file_names_keep_their_decimals(name, delay):
    assert parse_delay_from_file(Path(name)) == delay
    stripped = strip_delay_from_file_string_and_cleanse(Path(name)).name
    assert "delay" not in stripped.lower()
    assert ".5ms" not in stripped


def test_clean_title_drops_decimal_delays():
    assert clean_title("01 - Main Title [eng] DELAY -12.5ms") == "01 Main Title"
