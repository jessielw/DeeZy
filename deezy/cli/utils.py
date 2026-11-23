import argparse
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
from typing import Any

from deezy.config.manager import ConfigManager, get_config_manager
from deezy.dee.shim import DeeShim, resolve_shim
from deezy.dee.tools import DependencyNotFoundError, FindDependencies
from deezy.enums.shared import PipeMode
from deezy.info import parse_audio_streams
from deezy.track_info.track_index import TrackIndex
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
        logger.debug("Best-effort operation failed; continuing.")

    try:
        if getattr(args, "output_template", None) is None:
            cfg_ot = _cfg_get("output_template")
            if cfg_ot is not None:
                # ensure it's a string
                args.output_template = str(cfg_ot)
    except Exception:
        logger.debug("Best-effort operation failed; continuing.")

    # only the formats with a --pipe option take the config's value
    if hasattr(args, "pipe") and args.pipe is None:
        cfg_pipe = _cfg_get("pipe")
        if cfg_pipe not in (None, ""):
            try:
                args.pipe = PipeMode(str(cfg_pipe))
            except ValueError:
                logger.warning(
                    f"Config pipe = '{cfg_pipe}' is not auto, always or never; "
                    "using auto."
                )

    bool_keys = (
        "allow_sleep",
        "overwrite",
        "parse_elementary_delay",
        "log_to_file",
        "keep_logs",
        "no_progress_bars",
    )
    for b in bool_keys:
        try:
            if not getattr(args, b, False):
                cfg_b = _cfg_get(b)
                if cfg_b is not None:
                    setattr(args, b, bool(cfg_b))
        except Exception:
            logger.debug("Best-effort operation failed; continuing.")

    return (
        resolved_limits.get("limit_ffmpeg"),
        resolved_limits.get("limit_dee"),
        resolved_limits.get("limit_truehdd"),
    )


# [global_defaults] keys DeeZy reads itself, so they aren't option defaults
OWN_CONFIG_KEYS = frozenset(
    {
        "temp_dir",
        "working_dir",
        "max_logs",
        "max_batch_results",
        "batch_output_dir",
        "limit_ffmpeg",
        "limit_dee",
        "limit_truehdd",
        "jitter_ms",
        "output_template",
        "pipe",
        "allow_sleep",
        "overwrite",
        "parse_elementary_delay",
        "log_to_file",
        "keep_logs",
        "no_progress_bars",
        "no_shim",
    }
)

# options [global_defaults] can't set, and where their value goes instead
NOT_CONFIG_DEFAULTS = {
    "output": "use output_template or batch_output_dir",
    "config": "give it on the command line",
    "name": "presets are run with 'encode preset --name'",
    "bitrate": "set default rates under [default_bitrates]",
    "ffmpeg": "set the path under [dependencies]",
    "dee": "set the path under [dependencies]",
    "truehdd": "set the path under [dependencies]",
    "dee_shim": "set the path under [dependencies]",
}


def _command_parsers(
    parser: argparse.ArgumentParser, args: argparse.Namespace
) -> list[argparse.ArgumentParser]:
    """The parsers args went through: deezy's, then each subcommand's."""
    chain = [parser]
    while True:
        sub = next(
            (
                a
                for a in chain[-1]._actions
                if isinstance(a, argparse._SubParsersAction)
            ),
            None,
        )
        name = getattr(args, sub.dest, None) if sub else None
        if sub is None or name not in sub.choices:
            return chain
        chain.append(sub.choices[name])


def _all_actions(parser: argparse.ArgumentParser) -> list[argparse.Action]:
    """The options of every command."""
    found = []
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for sub in action.choices.values():
                found += _all_actions(sub)
        elif action.option_strings:
            found.append(action)
    return found


def _config_option(
    key: str, actions: list[argparse.Action]
) -> tuple[argparse.Action, bool] | None:
    """The option a [global_defaults] key names, and whether it is a --no-x
    switch named by its positive form x."""
    option = "--" + key.replace("_", "-")
    by_option = {name: a for a in actions for name in a.option_strings}
    if option in by_option:
        return by_option[option], False
    negated = by_option.get("--no-" + option[2:])
    if isinstance(negated, argparse._StoreFalseAction):
        return negated, True
    return None


