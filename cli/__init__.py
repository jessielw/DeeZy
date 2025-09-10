import argparse
from pathlib import Path
import sys

from cli.utils import (
    CustomHelpFormatter,
    dialnorm_options,
    int_0_100,
    validate_track_index,
)
from deezy.audio_encoders.dee.atmos import AtmosEncoder
from deezy.audio_encoders.dee.dd import DDEncoderDEE
from deezy.audio_encoders.dee.ddp import DDPEncoderDEE
from deezy.config.defaults import get_default_config_path
from deezy.config.manager import get_config_manager
from deezy.enums import case_insensitive_enum, enum_choices
from deezy.enums.atmos import AtmosMode, WarpMode
from deezy.enums.dd import DolbyDigitalChannels
from deezy.enums.ddp import DolbyDigitalPlusChannels
from deezy.enums.ddp_bluray import DolbyDigitalPlusBlurayChannels
from deezy.enums.shared import DeeDRC, LogLevel, MeteringMode, StereoDownmix
from deezy.info import parse_audio_streams
from deezy.payloads.atmos import AtmosPayload
from deezy.payloads.dd import DDPayload
from deezy.payloads.ddp import DDPPayload
from deezy.utils._version import __version__, program_name
from deezy.utils.dependencies import DependencyNotFoundError, FindDependencies
from deezy.utils.exit import EXIT_FAIL, EXIT_SUCCESS, exit_application
from deezy.utils.file_parser import parse_input_s
from deezy.utils.logger import logger, logger_manager


def create_main_parser():
    """Create the main argument parser with global options."""
    parser = argparse.ArgumentParser(prog=program_name)
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "--config",
        type=str,
        help="Path to configuration file (default: deezy-conf.toml beside executable)",
        metavar="CONFIG_FILE",
    )
    parser.add_argument(
        "--log-level",
        type=case_insensitive_enum(LogLevel),
        default=LogLevel.INFO,
        choices=tuple(LogLevel),
        metavar=enum_choices(LogLevel),
        help="Sets the log level (defaults to INFO).",
    )
    parser.add_argument(
        "--log-to-file",
        action="store_true",
        help="Write log to file (defaults to input path with suffix of .log).",
    )
    parser.add_argument(
        "--no-progress-bars",
        action="store_true",
        help="Disables progress bars on level INFO (disabled for DEBUG or higher).",
    )
    return parser


