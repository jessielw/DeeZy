import argparse
from pathlib import Path
import sys
import traceback

from cli.payload_factory import PayloadBuilder
from cli.utils import (
    CustomHelpFormatter,
    clean_deezy_temp_folders,
    dialnorm_options,
    get_deezy_temp_info,
    int_0_100,
    validate_track_index,
)
from deezy.audio_encoders.dee.ac4 import Ac4Encoder
from deezy.audio_encoders.dee.atmos import AtmosEncoder
from deezy.audio_encoders.dee.dd import DDEncoderDEE
from deezy.audio_encoders.dee.ddp import DDPEncoderDEE
from deezy.config.defaults import get_default_config_path
from deezy.config.manager import ConfigManager, get_config_manager
from deezy.enums import case_insensitive_enum, enum_choices
from deezy.enums.ac4 import Ac4EncodingProfile
from deezy.enums.atmos import AtmosMode, WarpMode
from deezy.enums.dd import DolbyDigitalChannels
from deezy.enums.ddp import DolbyDigitalPlusChannels
from deezy.enums.ddp_bluray import DolbyDigitalPlusBlurayChannels
from deezy.enums.shared import TrackType
from deezy.enums.shared import DeeDRC, LogLevel, MeteringMode, StereoDownmix
from deezy.info import parse_audio_streams
from deezy.track_info.track_index import TrackIndex
from deezy.utils._version import __version__, program_name
from deezy.utils.dependencies import DependencyNotFoundError, FindDependencies
from deezy.utils.exit import EXIT_FAIL, EXIT_SUCCESS, exit_application
from deezy.utils.file_parser import parse_input_s
from deezy.utils.logger import logger, logger_manager


def create_main_parser() -> argparse.ArgumentParser:
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
        choices=LogLevel,
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