def _config_value(action: argparse.Action, value: Any, positive: bool) -> Any:
    """A config value as the option's default, checked as the option checks
    its command line value. Raises ValueError for one it would refuse."""
    option = action.option_strings[0]
    if isinstance(action, argparse._StoreTrueAction | argparse._StoreFalseAction):
        if not isinstance(value, bool):
            raise ValueError(f"{option} takes true or false")
        if isinstance(action, argparse._StoreFalseAction) and not positive:
            return not value
        return value
    if type(action) is not argparse._StoreAction or action.nargs is not None:
        raise ValueError(f"{option} can't be set in the config")
    if isinstance(value, bool | list | dict):
        raise ValueError(f"{option} takes a single value")
    try:
        convert = action.type
        converted = convert(str(value)) if callable(convert) else str(value)
    except (argparse.ArgumentTypeError, TypeError, ValueError) as e:
        raise ValueError(str(e) or f"not a {option} value") from e
    if action.choices is not None and converted not in action.choices:
        choices = ", ".join(str(getattr(c, "value", c)) for c in action.choices)
        raise ValueError(f"{option} takes {choices}")
    return converted


def apply_config_option_defaults(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
    config_manager: ConfigManager | None,
) -> bool:
    """Make the config's [global_defaults] the defaults of the command's options.

    A key is an option's name with '_' for '-' (--speech-threshold is
    speech_threshold); a --no-x switch may also be named by x, its positive
    form (dialogue_intelligence = false is --no-dialogue-intelligence). A key
    applies to the commands that have the option. The caller parses the
    command line again, so it, and a preset, still win. A key that names no
    option, or a value the option refuses, is ignored with a warning. Returns
    whether any default changed.
    """
    config = config_manager.config if config_manager else {}
    defaults = config.get("global_defaults") or {}
    if not defaults:
        return False
    command = [a for p in _command_parsers(parser, args) for a in p._actions]
    command = [a for a in command if a.option_strings]
    everything = _all_actions(parser)
    changed = False
    for key, value in defaults.items():
        key = str(key)
        if key in OWN_CONFIG_KEYS:
            continue
        if key in NOT_CONFIG_DEFAULTS:
            logger.warning(
                f"Config [global_defaults] {key} is ignored: "
                f"{NOT_CONFIG_DEFAULTS[key]}."
            )
            continue
        if _config_option(key, everything) is None:
            logger.warning(
                f"Config [global_defaults] {key} is ignored: DeeZy has no "
                f"--{key.replace('_', '-')} option."
            )
            continue
        found = _config_option(key, command)
        if found is None:
            continue  # another command's option
        action, positive = found
        try:
            default = _config_value(action, value, positive)
        except ValueError as e:
            logger.warning(
                f"Config [global_defaults] {key} = {value!r} is ignored: {e}."
            )
            continue
        # every option of the destination, so --no-surround-3db's default
        # doesn't win over --surround-3db's
        for other in command:
            if other.dest == action.dest:
                other.default = default
        changed = True
    return changed


def apply_default_bitrate(
    args: argparse.Namespace, config_manager: ConfigManager | None
) -> None:
    """Apply default bitrate based on format and channels/mode if none specified."""
    # Blu-ray secondary audio has its own rates and default (192 kbps); the
    # plain DD+ rates configured for its layout would override them
    if getattr(args, "bluray_secondary", False):
        return
    # TrueHD is lossless and has no data rate
    if getattr(args, "format_command", None) in ("thd", "thd-atmos"):
        return
    if not hasattr(args, "bitrate") or args.bitrate is None:
        channels_or_mode = None
        if args.format_command == "ddp-atmos":
            if hasattr(args, "atmos_mode") and args.atmos_mode:
                channels_or_mode = (
                    args.atmos_mode.value
                    if hasattr(args.atmos_mode, "value")
                    else str(args.atmos_mode)
                )
        elif args.format_command == "aac":
            # AAC's rates are per profile; the output is always 2.0
            profile = getattr(args, "aac_profile", None)
            if profile:
                channels_or_mode = getattr(profile, "value", str(profile))
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