def create_common_argument_groups():
    """Create reusable argument groups."""
    # Input files argument group
    input_group = argparse.ArgumentParser(add_help=False)
    input_group.add_argument(
        "input", nargs="+", help="Input file paths or directories", metavar="INPUT"
    )

    # Common Encode Args
    encode_group = argparse.ArgumentParser(add_help=False)
    encode_group.add_argument(
        "--ffmpeg",
        type=str,
        help="Path to FFMPEG executable.",
    )
    encode_group.add_argument(
        "--truehdd",
        type=str,
        help="Path to Truehdd executable.",
    )
    encode_group.add_argument(
        "--dee",
        type=str,
        help="Path to Dolby Encoding Engine executable.",
    )
    encode_group.add_argument(
        "--track-index",
        type=validate_track_index,
        default=0,
        help="The index of the audio track to use.",
    )
    encode_group.add_argument(
        "--delay",
        type=str,
        help="The delay in milliseconds or seconds. Note '--delay=' is required! (--delay=-10ms / --delay=10s).",
    )
    encode_group.add_argument(
        "--keep-temp",
        action="store_true",
        help="Keeps the temp files after finishing.",
    )
    encode_group.add_argument(
        "--temp-dir",
        type=str,
        help=(
            "Path to store temporary files to. If not specified this will "
            "automatically happen in the temp dir of the os."
        ),
    )
    encode_group.add_argument(
        "--output",
        type=str,
        help=(
            "The output file path. If not specified we will attempt to automatically add "
            "Delay/Language string to output file name."
        ),
    )

    # codec group
    codec_group = argparse.ArgumentParser(add_help=False)
    codec_group.add_argument(
        "--bitrate",
        type=int,
        default=None,
        help=(
            "The bitrate in Kbps (If too high or low for you desired layout, "
            "the bitrate will automatically be adjusted to the closest allowed bitrate)."
        ),
    )
    codec_group.add_argument(
        "--drc-line-mode",
        type=case_insensitive_enum(DeeDRC),
        choices=tuple(DeeDRC),
        metavar=enum_choices(DeeDRC),
        default=DeeDRC.FILM_LIGHT,
        help="Dynamic range compression settings.",
    )
    codec_group.add_argument(
        "--drc-rf-mode",
        type=case_insensitive_enum(DeeDRC),
        choices=tuple(DeeDRC),
        metavar=enum_choices(DeeDRC),
        default=DeeDRC.FILM_LIGHT,
        help="Dynamic range compression settings.",
    )
    codec_group.add_argument(
        "--custom-dialnorm",
        type=dialnorm_options,
        default=0,
        help="Custom dialnorm (0 disables custom dialnorm).",
    )

    # dialogue intelligence group
    shared_loudness_args = argparse.ArgumentParser(add_help=False)
    dd_ddp_metering_choices = (
        MeteringMode.MODE_1770_1,
        MeteringMode.MODE_1770_2,
        MeteringMode.MODE_1770_3,
        MeteringMode.MODE_LEQA,
    )
    shared_loudness_args.add_argument(
        "--metering-mode",
        type=case_insensitive_enum(MeteringMode),
        choices=dd_ddp_metering_choices,
        metavar="{" + ",".join(str(e.value) for e in dd_ddp_metering_choices) + "}",
        default=MeteringMode.MODE_1770_3,
        help="Loudness measuring mode according to one of the broadcast standards.",
    )
    shared_loudness_args.add_argument(
        "--no-dialogue-intelligence",
        action="store_false",
        help="Dialogue Intelligence enabled. Option ignored for 1770-1 or LeqA metering mode.",
    )
    shared_loudness_args.add_argument(
        "--speech-threshold",
        type=int_0_100,
        default=15,
        help=(
            "[0-100] If the percentage of speech is higher than the threshold, the encoder uses speech "
            "gating to set the dialnorm value. (Otherwise, the encoder uses level gating)."
        ),
    )

    # atmos loudness args (supports all metering modes including 1770-4)
    atmos_loudness_args = argparse.ArgumentParser(add_help=False)
    atmos_metering_choices = tuple(MeteringMode)
    atmos_loudness_args.add_argument(
        "--metering-mode",
        type=case_insensitive_enum(MeteringMode),
        choices=atmos_metering_choices,
        metavar="{" + ",".join(str(e.value) for e in atmos_metering_choices) + "}",
        default=MeteringMode.MODE_1770_4,
        help="Loudness measuring mode according to one of the broadcast standards.",
    )
    atmos_loudness_args.add_argument(
        "--no-dialogue-intelligence",
        action="store_false",
        help="Dialogue Intelligence enabled. Option ignored for 1770-1 or LeqA metering mode.",
    )
    atmos_loudness_args.add_argument(
        "--speech-threshold",
        type=int_0_100,
        default=15,
        help=(
            "[0-100] If the percentage of speech is higher than the threshold, the encoder uses speech "
            "gating to set the dialnorm value. (Otherwise, the encoder uses level gating)."
        ),
    )

    # dd/ddp (no atmos) only group
    dd_ddp_only_group = argparse.ArgumentParser(add_help=False)
    dd_ddp_only_group.add_argument(
        "--no-low-pass-filter",
        action="store_false",
        help="Disables low pass filter.",
    )
    dd_ddp_only_group.add_argument(
        "--no-surround-3db",
        action="store_false",
        help="Disables surround 3db attenuation.",
    )
    dd_ddp_only_group.add_argument(
        "--no-surround-90-deg-phase-shift",
        action="store_false",
        help="Disables surround 90 degree phase shift.",
    )

    # dd stereo downmix
    stereo_downmix_metadata_group = argparse.ArgumentParser(add_help=False)
    stereo_downmix_metadata_group.add_argument(
        "--stereo-down-mix",
        type=case_insensitive_enum(StereoDownmix),
        choices=tuple(StereoDownmix),
        default=StereoDownmix.LORO,
        metavar=enum_choices(StereoDownmix),
        help="Down mix method for stereo.",
    )

    # down mixing metadata
    downmix_metadata_group = argparse.ArgumentParser(add_help=False)
    downmix_metadata_group.add_argument(
        "--lt-rt-center",
        type=str,
        choices=("+3", "+1.5", "0", "-1.5", "-3", "-4.5", "-6", "-inf"),
        default="-3",
        help="Lt/Rt center downmix level.",
    )
    downmix_metadata_group.add_argument(
        "--lt-rt-surround",
        type=str,
        choices=("-1.5", "-3", "-4.5", "-6", "-inf"),
        default="-3",
        help="Lt/Rt surround downmix level.",
    )
    downmix_metadata_group.add_argument(
        "--lo-ro-center",
        type=str,
        choices=("+3", "+1.5", "0", "-1.5", "-3", "-4.5", "-6", "-inf"),
        default="-3",
        help="Lo/Ro center downmix level.",
    )
    downmix_metadata_group.add_argument(
        "--lo-ro-surround",
        type=str,
        choices=("-1.5", "-3", "-4.5", "-6", "-inf"),
        default="-3",
        help="Lo/Ro surround downmix level.",
    )

    return {
        "input_group": input_group,
        "encode_group": encode_group,
        "codec_group": codec_group,
        "shared_loudness_args": shared_loudness_args,
        "atmos_loudness_args": atmos_loudness_args,
        "dd_ddp_only_group": dd_ddp_only_group,
        "stereo_downmix_metadata_group": stereo_downmix_metadata_group,
        "downmix_metadata_group": downmix_metadata_group,
    }


