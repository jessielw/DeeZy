"""
Delays, in samples at 48 kHz from the parsed input to DEE's command line.

A delay comes from ``--delay`` or the file name (``DELAY -10.5ms``) and is given
in milliseconds, seconds or frames: ``-10.5ms``, ``1.25s``, ``-3@23.976``. DEE
starts each encode some samples late, and later still when it changes the
channel count. The encode takes that off, so the output carries exactly the
delay asked for.
"""

from dataclasses import dataclass, replace
from fractions import Fraction
import math
import re

from deezy.dee.spec import SAMPLE_RATE, FormatSpec
from deezy.exceptions import InvalidDelayError

_NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)"
_TIME = re.compile(rf"({_NUMBER})(ms|s)", re.IGNORECASE)
_FRAMES = re.compile(rf"({_NUMBER})@(.+)")
_RATIO = re.compile(r"(\d+)/(\d+)")
_DECIMAL = re.compile(r"\d+(?:\.\d*)?|\.\d+")

# ffmpeg's names for these frame rates
FPS_NAMES = {
    "ntsc": Fraction(30000, 1001),
    "pal": Fraction(25),
    "film": Fraction(24),
    "ntsc-film": Fraction(24000, 1001),
}

DELAY_FORMAT = (
    "A delay is milliseconds, seconds or frames at a frame rate: -10.5ms, 1.25s, "
    "or -3@23.976 (the rate may also be 24000/1001, ntsc, pal, film or ntsc-film)."
)


def parse_fps(text: str) -> Fraction:
    """
    A frame rate such as ``24``, ``23.976``, ``24000/1001`` or ``pal``.

    A decimal that rounds an NTSC rate (23.976, 29.97, 59.94, ...) means the
    exact rate, N * 1000/1001.
    """
    text = text.strip().lower()
    if text in FPS_NAMES:
        return FPS_NAMES[text]
    ratio = _RATIO.fullmatch(text)
    if ratio and int(ratio.group(2)):
        fps = Fraction(int(ratio.group(1)), int(ratio.group(2)))
    elif _DECIMAL.fullmatch(text):
        fps = Fraction(text)
        if fps.denominator != 1:
            ntsc = Fraction(round(fps * Fraction(1001, 1000)) * 1000, 1001)
            if abs(ntsc - fps) < Fraction(1, 200):
                fps = ntsc
    else:
        fps = Fraction(0)
    if fps <= 0:
        raise InvalidDelayError(f"Invalid frame rate '{text}'. {DELAY_FORMAT}")
    return fps


def parse_delay(text: str) -> Fraction:
    """A delay string as exact seconds."""
    text = text.strip()
    time = _TIME.fullmatch(text)
    if time:
        seconds = Fraction(time.group(1))
        return seconds / 1000 if time.group(2).lower() == "ms" else seconds
    frames = _FRAMES.fullmatch(text)
    if frames:
        return Fraction(frames.group(1)) / parse_fps(frames.group(2))
    raise InvalidDelayError(f"Invalid delay '{text}'. {DELAY_FORMAT}")


def to_samples(seconds: Fraction) -> int:
    """Seconds as the nearest whole sample at 48 kHz, halves away from zero."""
    samples = math.floor(abs(seconds) * SAMPLE_RATE + Fraction(1, 2))
    return -samples if seconds < 0 else samples


def seconds_arg(samples: int, *, truncated: bool = False) -> str:
    """
    Samples as the seconds DEE takes on its command line, to the microsecond.

    DEE rounds ``--start`` to the nearest sample, so the nearest microsecond
    (within 0.03 samples) lands on it. It truncates ``--add-silence``, which
    takes ``truncated``: the microsecond at or above the exact value (under 0.05
    samples above) truncates to it.
    """
    us = Fraction(samples * 1_000_000, SAMPLE_RATE)
    us = math.ceil(us) if truncated else math.floor(us + Fraction(1, 2))
    return f"{us // 1_000_000}.{us % 1_000_000:06d}"


def compensation(spec: FormatSpec, *, channel_change: bool = False) -> int:
    """
    The samples DEE adds to an encode, which the encode takes off.

    ``channel_change`` is for an encode where DEE itself changes the channel
    count, which adds the spec's channel-change samples.
    """
    return spec.delay_samples + (spec.channel_change_samples if channel_change else 0)


@dataclass(frozen=True, slots=True)
class Delay:
    """A requested delay and the delay DEE adds, both in samples at 48 kHz."""

    requested: int = 0
    compensation: int = 0

    @classmethod
    def parse(cls, text: str) -> "Delay":
        return cls(to_samples(parse_delay(text)))

    def is_delay(self) -> bool:
        """
        True when a delay was asked for. The encode then carries it, so the
        output's container delay is 0.
        """
        return self.requested != 0

    @property
    def ms(self) -> float:
        return self.requested * 1000 / SAMPLE_RATE

    @property
    def offset(self) -> int:
        """How far to shift the audio: > 0 prepends silence, < 0 trims the start."""
        return self.requested - self.compensation

    def compensated(self, samples: int) -> "Delay":
        """This delay for an encode where DEE adds ``samples``."""
        return replace(self, compensation=samples)

    def dee_args(self) -> list[str]:
        """
        Where DEE starts reading, and the silence it prepends.

        ``--start`` is always given: left out, DEE starts at the master's first
        frame of action instead of the first sample.
        """
        if self.offset < 0:
            return ["--start", seconds_arg(-self.offset)]
        args = ["--start", "0"]
        if self.offset > 0:
            # prepend silence, nothing appended
            args += ["--add-silence", f"{seconds_arg(self.offset, truncated=True)}:0"]
        return args