def sniff_config_arg(argv: list[str] | None = None) -> str | None:
    """Read `--config` straight out of argv.

    Presets are injected before argparse runs, so the config that holds them
    has to be located without a parsed Namespace to read it from.
    """
    argv = sys.argv if argv is None else argv
    for i, arg in enumerate(argv):
        if arg == "--config":
            return argv[i + 1] if i + 1 < len(argv) else None
        if arg.startswith("--config="):
            return arg.split("=", 1)[1]
    return None


def handle_preset_injection() -> None:
    """Handle preset injection into sys.argv before argparse runs."""
    if len(sys.argv) >= 4 and "preset" in sys.argv and "--name" in sys.argv:
        try:
            name_idx = sys.argv.index("--name")
            if name_idx + 1 < len(sys.argv):
                preset_name = sys.argv[name_idx + 1]
                config_manager = get_config_manager(sniff_config_arg())
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
        # a user-supplied --config replaces auto-discovery (preset injection
        # may have loaded it already)
        config_manager = get_config_manager(getattr(args, "config", None) or None)
    return config_manager


def handle_dependencies(
    args: argparse.Namespace, config_manager: ConfigManager | None
) -> dict[str, Path | DeeShim | None] | None:
    """
    Handle tool dependencies detection.
    CLI > Config.
    """
    if args.sub_command in ("config", "temp", "bitrates", "tools"):
        return None

    deps = {}
    config_deps = (
        config_manager.config.get("dependencies", {}) if config_manager else {}
    )

    for key in ("ffmpeg", "truehdd", "dee"):
        cli_value = getattr(args, key, None)
        config_value = config_deps.get(key)
        deps[key] = cli_value or config_value

    atmos_required = getattr(args, "format_command", None) in (
        "ddp-atmos",
        "thd-atmos",
        "ac4-atmos",
        "ac4-ims",
    )

    finder = FindDependencies()
    try:
        tools = finder.get_dependencies(
            WORKING_DIRECTORY,
            deps["ffmpeg"],
            deps["truehdd"],
            deps["dee"],
            require_truehdd=atmos_required,
        )
        finder.check_dee_version(Path(tools.dee))
        shim = _dee_shim(args, config_manager, Path(tools.dee))
    except DependencyNotFoundError as e:
        exit_application(str(e), EXIT_FAIL)

    return {
        "ffmpeg_path": Path(tools.ffmpeg),
        "truehdd_path": Path(tools.truehdd) if tools.truehdd else None,
        "dee_path": Path(tools.dee),
        "dee_shim": shim,
    }


def _dee_shim(
    args: argparse.Namespace, config_manager: ConfigManager | None, dee_dir: Path
) -> DeeShim | None:
    """dee_shim for an encode (CLI > config > found), unless it is turned off."""
    if args.sub_command != "encode":
        return None
    config = config_manager.config if config_manager else {}
    disabled = bool(getattr(args, "no_shim", False)) or bool(
        config.get("global_defaults", {}).get("no_shim", False)
    )
    user_value = getattr(args, "dee_shim", None) or config.get("dependencies", {}).get(
        "dee_shim"
    )
    return resolve_shim(WORKING_DIRECTORY, dee_dir, user_value, disabled)


def handle_file_inputs(args: argparse.Namespace) -> list[Path]:
    """Parse and validate file inputs."""
    if not hasattr(args, "input") or not args.input:
        if args.sub_command not in {"config", "temp", "bitrates", "tools"}:
            exit_application("", EXIT_FAIL)
        return []

    if args.sub_command not in ("find", "info", "encode", "measure"):
        return []

    try:
        file_inputs = parse_input_s(args.input)
    except FileNotFoundError as e:
        # a mistyped path is a user error, not something to hand back a traceback for
        exit_application(str(e), EXIT_FAIL)

    if not file_inputs and args.sub_command in ("find", "info", "encode", "measure"):
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