def create_encode_parsers(subparsers, argument_groups):
    """Create encode command parsers."""
    # Encode command parser
    encode_parser = subparsers.add_parser("encode")
    encode_subparsers = encode_parser.add_subparsers(
        dest="format_command", required=True
    )

    ### Dolby Digital Command ###
    encode_dd_parser = encode_subparsers.add_parser(
        "dd",
        parents=(
            argument_groups["input_group"],
            argument_groups["encode_group"],
            argument_groups["codec_group"],
            argument_groups["shared_loudness_args"],
            argument_groups["dd_ddp_only_group"],
            argument_groups["stereo_downmix_metadata_group"],
            argument_groups["downmix_metadata_group"],
        ),
        formatter_class=lambda prog: CustomHelpFormatter(
            prog,
            width=78,
            max_help_position=7,
        ),
    )
    encode_dd_parser.add_argument(
        "--channels",
        type=case_insensitive_enum(DolbyDigitalChannels),
        choices=tuple(DolbyDigitalChannels),
        default=DolbyDigitalChannels.AUTO,
        metavar=enum_choices(DolbyDigitalChannels),
        help="The number of channels.",
    )

    ### Dolby Digital Plus Command ###
    encode_ddp_parser = encode_subparsers.add_parser(
        "ddp",
        parents=(
            argument_groups["input_group"],
            argument_groups["encode_group"],
            argument_groups["codec_group"],
            argument_groups["shared_loudness_args"],
            argument_groups["dd_ddp_only_group"],
            argument_groups["stereo_downmix_metadata_group"],
            argument_groups["downmix_metadata_group"],
        ),
        formatter_class=lambda prog: CustomHelpFormatter(
            prog,
            width=78,
            max_help_position=7,
        ),
    )
    encode_ddp_parser.add_argument(
        "--channels",
        type=case_insensitive_enum(DolbyDigitalPlusChannels),
        choices=tuple(DolbyDigitalPlusChannels),
        default=DolbyDigitalPlusChannels.AUTO,
        metavar=enum_choices(DolbyDigitalPlusChannels),
        help="The number of channels.",
    )

    ### Dolby Digital Plus BluRay Command ###
    encode_ddp_bluray_parser = encode_subparsers.add_parser(
        "ddp-bluray",
        parents=(
            argument_groups["input_group"],
            argument_groups["encode_group"],
            argument_groups["codec_group"],
            argument_groups["shared_loudness_args"],
            argument_groups["dd_ddp_only_group"],
            argument_groups["stereo_downmix_metadata_group"],
            argument_groups["downmix_metadata_group"],
        ),
        formatter_class=lambda prog: CustomHelpFormatter(
            prog,
            width=78,
            max_help_position=7,
        ),
    )
    encode_ddp_bluray_parser.add_argument(
        "--channels",
        type=case_insensitive_enum(DolbyDigitalPlusBlurayChannels),
        choices=tuple(DolbyDigitalPlusBlurayChannels),
        default=DolbyDigitalPlusBlurayChannels.SURROUNDEX,
        metavar=enum_choices(DolbyDigitalPlusBlurayChannels),
        help="The number of channels.",
    )

    ### Atmos Command ###
    encode_atmos_parser = encode_subparsers.add_parser(
        "atmos",
        parents=(
            argument_groups["input_group"],
            argument_groups["encode_group"],
            argument_groups["codec_group"],
            argument_groups["atmos_loudness_args"],
            argument_groups["downmix_metadata_group"],
        ),
        formatter_class=lambda prog: CustomHelpFormatter(
            prog,
            width=78,
            max_help_position=7,
        ),
    )
    encode_atmos_parser.add_argument(
        "--atmos-mode",
        type=case_insensitive_enum(AtmosMode),
        choices=tuple(AtmosMode),
        default=AtmosMode.STREAMING,
        metavar=enum_choices(AtmosMode),
        help="Atmos encoding mode.",
    )
    encode_atmos_parser.add_argument(
        "--thd-warp-mode",
        type=case_insensitive_enum(WarpMode),
        choices=tuple(WarpMode),
        default=WarpMode.NORMAL,
        metavar=enum_choices(WarpMode),
        help="Specify warp mode when not present in metadata (truehdd).",
    )
    encode_atmos_parser.add_argument(
        "--no-bed-conform",
        action="store_false",
        help="Disables bed conformance for Atmos content (truehd).",
    )

    ### Preset Command ###
    encode_preset_parser = encode_subparsers.add_parser(
        "preset",
        parents=(
            argument_groups["input_group"],
            argument_groups["encode_group"],
            argument_groups["codec_group"],
            argument_groups["shared_loudness_args"],
            argument_groups["dd_ddp_only_group"],
            argument_groups["stereo_downmix_metadata_group"],
            argument_groups["downmix_metadata_group"],
        ),
        formatter_class=lambda prog: CustomHelpFormatter(
            prog,
            width=78,
            max_help_position=7,
        ),
        help="Encode using a preset configuration (format determined from preset).",
    )
    encode_preset_parser.add_argument(
        "--name",
        dest="preset_name",
        required=True,
        help="Name of the preset to use for encoding.",
        metavar="PRESET_NAME",
    )
    # add format-specific arguments that might be needed
    encode_preset_parser.add_argument(
        "--channels",
        type=str,
        help="Override channels setting from preset (format depends on preset's format).",
    )
    encode_preset_parser.add_argument(
        "--atmos-mode",
        type=case_insensitive_enum(AtmosMode),
        choices=tuple(AtmosMode),
        default=AtmosMode.STREAMING,
        metavar=enum_choices(AtmosMode),
        help="Atmos encoding mode (only used if preset format is atmos).",
    )
    encode_preset_parser.add_argument(
        "--thd-warp-mode",
        type=case_insensitive_enum(WarpMode),
        choices=tuple(WarpMode),
        default=WarpMode.NORMAL,
        metavar=enum_choices(WarpMode),
        help="Specify warp mode when not present in metadata (only used if preset format is atmos).",
    )
    encode_preset_parser.add_argument(
        "--no-bed-conform",
        action="store_false",
        help="Disables bed conformance for Atmos content (only used if preset format is atmos).",
    )


