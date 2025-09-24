import argparse
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from deezy.config.manager import ConfigManager, get_config_manager
from deezy.info import parse_audio_streams
from deezy.track_info.track_index import TrackIndex
from deezy.utils.dependencies import DependencyNotFoundError, FindDependencies
from deezy.utils.exit import EXIT_FAIL, EXIT_SUCCESS, exit_application
from deezy.utils.file_parser import parse_input_s
from deezy.utils.logger import logger, logger_manager
from deezy.utils.utils import WORKING_DIRECTORY


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


def apply_config_defaults_to_args(
    args: argparse.Namespace, config_manager: Any
) -> tuple[int | None, int | None, int | None]:
    """Apply config defaults into argparse Namespace and resolve per-phase limits.

    Returns a 3-tuple of (ffmpeg_limit, dee_limit, truehd_limit) where None
    indicates "inherit max_parallel".
    """

    def _cfg_get(key: str):
        try:
            return config_manager.get_config_default(key) if config_manager else None
        except Exception:
            return None

    limits_map = {
        "limit_ffmpeg": "limit_ffmpeg",
        "limit_dee": "limit_dee",
        "limit_truehdd": "limit_truehdd",
    }

    resolved_limits: dict[str, int | None] = {}
    for attr, cfg_key in limits_map.items():
        val = getattr(args, attr, None)
        if val is None:
            cfg_val = _cfg_get(cfg_key)
            if cfg_val is not None:
                try:
                    cfg_int = int(cfg_val)
                    resolved_limits[attr] = None if cfg_int == 0 else cfg_int
                except Exception:
                    resolved_limits[attr] = None
            else:
                resolved_limits[attr] = None
        else:
            resolved_limits[attr] = val

    try:
        if getattr(args, "jitter_ms", 0) == 0:
            cfg_j = _cfg_get("jitter_ms")
            if cfg_j is not None:
                args.jitter_ms = int(cfg_j)
    except Exception:
        pass

    try:
        if getattr(args, "output_template", None) is None:
            cfg_ot = _cfg_get("output_template")
            if cfg_ot is not None:
                # ensure it's a string
                args.output_template = str(cfg_ot)
    except Exception:
        pass

    bool_keys = (
        "overwrite",
        "parse_elementary_delay",
        "log_to_file",
        "no_progress_bars",
    )
    for b in bool_keys:
        try:
            if not getattr(args, b, False):
                cfg_b = _cfg_get(b)
                if cfg_b is not None:
                    setattr(args, b, bool(cfg_b))
        except Exception:
            pass

    return (
        resolved_limits.get("limit_ffmpeg"),
        resolved_limits.get("limit_dee"),
        resolved_limits.get("limit_truehdd"),
    )


def apply_default_bitrate(
    args: argparse.Namespace, config_manager: ConfigManager | None
) -> None:
    """Apply default bitrate based on format and channels/mode if none specified."""
    if not hasattr(args, "bitrate") or args.bitrate is None:
        channels_or_mode = None
        if args.format_command == "atmos":
            if hasattr(args, "atmos_mode") and args.atmos_mode:
                channels_or_mode = (
                    args.atmos_mode.value
                    if hasattr(args.atmos_mode, "value")
                    else str(args.atmos_mode)
                )
        else:
            if hasattr(args, "channels") and args.channels:
                channels_or_mode = args.channels

        if config_manager is not None:
            try:
                default_bitrate = config_manager.get_default_bitrate(
                    args.format_command, channels_or_mode
                )
            except Exception:
                default_bitrate = None

            if default_bitrate:
                args.bitrate = default_bitrate
                logger.debug(
                    f"No bitrate specified, using default {default_bitrate}k for {args.format_command}"
                )


def handle_preset_injection() -> None:
    """Handle preset injection into sys.argv before argparse runs."""
    if len(sys.argv) >= 4 and "preset" in sys.argv and "--name" in sys.argv:
        try:
            name_idx = sys.argv.index("--name")
            if name_idx + 1 < len(sys.argv):
                preset_name = sys.argv[name_idx + 1]
                config_manager = get_config_manager()
                config_manager.load_config()
                config_manager.inject_preset_args(preset_name)
        except (ValueError, IndexError):
            pass


def setup_logging(args: argparse.Namespace) -> None:
    """Initialize logging based on arguments."""
    logger_manager.set_level(args.log_level.to_logging_level())


def handle_configuration(args: argparse.Namespace) -> ConfigManager | None:
    """Load configuration manager."""
    config_manager = None
    if args.sub_command != "config":
        config_manager = get_config_manager()
    return config_manager


def handle_dependencies(
    args: argparse.Namespace, config_manager: ConfigManager | None
) -> dict[str, Path | None] | None:
    """
    Handle tool dependencies detection.
    CLI > Config.
    """
    if args.sub_command in ("config", "temp"):
        return None

    deps = {}
    config_deps = (
        config_manager.config.get("dependencies", {}) if config_manager else {}
    )

    for key in ("ffmpeg", "truehdd", "dee"):
        cli_value = getattr(args, key, None)
        config_value = config_deps.get(key)
        deps[key] = cli_value or config_value

    atmos_required = getattr(args, "format_command", None) in ("atmos", "ac4")

    try:
        tools = FindDependencies().get_dependencies(
            WORKING_DIRECTORY,
            deps["ffmpeg"],
            deps["truehdd"],
            deps["dee"],
            require_truehdd=atmos_required,
        )
    except DependencyNotFoundError as e:
        exit_application(str(e), EXIT_FAIL)

    return {
        "ffmpeg_path": Path(tools.ffmpeg),
        "truehdd_path": Path(tools.truehdd) if tools.truehdd else None,
        "dee_path": Path(tools.dee),
    }


def handle_file_inputs(args: argparse.Namespace) -> list[Path]:
    """Parse and validate file inputs."""
    if not hasattr(args, "input") or not args.input:
        if args.sub_command not in {"config", "temp"}:
            exit_application("", EXIT_FAIL)
        return []

    if args.sub_command not in ("find", "info", "encode"):
        return []

    file_inputs = parse_input_s(args.input)
    if not file_inputs and args.sub_command in ("find", "info", "encode"):
        exit_application("No input files were found.", EXIT_FAIL)

    return file_inputs


def execute_find_command(args: argparse.Namespace, file_inputs: list[Path]) -> None:
    """Execute find command."""
    file_names = []
    for input_file in file_inputs:
        # if name only is used, print only the name of the file.
        if getattr(args, "name", False):
            input_file = input_file.name
        file_names.append(str(input_file))

    exit_application("\n".join(file_names), EXIT_SUCCESS)


def execute_info_command(_args: argparse.Namespace, file_inputs: list[Path]) -> None:
    """Execute info command."""
    track_s_info = ""
    for input_file in file_inputs:
        info = parse_audio_streams(input_file)
        if info.media_info:
            track_s_info = (
                track_s_info
                + f"File: {input_file.name}\nAudio tracks: {info.track_list}\n"
                + info.media_info
                + "\n\n"
            )
    exit_application(track_s_info, EXIT_SUCCESS)
