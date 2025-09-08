import argparse
from typing import Any


class CustomHelpFormatter(argparse.RawTextHelpFormatter):
    """Custom help formatter for argparse that modifies the format of action invocations.

    Inherits from argparse.RawTextHelpFormatter and overrides the _format_action_invocation method.
    This formatter adds a comma after each option string, and removes the default metavar from the
    args string of optional arguments that have no explicit metavar specified.

    Attributes:
        max_help_position (int): The maximum starting column for the help string.
        width (int): The width of the help string.

    Methods:
        _format_action_invocation(action): Overrides the method in RawTextHelpFormatter.
            Modifies the format of action invocations by adding a comma after each option string
            and removing the default metavar from the args string of optional arguments that have
            no explicit metavar specified. Returns the modified string."""

    def _format_action_invocation(self, action):
        if not action.option_strings or action.nargs == 0:
            return super()._format_action_invocation(action)

        default = self._get_default_metavar_for_optional(action)
        args_string = self._format_args(action, default)

        option_strings = ", ".join(action.option_strings)
        return f"{option_strings}, {args_string}"


def validate_track_index(value: Any) -> int:
    """
    Determines if the input is a valid number.
    If it's not returns the default of 0.

    Args:
        value (Any): Can be any input

    Returns:
        int: Corrected track index
    """

    # Check if the input is valid
    if value.isdigit():
        return int(value)
    # If the input is invalid, return the default value
    return 0


def int_0_100(value: str) -> int:
    """Validate it's in range from 0-100"""
    val = int(value)
    if val < 0 or val > 100:
        raise argparse.ArgumentTypeError("Value must be between 0 and 100")
    return val


def dialnorm_options(value: str) -> int:
    val = int(value)
    if val < -31 or val > 0:
        raise argparse.ArgumentTypeError(
            "Value must be between -31 and 0 (0 sets disables custom dialnorm)"
        )
    return val