def create_other_parsers(subparsers, argument_groups):
    """Create find, info, and config command parsers."""
    # Find command parser
    find_parser = subparsers.add_parser(
        "find", parents=[argument_groups["input_group"]]
    )
    find_parser.add_argument(
        "-n",
        "--name",
        action="store_true",
        help="Only display names instead of full paths.",
    )

    # Info command parser
    _info_parser = subparsers.add_parser(
        "info", parents=[argument_groups["input_group"]]
    )

    # Config command parser
    config_parser = subparsers.add_parser("config", help="Configuration management")
    config_subparsers = config_parser.add_subparsers(
        dest="config_command", required=True
    )

    # Generate config subcommand
    generate_parser = config_subparsers.add_parser(
        "generate", help="Generate configuration file"
    )
    generate_parser.add_argument(
        "-o",
        "--output",
        type=str,
        help="Output path for config file (default: auto-detect)",
    )
    generate_parser.add_argument(
        "--overwrite", action="store_true", help="Overwrite existing config file"
    )
    generate_parser.add_argument(
        "--from-args",
        action="store_true",
        help="Generate config from current CLI arguments (use with encode command)",
    )

    # info config subcommand
    info_parser = config_subparsers.add_parser(
        "info", help="Show configuration information"
    )
    info_parser.add_argument("--path", type=str, help="Show specific config file path")

    # validate config subcommand
    validate_parser = config_subparsers.add_parser(
        "validate", help="Validate configuration file"
    )
    validate_parser.add_argument("--preset", type=str, help="Validate specific preset")

    # list presets subcommand
    list_parser = config_subparsers.add_parser(
        "list-presets", help="List available presets"
    )
    list_parser.add_argument(
        "--detailed", action="store_true", help="Show detailed preset information"
    )


