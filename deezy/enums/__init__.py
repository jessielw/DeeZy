from argparse import ArgumentTypeError
from enum import Enum
from typing import Type


def _missing_func(cls, value):
    """Helper function to check member/value for a match."""
    if value is None:
        return

    value_str = str(value).lower() if isinstance(value, str) else value

    for member in cls:
        member_name = member.name.lower()
        member_value = member.value

        # compare member name (case-insensitive)
        if isinstance(value, str):
            if member_name == value_str or member_name.replace("_", " ") == value_str:
                return member

        # compare member value
        if isinstance(member_value, str) and isinstance(value, str):
            member_value_lower = member_value.lower()
            if (
                member_value_lower == value_str
                or member_value_lower.replace("_", " ") == value_str
            ):
                return member
        elif member_value == value:
            return member


class CaseInsensitiveEnum(Enum):
    """Case insensitive Enum that will attempt to match on both the value and member."""

    @classmethod
    def _missing_(cls, value):
        """Override this method to ignore case sensitivity"""
        missing = _missing_func(cls, value)
        if missing:
            return missing
        raise ValueError(f"No {cls.__name__} member with value '{value}'")


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
        v = value.strip() # TODO: be sure to check this when we remove the weird atmos input channel names
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
    """
    return f"{{{','.join(str(e.value) for e in enum_class)}}}"
