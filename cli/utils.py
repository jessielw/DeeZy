import argparse
import os
from pathlib import Path
import shutil
import tempfile
import time
from typing import Any

from deezy.track_info.track_index import TrackIndex


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


def validate_track_index(value: Any) -> TrackIndex:
    """
    Parse and validate track index input.

    Supports FFmpeg-style notation:
    - a:N (audio track N)
    - s:N (stream track N)
    - N (defaults to audio track N)
    """
    return TrackIndex.from_string(str(value))


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


def get_deezy_temp_info() -> tuple[Path, list[Path], float]:
    """Get information about DeeZy temp folders.

    Returns:
        tuple: (deezy_temp_base, job_folders, total_size_mb)
    """
    system_temp = Path(tempfile.gettempdir())
    deezy_temp_base = system_temp / "deezy"

    if not deezy_temp_base.exists():
        return deezy_temp_base, [], 0.0

    job_folders = []
    total_size = 0

    try:
        with os.scandir(deezy_temp_base) as entries:
            for entry in entries:
                if entry.is_dir():
                    folder_path = Path(entry.path)
                    job_folders.append(folder_path)

                    # calculate folder size
                    try:
                        folder_size = sum(
                            f.stat().st_size
                            for f in folder_path.rglob("*")
                            if f.is_file()
                        )
                        total_size += folder_size
                    except (OSError, PermissionError):
                        # skip folders we can't access
                        continue
    except (OSError, PermissionError):
        # if we can't scan the directory, return empty results
        return deezy_temp_base, [], 0.0

    total_size_mb = total_size / 1024 / 1024
    return deezy_temp_base, job_folders, total_size_mb


def clean_deezy_temp_folders(
    max_age_hours: int = 24, dry_run: bool = False
) -> tuple[int, float]:
    """Clean old DeeZy temp folders.

    Args:
        max_age_hours: Remove folders older than this many hours
        dry_run: If True, don't actually delete anything

    Returns:
        tuple: (folders_removed_count, total_size_mb_removed)
    """
    system_temp = Path(tempfile.gettempdir())
    deezy_temp_base = system_temp / "deezy"

    if not deezy_temp_base.exists():
        return 0, 0.0

    current_time = time.time()
    cutoff_time = current_time - (max_age_hours * 3600)

    folders_to_remove = []
    total_size = 0

    try:
        with os.scandir(deezy_temp_base) as entries:
            for entry in entries:
                if entry.is_dir():
                    try:
                        # use the cached stat info from scandir
                        folder_mtime = entry.stat().st_mtime
                        if folder_mtime < cutoff_time:
                            folder_path = Path(entry.path)
                            folder_size = sum(
                                f.stat().st_size
                                for f in folder_path.rglob("*")
                                if f.is_file()
                            )
                            folders_to_remove.append((folder_path, folder_size))
                            total_size += folder_size
                    except (OSError, PermissionError):
                        # skip folders we can't access
                        continue
    except (OSError, PermissionError):
        # if we can't scan the directory, return empty results
        return 0, 0.0

    if dry_run:
        return len(folders_to_remove), total_size / 1024 / 1024

    # remove folders
    removed_count = 0
    for folder, _ in folders_to_remove:
        try:
            shutil.rmtree(folder)
            removed_count += 1
        except (OSError, PermissionError):
            # skip folders we can't remove
            continue

    return removed_count, total_size / 1024 / 1024