def apply_default_bitrate(args, config_manager):
    """Apply default bitrate based on format and channels/mode if none specified."""
    if not hasattr(args, "bitrate") or args.bitrate is None:
        # determine the channel/mode key based on format
        channels_or_mode = None
        if args.format_command == "atmos":
            # for Atmos, use the mode (streaming/bluray)
            if hasattr(args, "atmos_mode") and args.atmos_mode:
                channels_or_mode = (
                    args.atmos_mode.value
                    if hasattr(args.atmos_mode, "value")
                    else str(args.atmos_mode)
                )
        else:
            # for DD/DDP, use channels
            if hasattr(args, "channels") and args.channels:
                channels_or_mode = args.channels

        # get default bitrate from config
        default_bitrate = config_manager.get_default_bitrate(
            args.format_command, channels_or_mode
        )

        if default_bitrate:
            args.bitrate = default_bitrate
            logger.info(
                f"No bitrate specified, using default {default_bitrate}k for {args.format_command}"
            )


def handle_preset_injection():
    """Handle preset injection into sys.argv before argparse runs."""

    # check if this is a preset command
    if len(sys.argv) >= 4 and "preset" in sys.argv and "--name" in sys.argv:
        try:
            name_idx = sys.argv.index("--name")

            # get preset name (should be right after --name)
            if name_idx + 1 < len(sys.argv):
                preset_name = sys.argv[name_idx + 1]

                # load config and get preset
                config_manager = get_config_manager()
                config_manager.load_config()
                config_manager.inject_preset_args(preset_name)

        except (ValueError, IndexError):
            # preset parsing failed, let argparse handle the error
            pass


def cli_parser(base_wd: Path):
    """Main CLI parser entry point."""
    # handle presets by injecting args before parsing
    handle_preset_injection()

    # create parser and subcommands
    parser = create_main_parser()
    subparsers = parser.add_subparsers(dest="sub_command")

    # create argument groups and parsers
    argument_groups = create_common_argument_groups()
    create_encode_parsers(subparsers, argument_groups)
    create_other_parsers(subparsers, argument_groups)

    # parse arguments and initialize
    args = parser.parse_args()
    setup_logging(args)

    if not args.sub_command:
        if not hasattr(args, "version"):
            parser.print_usage()
        exit_application("", EXIT_FAIL)

    # handle configuration and dependencies
    config_manager = handle_configuration(args)

    # apply default bitrates for encoding commands
    if args.sub_command == "encode" and hasattr(args, "format_command"):
        apply_default_bitrate(args, config_manager)
    dependencies = handle_dependencies(args, base_wd, config_manager)
    file_inputs = handle_file_inputs(args)

    # execute the appropriate command
    execute_command(args, file_inputs, dependencies, config_manager)


def setup_logging(args):
    """Initialize logging based on arguments."""
    logger_manager.set_level(args.log_level.to_logging_level())


def handle_configuration(args):
    """Load configuration manager."""
    config_manager = None
    if args.sub_command != "config":
        config_manager = get_config_manager()
        # config is already loaded by preset injection if needed

    return config_manager