def create_common_argument_groups() -> dict[str, argparse.ArgumentParser]:
    """Create reusable argument groups."""
    # input files argument group
    input_group = argparse.ArgumentParser(add_help=False)
    input_group.add_argument(
        "input", nargs="+", help="Input file paths or directories", metavar="INPUT"
    )

    # common Encode Args
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
        default=TrackIndex(TrackType.AUDIO, 0),
        help="Track to use for encoding. Supports: 'N' (audio track N), 'a:N' (audio track N), 's:N' (stream index N).",
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

    # bitrate group
    bitrate_group = argparse.ArgumentParser(add_help=False)
    bitrate_group.add_argument(
        "--bitrate",
        type=int,
        default=None,
        help=(
            "The bitrate in Kbps (If too high or low for you desired layout, "
            "the bitrate will automatically be adjusted to the closest allowed bitrate)."
        ),
    )

    # DD/DDP/Atmos DRC group (limited choices)
    dd_ddp_atmos_drc_group = argparse.ArgumentParser(add_help=False)
    dd_ddp_atmos_drc_choices = (
        DeeDRC.FILM_STANDARD,
        DeeDRC.FILM_LIGHT,
        DeeDRC.MUSIC_STANDARD,
        DeeDRC.MUSIC_LIGHT,
        DeeDRC.SPEECH,
    )
    dd_ddp_atmos_drc_group.add_argument(
        "--drc-line-mode",
        type=case_insensitive_enum(DeeDRC),
        choices=dd_ddp_atmos_drc_choices,
        metavar=enum_choices(dd_ddp_atmos_drc_choices),
        default=DeeDRC.FILM_LIGHT,
        help="Dynamic range compression settings.",
    )
    dd_ddp_atmos_drc_group.add_argument(
        "--drc-rf-mode",
        type=case_insensitive_enum(DeeDRC),
        choices=dd_ddp_atmos_drc_choices,
        metavar=enum_choices(dd_ddp_atmos_drc_choices),
        default=DeeDRC.FILM_LIGHT,
        help="Dynamic range compression settings.",
    )
    dd_ddp_atmos_drc_group.add_argument(
        "--custom-dialnorm",
        type=dialnorm_options,
        default=0,
        help="Custom dialnorm (0 disables custom dialnorm).",
    )

    # shared loudness arguments (common to all formats)
    loudness_group = argparse.ArgumentParser(add_help=False)
    loudness_group.add_argument(
        "--no-dialogue-intelligence",
        action="store_false",
        help="Dialogue Intelligence enabled. Option ignored for 1770-1 or LeqA metering mode.",
    )
    loudness_group.add_argument(
        "--speech-threshold",
        type=int_0_100,
        default=15,
        help=(
            "[0-100] If the percentage of speech is higher than the threshold, the encoder uses speech "
            "gating to set the dialnorm value. (Otherwise, the encoder uses level gating)."
        ),
    )

    # DD/DDP limited metering mode (excludes MODE_1770_4)
    dd_ddp_metering_group = argparse.ArgumentParser(add_help=False)
    dd_ddp_metering_choices = (
        MeteringMode.MODE_1770_1,
        MeteringMode.MODE_1770_2,
        MeteringMode.MODE_1770_3,
        MeteringMode.MODE_LEQA,
    )
    dd_ddp_metering_group.add_argument(
        "--metering-mode",
        type=case_insensitive_enum(MeteringMode),
        choices=dd_ddp_metering_choices,
        metavar=enum_choices(dd_ddp_metering_choices),
        default=MeteringMode.MODE_1770_3,
        help="Loudness measuring mode according to one of the broadcast standards.",
    )

    # Atmos/AC4 full metering mode (includes MODE_1770_4)
    atmos_ac4_metering_group = argparse.ArgumentParser(add_help=False)
    atmos_ac4_metering_group.add_argument(
        "--metering-mode",
        type=case_insensitive_enum(MeteringMode),
        choices=MeteringMode,
        metavar=enum_choices(MeteringMode),
        default=MeteringMode.MODE_1770_4,
        help="Loudness measuring mode according to one of the broadcast standards.",
    )

    # DD/DDP specific processing options
    dd_ddp_processing_group = argparse.ArgumentParser(add_help=False)
    dd_ddp_processing_group.add_argument(
        "--no-low-pass-filter",
        action="store_false",
        help="Disables low pass filter.",
    )
    dd_ddp_processing_group.add_argument(
        "--no-surround-3db",
        action="store_false",
        help="Disables surround 3db attenuation.",
    )
    dd_ddp_processing_group.add_argument(
        "--no-surround-90-deg-phase-shift",
        action="store_false",
        help="Disables surround 90 degree phase shift.",
    )

    # stereo downmix mode
    stereo_downmix_group = argparse.ArgumentParser(add_help=False)
    stereo_downmix_group.add_argument(
        "--stereo-down-mix",
        type=case_insensitive_enum(StereoDownmix),
        choices=StereoDownmix,
        default=StereoDownmix.LORO,
        metavar=enum_choices(StereoDownmix),
        help="Down mix method for stereo.",
    )

    # downmix metadata levels
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

    # DD channels group
    dd_channels_group = argparse.ArgumentParser(add_help=False)
    dd_channels_group.add_argument(
        "--channels",
        type=case_insensitive_enum(DolbyDigitalChannels),
        choices=DolbyDigitalChannels,
        default=DolbyDigitalChannels.AUTO,
        metavar=enum_choices(DolbyDigitalChannels),
        help="The number of channels.",
    )

    # DDP channels group
    ddp_channels_group = argparse.ArgumentParser(add_help=False)
    ddp_channels_group.add_argument(
        "--channels",
        type=case_insensitive_enum(DolbyDigitalPlusChannels),
        choices=DolbyDigitalPlusChannels,
        default=DolbyDigitalPlusChannels.AUTO,
        metavar=enum_choices(DolbyDigitalPlusChannels),
        help="The number of channels.",
    )

    # DDP BluRay channels group
    ddp_bluray_channels_group = argparse.ArgumentParser(add_help=False)
    ddp_bluray_channels_group.add_argument(
        "--channels",
        type=case_insensitive_enum(DolbyDigitalPlusBlurayChannels),
        choices=DolbyDigitalPlusBlurayChannels,
        default=DolbyDigitalPlusBlurayChannels.SURROUNDEX,
        metavar=enum_choices(DolbyDigitalPlusBlurayChannels),
        help="The number of channels.",
    )

    # atmos specific options
    atmos_options_group = argparse.ArgumentParser(add_help=False)
    atmos_options_group.add_argument(
        "--atmos-mode",
        type=case_insensitive_enum(AtmosMode),
        choices=AtmosMode,
        default=AtmosMode.STREAMING,
        metavar=enum_choices(AtmosMode),
        help="Atmos encoding mode.",
    )

    # trueHDD options (shared by Atmos and AC4)
    truehdd_options_group = argparse.ArgumentParser(add_help=False)
    truehdd_options_group.add_argument(
        "--thd-warp-mode",
        type=case_insensitive_enum(WarpMode),
        choices=WarpMode,
        default=WarpMode.NORMAL,
        metavar=enum_choices(WarpMode),
        help="Specify warp mode when not present in metadata (truehdd).",
    )
    truehdd_options_group.add_argument(
        "--bed-conform",
        action="store_true",
        help="Enables bed conformance for Atmos content (truehd).",
    )

    # AC4 basic options
    ac4_basic_options_group = argparse.ArgumentParser(add_help=False)
    ac4_basic_options_group.add_argument(
        "--ims-legacy-presentation",
        action="store_true",
        help=(
            "Determines whether the Dolby AC-4 encoder inserts an additional "
            "presentation for backward compatibility."
        ),
    )
    ac4_basic_options_group.add_argument(
        "--encoding-profile",
        type=case_insensitive_enum(Ac4EncodingProfile),
        choices=Ac4EncodingProfile,
        metavar=enum_choices(Ac4EncodingProfile),
        default=Ac4EncodingProfile.IMS,
        help="Encoding profile. For encoding music content, select ims_music.",
    )

    # AC4 DRC options (full DeeDRC enum choices)
    ac4_drc_group = argparse.ArgumentParser(add_help=False)
    ac4_drc_args = (
        "--ddp-drc",
        "--flat-panel-drc",
        "--home-theatre-drc",
        "--portable-headphones-drc",
        "--portable-speakers-drc",
    )
    for ac4_drc in ac4_drc_args:
        ac4_drc_group.add_argument(
            ac4_drc,
            type=case_insensitive_enum(DeeDRC),
            choices=DeeDRC,
            metavar=enum_choices(DeeDRC),
            default=DeeDRC.FILM_LIGHT,
            help="Dynamic range compression settings for AC4.",
        )

    # preset metering mode (full choices for flexibility)
    preset_metering_group = argparse.ArgumentParser(add_help=False)
    preset_metering_group.add_argument(
        "--metering-mode",
        type=case_insensitive_enum(MeteringMode),
        choices=MeteringMode,
        metavar=enum_choices(MeteringMode),
        help="Loudness measuring mode according to one of the broadcast standards.",
    )

    # preset override channels (flexible string type)
    preset_channels_group = argparse.ArgumentParser(add_help=False)
    preset_channels_group.add_argument(
        "--channels",
        type=str,
        help="Override channels setting from preset (format depends on preset's format).",
    )

    return {
        "input_group": input_group,
        "encode_group": encode_group,
        "bitrate_group": bitrate_group,
        "dd_ddp_atmos_drc_group": dd_ddp_atmos_drc_group,
        "loudness_group": loudness_group,
        "dd_ddp_metering_group": dd_ddp_metering_group,
        "atmos_ac4_metering_group": atmos_ac4_metering_group,
        "preset_metering_group": preset_metering_group,
        "dd_ddp_processing_group": dd_ddp_processing_group,
        "stereo_downmix_group": stereo_downmix_group,
        "downmix_metadata_group": downmix_metadata_group,
        "dd_channels_group": dd_channels_group,
        "ddp_channels_group": ddp_channels_group,
        "ddp_bluray_channels_group": ddp_bluray_channels_group,
        "atmos_options_group": atmos_options_group,
        "truehdd_options_group": truehdd_options_group,
        "ac4_basic_options_group": ac4_basic_options_group,
        "ac4_drc_group": ac4_drc_group,
        "preset_channels_group": preset_channels_group,
    }


