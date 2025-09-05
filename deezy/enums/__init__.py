from argparse import ArgumentTypeError
from enum import Enum
from typing import Type


def case_insensitive_enum(enum_class):
    """Return a converter that takes a string and returns the corresponding
    enumeration value, regardless of case.

    Args:
        enum_class (Enum): The enumeration class to convert values to.

    Returns:
        A converter function that takes a string and returns the corresponding
        enumeration value.

    Raises:
        ArgumentTypeError: If the input string is not a valid choice
        for the given enumeration class.
    """

    def converter(value):
        v = value.strip()
        try:
            # numeric form e.g. "514"
            if v.isdigit():
                return enum_class(int(v))

            # direct name lookup (case-insensitive) e.g. "ATMOS_5_1_4"
            members = enum_class.__members__
            key = v.upper()
            if key in members:
                return enum_class[key]

            # allow enum classes to implement a from_string parser (e.g. "5.1.4")
            from_str = getattr(enum_class, "from_string", None)
            if callable(from_str):
                parsed = from_str(v)
                if isinstance(parsed, enum_class):
                    return parsed
                if isinstance(parsed, int):
                    return enum_class(parsed)
                if isinstance(parsed, str) and parsed.upper() in members:
                    return enum_class[parsed.upper()]

            raise ArgumentTypeError(f"Invalid choice: {value}")
        except (KeyError, ValueError, TypeError):
            raise ArgumentTypeError(f"Invalid choice: {value}")

    return converter


def enum_choices(enum_class: Type[Enum]) -> str:
    """
    Returns a string representation of all possible choices in the given enumeration class.

    Args:
        enum_class (Enum): The enumeration class to retrieve choices from.

    Returns:
        A string with the format "{choice1[choice_value1]},{choice2[choice_value2]},...".

    Example:
        If the enumeration class is defined as follows:

        class DolbyDigitalChannels(Enum):
            MONO = 1
            STEREO = 2
            SURROUND = 6

        The function will return the following string:

        "{MONO[1]},{STEREO[2]},{SURROUND[6]}"
    """
    return f"{{{','.join(e.name + '[' + str(e.value) + ']' for e in enum_class)}}}"