def handle_dependencies(args, base_wd, config_manager):
    """Handle tool dependencies detection."""
    if args.sub_command in {"config"}:
        return None

    # get dependency paths from CLI args or config
    ffmpeg_arg = None
    truehdd_arg = None
    # Simple dependency handling - just use what's provided in args or empty string for auto-detection
    ffmpeg_arg = args.ffmpeg if hasattr(args, "ffmpeg") and args.ffmpeg else ""
    truehdd_arg = args.truehdd if hasattr(args, "truehdd") and args.truehdd else ""
    dee_arg = args.dee if hasattr(args, "dee") and args.dee else ""

    # check if Atmos is being used (only available for DDP)
    atmos_required = hasattr(args, "format_command") and args.format_command == "atmos"

    try:
        tools = FindDependencies().get_dependencies(
            base_wd,
            ffmpeg_arg,
            truehdd_arg,
            dee_arg,
            require_truehdd=atmos_required,
        )
    except DependencyNotFoundError as e:
        exit_application(str(e), EXIT_FAIL)

    return {
        "ffmpeg_path": Path(tools.ffmpeg),
        "truehdd_path": Path(tools.truehdd) if tools.truehdd else None,
        "dee_path": Path(tools.dee),
    }


def handle_file_inputs(args):
    """Parse and validate file inputs."""
    if not hasattr(args, "input") or not args.input:
        if args.sub_command not in {"config"}:
            exit_application("", EXIT_FAIL)
        return []

    if args.sub_command not in ("find", "info", "encode"):
        return []

    # parse all possible file inputs
    file_inputs = parse_input_s(args.input)
    if not file_inputs and args.sub_command in ("find", "info", "encode"):
        exit_application("No input files were found.", EXIT_FAIL)

    return file_inputs


def execute_command(args, file_inputs, dependencies, config_manager):
    """Execute the appropriate command based on parsed arguments."""
    if args.sub_command == "encode":
        execute_encode_command(args, file_inputs, dependencies)
    elif args.sub_command == "find":
        execute_find_command(args, file_inputs)
    elif args.sub_command == "info":
        execute_info_command(args, file_inputs)
    elif args.sub_command == "config":
        execute_config_command(args, config_manager)


