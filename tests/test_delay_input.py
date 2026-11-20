from pathlib import Path

import pytest

from deezy.audio_encoders.delay import get_dee_delay, parse_delay_ms
from deezy.exceptions import InvalidDelayError
from deezy.track_info.utils import (
    clean_title,
    parse_delay_from_file,
    strip_delay_from_file_string_and_cleanse,
)


@pytest.mark.parametrize(
    ("text", "ms"),
    [
        ("10ms", 10.0),
        ("-10ms", -10.0),
        ("+10ms", 10.0),
        ("-10.5ms", -10.5),
        ("10.25MS", 10.25),
        (".5ms", 0.5),
        ("2s", 2000.0),
        ("-1.25s", -1250.0),
        ("0ms", 0.0),
        (" 15ms ", 15.0),
    ],
)
def test_delays_are_read_with_their_decimals(text, ms):
    assert parse_delay_ms(text) == pytest.approx(ms)


@pytest.mark.parametrize(
    "text", ["10", "ms", "abc", "10 ms", "1.2.3ms", "--5ms", "5msx", "-5m", ""]
)
def test_malformed_delays_are_refused(text):
    with pytest.raises(InvalidDelayError):
        parse_delay_ms(text)


def test_a_decimal_delay_reaches_dee_intact():
    # 10.5 ms less the 256 samples DEE adds
    assert get_dee_delay("10.5ms").offset_seconds() == pytest.approx(
        0.0105 - 256 / 48000
    )


def test_a_negative_decimal_delay_trims_the_start():
    assert get_dee_delay("-1.5s").offset_seconds() == pytest.approx(-1.5 - 256 / 48000)


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
