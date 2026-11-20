import re

from deezy.enums.shared import DEE_DELAY_SAMPLES, DeeDelay
from deezy.exceptions import InvalidDelayError

# a signed number of milliseconds or seconds, e.g. -10ms, 10.5ms, +1.25s
_DELAY_INPUT = re.compile(r"([+-]?)(\d+(?:\.\d*)?|\.\d+)(ms|s)", re.IGNORECASE)
_DELAY_FORMAT = (
    "Delay input must be in the format of -10ms/10ms or -10s/10s "
    "(decimals are allowed, e.g. -10.5ms or 1.25s)"
)


def parse_delay_ms(delay: str) -> float:
    """A delay string such as ``-10.5ms`` or ``1.25s`` as milliseconds."""
    match = _DELAY_INPUT.fullmatch(delay.strip())
    if not match:
        raise InvalidDelayError(f"Invalid delay '{delay}'. {_DELAY_FORMAT}")
    sign, number, unit = match.groups()
    ms = float(number) * (1 if unit.lower() == "ms" else 1000)
    return -ms if sign == "-" else ms


def get_dee_delay(
    delay: str, compensation_samples: int = DEE_DELAY_SAMPLES
) -> DeeDelay:
    """
    The delay to hand DEE for a delay string such as ``-10ms`` or ``1.25s``.

    Parameters:
        delay (str): The delay string to be converted.
        compensation_samples (int): The delay DEE adds to the encode, in
            samples at 48 kHz, which the encode takes off.

    Raises:
        InvalidDelayError: If the delay is not a signed number of ms or s.
    """
    return DeeDelay(parse_delay_ms(delay), compensation_samples)