def execute_encode_command(args, file_inputs, dependencies):
    """Execute encoding commands."""
    ffmpeg_path = dependencies["ffmpeg_path"]
    truehdd_path = dependencies["truehdd_path"]
    dee_path = dependencies["dee_path"]

    # encode Dolby Digital
    if args.format_command == "dd":
        try:
            for input_file in file_inputs:
                # update logger to write to file if needed
                if args.log_to_file:
                    logger_manager.set_file(input_file.with_suffix(".log"))
                payload = DDPayload(
                    no_progress_bars=args.no_progress_bars,
                    ffmpeg_path=ffmpeg_path,
                    truehdd_path=truehdd_path,
                    dee_path=dee_path,
                    file_input=input_file,
                    track_index=args.track_index,
                    bitrate=args.bitrate,
                    temp_dir=Path(args.temp_dir) if args.temp_dir else None,
                    delay=args.delay,
                    keep_temp=args.keep_temp,
                    file_output=Path(args.output) if args.output else None,
                    stereo_mix=args.stereo_down_mix,
                    metering_mode=args.metering_mode,
                    drc_line_mode=args.drc_line_mode,
                    drc_rf_mode=args.drc_rf_mode,
                    dialogue_intelligence=args.no_dialogue_intelligence,
                    speech_threshold=args.speech_threshold,
                    custom_dialnorm=str(args.custom_dialnorm),
                    channels=args.channels,
                    lfe_lowpass_filter=args.no_low_pass_filter,
                    surround_90_degree_phase_shift=args.no_surround_3db,
                    surround_3db_attenuation=args.no_surround_90_deg_phase_shift,
                    loro_center_mix_level=args.lo_ro_center,
                    loro_surround_mix_level=args.lo_ro_surround,
                    ltrt_center_mix_level=args.lt_rt_center,
                    ltrt_surround_mix_level=args.lt_rt_surround,
                    preferred_downmix_mode=args.stereo_down_mix,
                )
                dd = DDEncoderDEE(payload).encode()
                logger.info(f"Job successful! Output file path:\n{dd}")
        except Exception as e:
            exit_application(str(e), EXIT_FAIL)

    # Encode Dolby Digital Plus
    elif args.format_command in ("ddp", "ddp-bluray"):
        try:
            for input_file in file_inputs:
                # update logger to write to file if needed
                if args.log_to_file:
                    logger_manager.set_file(input_file.with_suffix(".log"))
                payload = DDPPayload(
                    no_progress_bars=args.no_progress_bars,
                    ffmpeg_path=ffmpeg_path,
                    truehdd_path=truehdd_path,
                    dee_path=dee_path,
                    file_input=input_file,
                    track_index=args.track_index,
                    bitrate=args.bitrate,
                    temp_dir=Path(args.temp_dir) if args.temp_dir else None,
                    delay=args.delay,
                    keep_temp=args.keep_temp,
                    file_output=Path(args.output) if args.output else None,
                    stereo_mix=args.stereo_down_mix,
                    metering_mode=args.metering_mode,
                    drc_line_mode=args.drc_line_mode,
                    drc_rf_mode=args.drc_rf_mode,
                    dialogue_intelligence=args.no_dialogue_intelligence,
                    speech_threshold=args.speech_threshold,
                    custom_dialnorm=str(args.custom_dialnorm),
                    channels=args.channels,
                    lfe_lowpass_filter=args.no_low_pass_filter,
                    surround_90_degree_phase_shift=args.no_surround_3db,
                    surround_3db_attenuation=args.no_surround_90_deg_phase_shift,
                    loro_center_mix_level=args.lo_ro_center,
                    loro_surround_mix_level=args.lo_ro_surround,
                    ltrt_center_mix_level=args.lt_rt_center,
                    ltrt_surround_mix_level=args.lt_rt_surround,
                    preferred_downmix_mode=args.stereo_down_mix,
                )
                ddp = DDPEncoderDEE(payload).encode()
                logger.info(f"Job successful! Output file path:\n{ddp}")
        except Exception as e:
            exit_application(str(e), EXIT_FAIL)

    # Encode Atmos
    elif args.format_command == "atmos":
        try:
            for input_file in file_inputs:
                # update logger to write to file if needed
                if args.log_to_file:
                    logger_manager.set_file(input_file.with_suffix(".log"))
                payload = AtmosPayload(
                    no_progress_bars=args.no_progress_bars,
                    ffmpeg_path=ffmpeg_path,
                    truehdd_path=truehdd_path,
                    dee_path=dee_path,
                    file_input=input_file,
                    track_index=args.track_index,
                    bitrate=args.bitrate,
                    temp_dir=Path(args.temp_dir) if args.temp_dir else None,
                    delay=args.delay,
                    keep_temp=args.keep_temp,
                    file_output=Path(args.output) if args.output else None,
                    stereo_mix=StereoDownmix.NOT_INDICATED,  # this is unused but must be passed
                    metering_mode=args.metering_mode,
                    drc_line_mode=args.drc_line_mode,
                    drc_rf_mode=args.drc_rf_mode,
                    dialogue_intelligence=args.no_dialogue_intelligence,
                    speech_threshold=args.speech_threshold,
                    custom_dialnorm=str(args.custom_dialnorm),
                    lfe_lowpass_filter=False,  # this is unused but must be passed
                    surround_90_degree_phase_shift=False,  # this is unused but must be passed
                    surround_3db_attenuation=False,  # this is unused but must be passed
                    loro_center_mix_level=args.lo_ro_center,
                    loro_surround_mix_level=args.lo_ro_surround,
                    ltrt_center_mix_level=args.lt_rt_center,
                    ltrt_surround_mix_level=args.lt_rt_surround,
                    preferred_downmix_mode=StereoDownmix.LORO,
                    atmos_mode=args.atmos_mode,
                    thd_wrap_mode=args.thd_warp_mode,
                    no_bed_conform=args.no_bed_conform,
                )
                atmos_job = AtmosEncoder(payload).encode()
                logger.info(f"Job successful! Output file path:\n{atmos_job}")
        except Exception as e:
            exit_application(str(e), EXIT_FAIL)

    # encode using preset (format_command was set by config manager based on preset)
    elif args.format_command == "preset":
        # this should not happen since config manager converts "preset" to actual format
        exit_application(
            "Preset format conversion failed. This is a bug in the configuration system.",
            EXIT_FAIL,
        )


