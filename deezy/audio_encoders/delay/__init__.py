import re
from datetime import timedelta

from deezy.enums.shared import DeeDelay, DeeDelayModes
from deezy.exceptions import InvalidDelayError


def get_dee_delay(delay: str, compensate: bool = True) -> DeeDelay:
    """
    Converts the delay string to the proper format, checks for invalid characters,
    and returns a tuple containing the Dee Delay mode and the delay in the
    appropriate format for Dee Delay.

    Parameters:
        delay (str): The delay string to be converted.
        compensate (bool): Rather or not we want to compensate for DEE's added audio delay,
        this compensates for dee's 256 added samples

    Returns:
        DeeDelay dataclass with needed values for processing (JSON).

    Raises:
        InvalidDelayError: If the delay input contains invalid characters or is
        not in the correct format.

    Example:
        ```
        dee = DeeDelay()
        dee.get_dee_delay('-2s')
        ```
    """
    # check for invalid characters in string
    check_for_invalid_characters(delay)

    # convert delay to proper format
    get_delay = convert_delay_ms(delay)

    # get only numbers from delay
    s_delay = re.search(r"-?\d+\.?\d*", get_delay)

    # if numbers was detected
    if s_delay:
        # convert numbers to a float
        s_delay = float(s_delay.group())

        # subtract the Dolby silence offset
        if compensate:
            s_delay -= 16 / 3

        # if delay is negative
        if s_delay < 0:
            dee_delay_mode = DeeDelayModes.NEGATIVE
            delay_json = str(timedelta(seconds=(abs(s_delay) / 1000)))
            if "." not in delay_json:
                delay_json = f"{delay_json}.0"

        # if delay is positive
        else:
            dee_delay_mode = DeeDelayModes.POSITIVE
            delay_json = format(s_delay / 1000, ".6f")

        # create an internal data class
        data_class = DeeDelay(dee_delay_mode, delay_json)

        return data_class

    # if no numbers were detected raise an error
    else:
        raise InvalidDelayError(
            "Delay input must be in the format of -10ms/10ms or -10s/10s"
        )


def convert_delay_ms(delay: str) -> str:
    """
    Converts the delay string to milliseconds.

    Args:
        delay (str): A delay string in the format of -10ms/10ms or -10s/10s.

    Returns:
        str: The delay string in milliseconds.
    """
    # lower delay string
    lowered_input = delay.lower()

    # set negative string
    negative = ""
    if "-" in lowered_input:
        negative = "-"

    # check if input is in milliseconds
    if "ms" in lowered_input:
        ms_delay = re.search(r"\d+", lowered_input)
        if ms_delay:
            ms_delay = float(ms_delay.group())
        else:
            raise InvalidDelayError(
                "Delay input must be in the format of -10ms/10ms or -10s/10s"
            )
        return f"{negative}{ms_delay}ms"

    # check if input is in seconds
    elif "s" in lowered_input:
        s_delay = re.search(r"\d+\.?\d*", lowered_input)
        if s_delay:
            s_delay = float(s_delay.group())
        else:
            raise InvalidDelayError(
                "Delay input must be in the format of -10ms/10ms or -10s/10s"
            )
        seconds_to_milliseconds = s_delay * 1000
        return f"{negative}{seconds_to_milliseconds}ms"

    raise ValueError(f"{delay} is an invalid delay input")


def check_for_invalid_characters(delay: str) -> None:
    """
    Check if a delay string contains any invalid characters.

    The delay string must be in the format of '-10ms/10ms' or '-10s/10s', where
    the leading '-' is optional, the number is an integer or a decimal with up
    to three digits, and the unit is 'ms' for milliseconds or 's' for seconds.

    If the delay string contains any characters other than digits, '-', 'm',
    's', or whitespace, an InvalidDelayError is raised with a message that
    includes the invalid characters.

    Parameters:
        delay (str): The delay string to check.

    Raises:
        InvalidDelayError: If the delay string contains any invalid characters.
    """
    invalid_chars = re.findall(r"[^\-\sms\d]", delay.lower())
    if invalid_chars:
        raise InvalidDelayError(
            f"Invalid characters detected: {', '.join(invalid_chars)}\n"
            "Delay input must be in the format of -10ms/10ms or -10s/10s"
        )
    if re.search(r"\s", delay):
        raise InvalidDelayError("Delay input cannot contain whitespace characters.")