def create_encode_parsers(
    subparsers: argparse._SubParsersAction,
    argument_groups: dict[str, argparse.ArgumentParser],
) -> None:
    """Create encode command parsers."""
    # encode command parser
    encode_parser = subparsers.add_parser("encode", help="Encode management")
    encode_subparsers = encode_parser.add_subparsers(
        dest="format_command", required=True
    )

    ### Dolby Digital Command ###
    _encode_dd_parser = encode_subparsers.add_parser(
        "dd",
        parents=(
            argument_groups["input_group"],
            argument_groups["encode_group"],
            argument_groups["bitrate_group"],
            argument_groups["dd_ddp_atmos_drc_group"],
            argument_groups["loudness_group"],
            argument_groups["dd_ddp_metering_group"],
            argument_groups["dd_ddp_processing_group"],
            argument_groups["stereo_downmix_group"],
            argument_groups["downmix_metadata_group"],
            argument_groups["dd_channels_group"],
        ),
        formatter_class=lambda prog: CustomHelpFormatter(
            prog,
            width=78,
            max_help_position=7,
        ),
    )

    ### Dolby Digital Plus Command ###
    _encode_ddp_parser = encode_subparsers.add_parser(
        "ddp",
        parents=(
            argument_groups["input_group"],
            argument_groups["encode_group"],
            argument_groups["bitrate_group"],
            argument_groups["dd_ddp_atmos_drc_group"],
            argument_groups["loudness_group"],
            argument_groups["dd_ddp_metering_group"],
            argument_groups["dd_ddp_processing_group"],
            argument_groups["stereo_downmix_group"],
            argument_groups["downmix_metadata_group"],
            argument_groups["ddp_channels_group"],
        ),
        formatter_class=lambda prog: CustomHelpFormatter(
            prog,
            width=78,
            max_help_position=7,
        ),
    )

    ### Dolby Digital Plus BluRay Command ###
    _encode_ddp_bluray_parser = encode_subparsers.add_parser(
        "ddp-bluray",
        parents=(
            argument_groups["input_group"],
            argument_groups["encode_group"],
            argument_groups["bitrate_group"],
            argument_groups["dd_ddp_atmos_drc_group"],
            argument_groups["loudness_group"],
            argument_groups["dd_ddp_metering_group"],
            argument_groups["dd_ddp_processing_group"],
            argument_groups["stereo_downmix_group"],
            argument_groups["downmix_metadata_group"],
            argument_groups["ddp_bluray_channels_group"],
        ),
        formatter_class=lambda prog: CustomHelpFormatter(
            prog,
            width=78,
            max_help_position=7,
        ),
    )

    ### Atmos Command ###
    _encode_atmos_parser = encode_subparsers.add_parser(
        "atmos",
        parents=(
            argument_groups["input_group"],
            argument_groups["encode_group"],
            argument_groups["bitrate_group"],
            argument_groups["dd_ddp_atmos_drc_group"],
            argument_groups["loudness_group"],
            argument_groups["atmos_ac4_metering_group"],
            argument_groups["downmix_metadata_group"],
            argument_groups["stereo_downmix_group"],
            argument_groups["atmos_options_group"],
            argument_groups["truehdd_options_group"],
        ),
        formatter_class=lambda prog: CustomHelpFormatter(
            prog,
            width=78,
            max_help_position=7,
        ),
    )

    ### AC4 Command ###
    _encode_ac4_parser = encode_subparsers.add_parser(
        "ac4",
        parents=(
            argument_groups["input_group"],
            argument_groups["encode_group"],
            argument_groups["bitrate_group"],
            argument_groups["loudness_group"],
            argument_groups["atmos_ac4_metering_group"],
            argument_groups["ac4_basic_options_group"],
            argument_groups["ac4_drc_group"],
            argument_groups["truehdd_options_group"],
        ),
        formatter_class=lambda prog: CustomHelpFormatter(
            prog,
            width=78,
            max_help_position=7,
        ),
    )

    ### Preset Command ###
    encode_preset_parser = encode_subparsers.add_parser(
        "preset",
        parents=(
            argument_groups["input_group"],
            argument_groups["encode_group"],
            argument_groups["bitrate_group"],
            argument_groups["dd_ddp_atmos_drc_group"],
            argument_groups["loudness_group"],
            argument_groups["preset_metering_group"],
            argument_groups["dd_ddp_processing_group"],
            argument_groups["stereo_downmix_group"],
            argument_groups["downmix_metadata_group"],
            argument_groups["preset_channels_group"],
            argument_groups["atmos_options_group"],
            argument_groups["truehdd_options_group"],
            argument_groups["ac4_basic_options_group"],
            argument_groups["ac4_drc_group"],
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


def create_other_parsers(
    subparsers: argparse._SubParsersAction,
    argument_groups: dict[str, argparse.ArgumentParser],
) -> None:
    """Create find, info, and config command parsers."""
    # find command parser
    find_parser = subparsers.add_parser(
        "find", parents=[argument_groups["input_group"]], help="Find management"
    )
    find_parser.add_argument(
        "-n",
        "--name",
        action="store_true",
        help="Only display names instead of full paths.",
    )

    # info command parser
    _info_parser = subparsers.add_parser(
        "info", parents=[argument_groups["input_group"]], help="Info management"
    )

    # config command parser
    config_parser = subparsers.add_parser("config", help="Configuration management")
    config_subparsers = config_parser.add_subparsers(
        dest="config_command", required=True
    )

    # generate config subcommand
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

    # temp management command parser
    temp_parser = subparsers.add_parser("temp", help="Temporary folder management")
    temp_subparsers = temp_parser.add_subparsers(dest="temp_command", required=True)

    # clean temp subcommand
    clean_parser = temp_subparsers.add_parser("clean", help="Clean DeeZy temp folders")
    clean_parser.add_argument(
        "--max-age",
        type=int,
        default=24,
        help="Remove folders older than N hours (default: 24)",
        metavar="HOURS",
    )
    clean_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without actually deleting",
    )
    # info temp subcommand
    temp_subparsers.add_parser("info", help="Show temp folder information")


def apply_default_bitrate(
    args: argparse.Namespace, config_manager: ConfigManager | None
) -> None:
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
        if config_manager is not None:
            default_bitrate = config_manager.get_default_bitrate(
                args.format_command, channels_or_mode
            )

            if default_bitrate:
                args.bitrate = default_bitrate
                logger.debug(
                    f"No bitrate specified, using default {default_bitrate}k for {args.format_command}"
                )


def handle_preset_injection() -> None:
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


def cli_parser(base_wd: Path) -> None:
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
    args: argparse.Namespace, base_wd: Path, config_manager: ConfigManager | None
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
            base_wd,
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

    # parse all possible file inputs
    file_inputs = parse_input_s(args.input)
    if not file_inputs and args.sub_command in ("find", "info", "encode"):
        exit_application("No input files were found.", EXIT_FAIL)

    return file_inputs


def execute_command(
    args: argparse.Namespace,
    file_inputs: list[Path],
    dependencies: dict[str, Path | None] | None,
    config_manager: ConfigManager | None,
) -> None:
    """Execute the appropriate command based on parsed arguments."""
    if args.sub_command == "encode":
        if dependencies is None:
            exit_application("Dependencies not found for encoding.", EXIT_FAIL)
        execute_encode_command(args, file_inputs, dependencies)
    elif args.sub_command == "find":
        execute_find_command(args, file_inputs)
    elif args.sub_command == "info":
        execute_info_command(args, file_inputs)
    elif args.sub_command == "config":
        execute_config_command(args, config_manager)
    elif args.sub_command == "temp":
        execute_temp_command(args)


def execute_encode_command(
    args: argparse.Namespace,
    file_inputs: list[Path],
    dependencies: dict[str, Path | None],
) -> None:
    """Execute encoding commands."""
    ffmpeg_path = dependencies["ffmpeg_path"]
    truehdd_path = dependencies["truehdd_path"]
    dee_path = dependencies["dee_path"]

    # assert required paths are not None
    assert ffmpeg_path is not None, "ffmpeg_path is required for encoding"
    assert dee_path is not None, "dee_path is required for encoding"

    try:
        for input_file in file_inputs:
            # update logger to write to file if needed
            if getattr(args, "log_to_file", False):
                logger_manager.set_file(input_file.with_suffix(".log"))

            # build payload based on format
            if args.format_command == "dd":
                payload = PayloadBuilder.build_dd_payload(
                    args, input_file, ffmpeg_path, truehdd_path, dee_path
                )
                result = DDEncoderDEE(payload).encode()
            elif args.format_command in ("ddp", "ddp-bluray"):
                payload = PayloadBuilder.build_ddp_payload(
                    args, input_file, ffmpeg_path, truehdd_path, dee_path
                )
                result = DDPEncoderDEE(payload).encode()
            elif args.format_command == "atmos":
                payload = PayloadBuilder.build_atmos_payload(
                    args, input_file, ffmpeg_path, truehdd_path, dee_path
                )
                result = AtmosEncoder(payload).encode()
            elif args.format_command == "ac4":
                payload = PayloadBuilder.build_ac4_payload(
                    args, input_file, ffmpeg_path, truehdd_path, dee_path
                )
                result = Ac4Encoder(payload).encode()
            elif args.format_command == "preset":
                # this should not happen since config manager converts "preset" to actual format
                exit_application(
                    "Preset format conversion failed. This is a bug in the configuration system.",
                    EXIT_FAIL,
                )
            else:
                exit_application(f"Unknown format: {args.format_command}", EXIT_FAIL)

            logger.info(f"Job successful! Output file path:\n{result}")

    except Exception as e:
        logger.debug(traceback.format_exc())
        exit_application(str(e), EXIT_FAIL)


def execute_find_command(args: argparse.Namespace, file_inputs: list[Path]) -> None:
    """Execute find command."""
    file_names = []
    for input_file in file_inputs:
        # if name only is used, print only the name of the file.
        if args.name:
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


def execute_config_command(
    args: argparse.Namespace, config_manager: ConfigManager | None
) -> None:
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


def execute_temp_command(args: argparse.Namespace) -> None:
    """Execute temp management commands."""
    if args.temp_command == "clean":
        removed_count, size_mb = clean_deezy_temp_folders(
            max_age_hours=args.max_age, dry_run=args.dry_run
        )

        if args.dry_run:
            if removed_count == 0:
                exit_application("No temp folders to clean.", EXIT_SUCCESS)
            else:
                exit_application(
                    f"Would remove {removed_count} folders ({size_mb:.1f} MB)",
                    EXIT_SUCCESS,
                )
        else:
            if removed_count == 0:
                exit_application("No temp folders to clean.", EXIT_SUCCESS)
            else:
                exit_application(
                    f"Removed {removed_count} temp folders ({size_mb:.1f} MB)",
                    EXIT_SUCCESS,
                )

    elif args.temp_command == "info":
        deezy_temp_base, job_folders, total_size_mb = get_deezy_temp_info()

        if not job_folders:
            exit_application("No DeeZy temp folders found.", EXIT_SUCCESS)

        message = f"DeeZy temp folder: {deezy_temp_base}\n"
        message += f"Job folders: {len(job_folders)}\n"
        message += f"Total size: {total_size_mb:.1f} MB"

        exit_application(message, EXIT_SUCCESS)