def execute_find_command(args, file_inputs):
    """Execute find command."""
    file_names = []
    for input_file in file_inputs:
        # if name only is used, print only the name of the file.
        if args.name:
            input_file = input_file.name
        file_names.append(str(input_file))

    exit_application("\n".join(file_names), EXIT_SUCCESS)


def execute_info_command(args, file_inputs):
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


def execute_config_command(args, config_manager):
    """Execute config command."""
    # config commands need their own manager instance
    if config_manager is None:
        config_manager = get_config_manager()

    if args.config_command == "generate":
        try:
            output_path = Path(args.output) if args.output else None

            # generate config (simplified - no from_args support yet)
            config_path = config_manager.generate_config(
                output_path=output_path, overwrite=args.overwrite
            )

            exit_application(
                f"Configuration file generated: {config_path}", EXIT_SUCCESS
            )

        except FileExistsError:
            exit_application(
                "Configuration file already exists. Use --overwrite to replace it.",
                EXIT_FAIL,
            )
        except Exception as e:
            exit_application(f"Failed to generate config: {e}", EXIT_FAIL)

    elif args.config_command == "info":
        try:
            if args.path:
                config_path = Path(args.path)
                if config_path.exists():
                    exit_application(f"Config file: {config_path}", EXIT_SUCCESS)
                else:
                    exit_application(f"Config file not found: {config_path}", EXIT_FAIL)
            else:
                if config_manager.config_path:
                    info_text = f"Active config file: {config_manager.config_path}\n"
                    info_text += f"Presets available: {', '.join(config_manager.list_presets()) or 'None'}"
                else:
                    info_text = (
                        "No configuration file found. Using built-in defaults.\n"
                    )
                    info_text += f"Default config location: {get_default_config_path()}"

                exit_application(info_text, EXIT_SUCCESS)
        except Exception as e:
            exit_application(f"Failed to load config info: {e}", EXIT_FAIL)

    elif args.config_command == "validate":
        try:
            if not config_manager.has_valid_config():
                exit_application("No configuration file found to validate.", EXIT_FAIL)

            if args.preset:
                # validate specific preset
                if args.preset not in config_manager.list_presets():
                    available = ", ".join(config_manager.list_presets()) or "None"
                    exit_application(
                        f"Preset '{args.preset}' not found. Available: {available}",
                        EXIT_FAIL,
                    )

                if config_manager.validate_preset(args.preset):
                    exit_application(f"Preset '{args.preset}' is valid.", EXIT_SUCCESS)
                else:
                    exit_application(f"Preset '{args.preset}' is invalid.", EXIT_FAIL)
            else:
                # validate all presets
                presets = config_manager.list_presets()
                if not presets:
                    exit_application("No presets found in configuration.", EXIT_SUCCESS)

                invalid_presets = []
                for preset in presets:
                    if not config_manager.validate_preset(preset):
                        invalid_presets.append(preset)

                if invalid_presets:
                    exit_application(
                        f"Invalid presets found: {', '.join(invalid_presets)}",
                        EXIT_FAIL,
                    )
                else:
                    exit_application(
                        f"All {len(presets)} presets are valid.", EXIT_SUCCESS
                    )

        except Exception as e:
            exit_application(f"Failed to validate config: {e}", EXIT_FAIL)

    elif args.config_command == "list-presets":
        try:
            presets = config_manager.list_presets()
            if not presets:
                exit_application("No presets found in configuration.", EXIT_SUCCESS)

            if args.detailed:
                info_lines = ["Available presets:"]
                for preset in presets:
                    preset_info = config_manager.get_preset_info(preset)
                    valid = "✓" if config_manager.validate_preset(preset) else "✗"
                    info_lines.append(f"  {valid} {preset}: {preset_info['command']}")
                exit_application("\n".join(info_lines), EXIT_SUCCESS)
            else:
                exit_application(
                    f"Available presets: {', '.join(presets)}", EXIT_SUCCESS
                )

        except Exception as e:
            exit_application(f"Failed to list presets: {e}", EXIT_FAIL)
