import argparse
import copy
import sys
import tempfile
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from deezy.audio_encoders.dee.ac4 import Ac4Encoder
from deezy.audio_encoders.dee.atmos import AtmosEncoder
from deezy.audio_encoders.dee.base import BaseDeeAudioEncoder
from deezy.audio_encoders.dee.dd import DDEncoderDEE
from deezy.audio_encoders.dee.ddp import DDPEncoderDEE
from deezy.cli.payload_factory import PayloadBuilder
from deezy.cli.utils import (
    CustomHelpFormatter,
    apply_config_defaults_to_args,
    apply_default_bitrate,
    clean_deezy_temp_folders,
    dialnorm_options,
    execute_find_command,
    execute_info_command,
    get_deezy_temp_info,
    handle_configuration,
    handle_dependencies,
    handle_file_inputs,
    handle_preset_injection,
    int_0_100,
    setup_logging,
    validate_track_index,
)
from deezy.config.defaults import get_default_config_path
from deezy.config.manager import ConfigManager, get_config_manager
from deezy.enums import case_insensitive_enum, enum_choices
from deezy.enums.ac4 import Ac4EncodingProfile
from deezy.enums.atmos import AtmosMode, WarpMode
from deezy.enums.dd import DolbyDigitalChannels
from deezy.enums.ddp import DolbyDigitalPlusChannels
from deezy.enums.ddp_bluray import DolbyDigitalPlusBlurayChannels
from deezy.enums.shared import (
    DeeDRC,
    LogLevel,
    MeteringMode,
    StereoDownmix,
    TrackType,
)
from deezy.exceptions import OutputExistsError
from deezy.track_info.track_index import TrackIndex
from deezy.utils.batch_results import BatchResultsManager
from deezy.utils.exit import EXIT_FAIL, EXIT_SUCCESS, exit_application
from deezy.utils.logger import logger, logger_manager
from deezy.utils.utils import WORKING_DIRECTORY

__version__ = "1.3.13"
program_name = "DeeZy"


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
    # NOTE: DEPRECATED: REMOVE <= 1.4.0
    encode_group.add_argument(
        "--parse-elementary-delay",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    encode_group.add_argument(
        "--keep-temp",
        action="store_true",
        help="Keeps the temp files after finishing.",
    )
    encode_group.add_argument(
        "--reuse-temp-files",
        action="store_true",
        help=(
            "Attempt to reuse already-extracted temp files adjacent to the input file when "
            "the extractor command is identical. This implies --keep-temp."
        ),
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
    encode_group.add_argument(
        "--output-template",
        type=str,
        help=(
            "Optional lightweight template to control auto-generated output filenames. "
            "Supported tokens: {title},{year},{stem},{stem-cleaned},{source},{lang},{channels},"
            "{worker},{delay},{opt-delay}."
        ),
    )
    encode_group.add_argument(
        "--output-preview",
        action="store_true",
        help=(
            "When set, render and show template-based filenames but do not write outputs. "
            "Useful to validate templates before running batch jobs."
        ),
    )
    encode_group.add_argument(
        "--max-parallel",
        type=int,
        default=1,
        help="Maximum number of files to process in parallel (default: 1).",
    )
    encode_group.add_argument(
        "--jitter-ms",
        type=int,
        default=0,
        help=(
            "Maximum random jitter in milliseconds to apply before heavy phases (FFmpeg/DEE/truehdd). "
            "Helps avoid synchronization spikes when running parallel jobs. Default 0 (disabled)."
        ),
    )
    encode_group.add_argument(
        "--max-logs",
        type=int,
        default=None,
        help=(
            "Maximum number of log files to keep in the working logs directory for this run. "
            "Overrides config value if provided. Use 0 to keep none."
        ),
        metavar="N",
    )
    encode_group.add_argument(
        "--max-batch-results",
        type=int,
        default=None,
        help=(
            "Maximum number of batch-results JSON files to keep in the working batch-results directory for this run. "
            "Overrides config value if provided. Use 0 to keep none."
        ),
        metavar="N",
    )
    encode_group.add_argument(
        "--working-dir",
        type=str,
        help=(
            "Directory to use for DeeZy working files (logs and batch-results). "
            "Overrides config/default. If not set, uses the workspace beside the executable."
        ),
    )
    encode_group.add_argument(
        "--batch-summary-output",
        action="store_true",
        help=(
            "Enable batch processing results summary (JSON format). "
            "Results will be saved to a 'batch-results' folder next to the executable by default."
        ),
    )
    encode_group.add_argument(
        "--batch-output-dir",
        type=str,
        help=(
            "When used with --batch-summary-output, place all encoded outputs into this directory "
            "instead of writing them next to the input files."
        ),
    )
    encode_group.add_argument(
        "--overwrite",
        action="store_true",
        help=("Overwrite existing output files instead of failing."),
    )

    # per-phase concurrency limits
    encode_group.add_argument(
        "--limit-ffmpeg",
        type=int,
        default=None,
        help=(
            "Optional limit for concurrent FFmpeg processing. Defaults to --max-parallel if not set. "
            "If set higher than --max-parallel the value will be capped to --max-parallel and a warning will be emitted."
        ),
    )
    encode_group.add_argument(
        "--limit-dee",
        type=int,
        default=None,
        help=(
            "Optional limit for concurrent DEE processing. Defaults to --max-parallel if not set. "
            "If set higher than --max-parallel the value will be capped to --max-parallel and a warning will be emitted."
        ),
    )
    encode_group.add_argument(
        "--limit-truehdd",
        type=int,
        default=None,
        help=(
            "Optional limit for concurrent truehdd processing. Defaults to --max-parallel if not set. "
            "If set higher than --max-parallel the value will be capped to --max-parallel and a warning will be emitted."
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
        help="Dialogue Intelligence disabled. Option ignored for 1770-1 or LeqA metering mode.",
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
    dd_ddp_processing_group.add_argument(
        "--upmix-50-to-51",
        action="store_true",
        help="Up-mix rare 5.0 layouts into 5.1 layouts by adding a silent LFE channel.",
    )

    # DDP BluRay processing group: same as DD/DDP processing but without the
    # --upmix-50-to-51 option because up-mixing to 5.1 is only meaningful for
    # standard DD/DDP workflows.
    ddp_bluray_processing_group = argparse.ArgumentParser(add_help=False)
    ddp_bluray_processing_group.add_argument(
        "--no-low-pass-filter",
        action="store_false",
        help="Disables low pass filter.",
    )
    ddp_bluray_processing_group.add_argument(
        "--no-surround-3db",
        action="store_false",
        help="Disables surround 3db attenuation.",
    )
    ddp_bluray_processing_group.add_argument(
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
        "ddp_bluray_processing_group": ddp_bluray_processing_group,
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
            argument_groups["ddp_bluray_processing_group"],
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


def cli_parser() -> None:
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
        # check for deprecated commands
        # NOTE: DEPRECATED: REMOVE <= 1.4.0
        if args.parse_elementary_delay:
            logger.warning(
                f"Argument '--parse-elementary-delay' is deprecated and will be removed in 1.4.0. "
                "This is no longer needed and everything is handled automatically."
            )
    dependencies = handle_dependencies(args, config_manager)
    file_inputs = handle_file_inputs(args)

    # execute the appropriate command
    execute_command(args, file_inputs, dependencies, config_manager)


# config->args helper moved to cli.utils.apply_config_defaults_to_args


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
        execute_encode_command(args, file_inputs, dependencies, config_manager)
    elif args.sub_command == "find":
        execute_find_command(args, file_inputs)
    elif args.sub_command == "info":
        execute_info_command(args, file_inputs)
    elif args.sub_command == "config":
        execute_config_command(args, config_manager)
    elif args.sub_command == "temp":
        execute_temp_command(args)


def encode_single_file(
    args: argparse.Namespace,
    input_file: Path,
    dependencies: dict[str, Path | None],
    worker_num: int | None = None,
    short_filename: str | None = None,
    file_id: str | None = None,
) -> tuple[Path, Path]:
    """
    Encode a single file and return the input file and result path.

    Args:
        args: Command line arguments
        input_file: Path to the input file
        dependencies: Dictionary of tool dependencies
        worker_num: Worker number for parallel processing (None for single processing)
        short_filename: Short filename for worker prefix display
        file_id: Unique file identifier for output naming (prevents overwrites)

    Returns:
        Tuple of (input_file, result_path)
    """
    ffmpeg_path = dependencies["ffmpeg_path"]
    truehdd_path = dependencies["truehdd_path"]
    dee_path = dependencies["dee_path"]

    # assert required paths are not None
    assert ffmpeg_path is not None, "ffmpeg_path is required for encoding"
    assert dee_path is not None, "dee_path is required for encoding"

    # set worker prefix for logger system
    if worker_num is not None and short_filename is not None:
        worker_prefix = f"Worker {worker_num} ({short_filename})"
        logger.info(f"Worker {worker_num} started processing: {input_file.name}")
    elif worker_num is not None:
        worker_prefix = f"Worker {worker_num}"
        logger.info(f"Worker {worker_num} started processing: {input_file.name}")
    else:
        worker_prefix = None
    logger_manager.set_worker_prefix(worker_prefix)

    # Force no progress bars for parallel processing to avoid Rich conflicts.
    # Rich progress bars don't work well with multiple concurrent instances.
    if worker_num is not None:
        # create a copy of args to avoid modifying the shared args object
        args = copy.deepcopy(args)
        args.no_progress_bars = True
        # set file_id for unique output filename generation (prevents overwrites)
        args.worker_id = file_id if file_id else f"w{worker_num}"
    else:
        # for sequential runs, if a file_id is supplied set it on args so payloads will pick it up
        if file_id:
            # it's fine to set on the shared args for sequential processing
            args.worker_id = file_id

    # update logger to write to file if needed
    if args.log_to_file:
        # place logs in centralized logs directory
        log_name = f"{input_file.stem}"
        if worker_num is not None:
            log_name = f"{log_name}.worker{worker_num}"
        # prefer computed working dir stored on args (set by execute_encode_command)
        work_dir_for_logs = Path(
            getattr(args, "_working_dir", WORKING_DIRECTORY / "deezy_work")
        )
        log_file = work_dir_for_logs / "logs" / f"{log_name}.log"
        logger_manager.set_file(log_file)

    # build payload and run encoder
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
        raise ValueError(
            "Preset format conversion failed. This is a bug in the configuration system."
        )
    else:
        raise ValueError(f"Unknown format: {args.format_command}")

    # log completion message for parallel processing
    if worker_num is not None:
        logger.info(f"Worker {worker_num} completed: {input_file.name} → {result.name}")

    return input_file, result


def execute_encode_command(
    args: argparse.Namespace,
    file_inputs: list[Path],
    dependencies: dict[str, Path | None],
    config_manager: ConfigManager | None,
) -> None:
    """Execute encoding commands."""
    max_parallel = getattr(args, "max_parallel", 1)
    batch_output_enabled = getattr(args, "batch_summary_output", False)

    # get temp_dir from config if exists (CLI arg > config default > automatic)
    temp_dir_arg = getattr(args, "temp_dir", None)
    config_temp_dir = None
    if config_manager is not None:
        config_temp_dir = config_manager.get_config_default("temp_dir")

    temp_dir = None
    if temp_dir_arg:
        temp_dir = Path(temp_dir_arg)
    elif config_temp_dir:
        temp_dir = Path(config_temp_dir)
    if temp_dir:
        try:
            temp_dir.mkdir(parents=True, exist_ok=True)
            setattr(args, "temp_dir", str(temp_dir))
        except Exception as temp_dir_e:
            logger.warning(
                f"Failed to create temp directory at {temp_dir} ({temp_dir_e})."
            )

    # centralized work directories: precedence CLI arg > config default > WORKING_DIRECTORY/deezy_work
    working_dir_arg = getattr(args, "working_dir", None)
    config_working_dir = None
    if config_manager is not None:
        config_working_dir = config_manager.get_config_default("working_dir")

    if working_dir_arg:
        work_dir = Path(working_dir_arg)
    elif config_working_dir:
        work_dir = Path(config_working_dir)
    else:
        work_dir = WORKING_DIRECTORY / "deezy_work"

    logs_dir = work_dir / "logs"
    batch_results_dir = work_dir / "batch-results"
    # ensure dirs exist when needed
    if not work_dir.exists():
        work_dir.mkdir(parents=True, exist_ok=True)
    if not logs_dir.exists():
        logs_dir.mkdir(parents=True, exist_ok=True)
    if not batch_results_dir.exists():
        batch_results_dir.mkdir(parents=True, exist_ok=True)

    # Trim old logs and batch-results based on config limits (config-only)
    # Determine trimming limits with precedence: CLI args > config defaults > None
    try:
        cli_max_logs = getattr(args, "max_logs", None)
        if cli_max_logs is not None:
            if int(cli_max_logs) < 0:
                exit_application("--max-logs must be >= 0", EXIT_FAIL)
            max_logs = int(cli_max_logs)
        else:
            max_logs = (
                int(config_manager.get_config_default("max_logs"))
                if config_manager
                else None
            )
    except Exception:
        max_logs = None

    try:
        cli_max_batch_results = getattr(args, "max_batch_results", None)
        if cli_max_batch_results is not None:
            if int(cli_max_batch_results) < 0:
                exit_application("--max-batch-results must be >= 0", EXIT_FAIL)
            max_batch_results = int(cli_max_batch_results)
        else:
            max_batch_results = (
                int(config_manager.get_config_default("max_batch_results"))
                if config_manager
                else None
            )
    except Exception:
        max_batch_results = None

    def _trim_dir(
        dir_path: Path, max_items: int | None, glob_pattern: str = "*"
    ) -> None:
        if max_items is None:
            return
        try:
            items = sorted(
                list(dir_path.glob(glob_pattern)), key=lambda p: p.stat().st_mtime
            )
            # if there are more files than max_items, delete the oldest
            while len(items) > max_items:
                oldest = items.pop(0)
                try:
                    if oldest.is_file():
                        oldest.unlink()
                    elif oldest.is_dir():
                        import shutil

                        shutil.rmtree(oldest)
                except Exception:
                    # ignore deletion errors; we don't want to abort processing for cleanup failures
                    pass
        except Exception:
            # ignore trimming errors
            pass

    _trim_dir(logs_dir, max_logs, glob_pattern="*.log")
    _trim_dir(batch_results_dir, max_batch_results, glob_pattern="*.json")

    # store computed work_dir on args so encode_single_file can find it
    setattr(args, "_working_dir", str(work_dir))

    # Apply config defaults into args and resolve per-phase limits once so both
    # sequential and parallel paths behave identically. Returns resolved
    # per-phase limits (None means inherit max_parallel).
    ff_limit, de_limit, th_limit = apply_config_defaults_to_args(args, config_manager)

    # determine if we should use worker prefixes
    # use prefixes only if there are multiple files AND max_parallel > 1
    use_worker_prefixes = len(file_inputs) > 1 and max_parallel > 1

    # track processing results
    successful_files = []
    failed_files = []

    # initialize batch results manager if batch output is enabled
    batch_manager = None
    if batch_output_enabled:
        # get original command line args (excluding script name)
        command_args = sys.argv[1:]

        # use centralized batch-results dir
        batch_manager = BatchResultsManager(
            command_args=command_args,
            total_files=len(file_inputs),
            max_parallel=max_parallel,
            output_dir=batch_results_dir,
        )

    # if the user provided a batch-output-dir, prepare it early (fail fast / create dir)
    batch_out_arg = getattr(args, "batch_output_dir", None)
    batch_out_dir: Path | None = None
    # If the user didn't provide a CLI batch_output_dir but the config has one,
    # use the config value so encoders and payloads see the same default.
    if batch_output_enabled and not batch_out_arg and config_manager is not None:
        try:
            cfg_bod = config_manager.get_config_default("batch_output_dir")
            if cfg_bod:
                batch_out_arg = cfg_bod
                # propagate back onto args so PayloadBuilder will include it
                setattr(args, "batch_output_dir", cfg_bod)
        except Exception:
            # ignore config lookup errors and proceed without batch output dir
            batch_out_arg = None

    if batch_output_enabled and batch_out_arg:
        # Fail fast: if the user asked for a batch output directory, ensure it exists
        # and is writable. If we cannot prepare it, stop immediately instead of
        # continuing and surprising the user later.
        batch_out_dir = Path(batch_out_arg)
        try:
            batch_out_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.error(f"Could not prepare batch output dir '{batch_out_arg}': {e}")
            exit_application(
                f"Could not prepare batch output dir '{batch_out_arg}': {e}", EXIT_FAIL
            )

        # verify the path is a directory
        if not batch_out_dir.exists() or not batch_out_dir.is_dir():
            logger.error(f"Batch output path '{batch_out_dir}' is not a directory.")
            exit_application(
                f"Batch output path '{batch_out_dir}' is not a directory.", EXIT_FAIL
            )

        # quick writability test: create and remove a small temp file in the dir
        try:
            tf = tempfile.NamedTemporaryFile(
                prefix=".deezy_write_test_", dir=str(batch_out_dir), delete=False
            )
            try:
                tf.write(b"deezetest")
                tf.flush()
            finally:
                tf.close()
            Path(tf.name).unlink()
        except Exception as e:
            logger.error(f"Batch output dir '{batch_out_dir}' is not writable: {e}")
            exit_application(
                f"Batch output dir '{batch_out_dir}' is not writable: {e}", EXIT_FAIL
            )

    try:
        if max_parallel == 1 or len(file_inputs) == 1:
            # sequential processing
            for i, input_file in enumerate(file_inputs):
                # create batch result if tracking is enabled
                batch_result = None
                if batch_manager:
                    file_id = f"f{i + 1}" if len(file_inputs) > 1 else "f1"
                    # compute centralized log file path used for this input
                    log_name = f"{input_file.stem}"
                    log_file = work_dir / "logs" / f"{log_name}.log"
                    batch_result = batch_manager.create_result(
                        input_file, file_id, log_file=log_file
                    )

                try:
                    # pass a file-specific id so encode_single_file can include it in output names
                    file_id = f"f{i + 1}" if len(file_inputs) > 1 else "f1"

                    # prepare per-job args copy; encoders are authoritative for filename
                    args_for_job = copy.deepcopy(args)

                    input_file, result = encode_single_file(
                        args_for_job, input_file, dependencies, None, None, file_id
                    )
                    # When running in output-preview mode we already emit the
                    # previewed path from the encoder; suppress the duplicate
                    # "Job successful" path line to avoid confusion.
                    if not getattr(args, "output_preview", False):
                        logger.info(f"Job successful! Output file path:\n{result}")
                    successful_files.append((input_file, result))

                    if batch_result:
                        batch_result.mark_success(result)
                except Exception as e:
                    # handle output-exists as a skipped file
                    if isinstance(e, OutputExistsError):
                        logger.info(f"Skipping {input_file.name}: {e}")
                        if batch_result:
                            batch_result.mark_skipped(str(e))
                    else:
                        logger.error(f"Failed to process {input_file}: {e}")
                        logger.debug(traceback.format_exc())
                        failed_files.append((input_file, str(e)))

                        if batch_result:
                            batch_result.mark_failure(str(e))
                    # continue with next file instead of exiting

        # parallel processing
        else:
            with ThreadPoolExecutor(max_workers=max_parallel) as executor:
                # Initialize phase semaphores and jitter in the encoder base so
                # all encoder instances share phase limits.
                BaseDeeAudioEncoder.init_phase_limits(
                    max_parallel,
                    args.jitter_ms,
                    ffmpeg_limit=ff_limit,
                    dee_limit=de_limit,
                    truehdd_limit=th_limit,
                )

                # submit all jobs and create batch results
                future_to_file = {}
                future_to_batch_result = {}

                for i, input_file in enumerate(file_inputs):
                    worker_num = (i % max_parallel) + 1 if use_worker_prefixes else None
                    # use file index for unique output naming
                    file_id = f"f{i + 1}" if use_worker_prefixes else f"f{i + 1}"
                    # use stem (filename without extension) for cleaner display
                    short_filename = input_file.stem if use_worker_prefixes else None

                    # create batch result if tracking is enabled
                    batch_result = None
                    if batch_manager:
                        actual_file_id = file_id or f"f{i + 1}"
                        # compute centralized log file path used for this input
                        log_name = f"{input_file.stem}"
                        if worker_num is not None:
                            log_name = f"{log_name}.worker{worker_num}"
                        log_file = work_dir / "logs" / f"{log_name}.log"
                        batch_result = batch_manager.create_result(
                            input_file, actual_file_id, log_file=log_file
                        )

                    # prepare per-job args copy; encoders handle final filename and
                    # overwrite decisions to ensure accuracy with mediainfo parsing.
                    args_for_job = copy.deepcopy(args)
                    future = executor.submit(
                        encode_single_file,
                        args_for_job,
                        input_file,
                        dependencies,
                        worker_num,
                        short_filename,
                        file_id,
                    )

                    future_to_file[future] = input_file
                    if batch_result:
                        future_to_batch_result[future] = batch_result

                # process completed jobs
                for future in as_completed(future_to_file):
                    input_file = future_to_file[future]
                    batch_result = (
                        future_to_batch_result.get(future) if batch_manager else None
                    )

                    try:
                        _original_file, result = future.result()
                        # When running in output-preview mode we already emit the
                        # previewed path from the encoder; suppress the duplicate
                        # "Job successful" path line to avoid confusion.
                        if not getattr(args, "output_preview", False):
                            logger.info(f"Job successful! Output file path:\n{result}")
                        successful_files.append((input_file, result))

                        if batch_result:
                            batch_result.mark_success(result)
                    except Exception as e:
                        if isinstance(e, OutputExistsError):
                            logger.info(f"Skipping {input_file.name}: {e}")
                            if batch_result:
                                batch_result.mark_skipped(str(e))
                        else:
                            logger.error(f"Failed to process {input_file}: {e}")
                            logger.debug(traceback.format_exc())
                            failed_files.append((input_file, str(e)))

                            if batch_result:
                                batch_result.mark_failure(str(e))
                        # continue processing other files instead of raising

        # summary of results
        total_files = len(file_inputs)
        if total_files > 1:
            logger.info("\n=== Processing Complete ===")
            logger.info(f"Total files: {total_files}")
            logger.info(f"Successful: {len(successful_files)}")
            logger.info(f"Failed: {len(failed_files)}")

            if failed_files:
                logger.info("\nFailed files:")
                for failed_file, error in failed_files:
                    logger.info(f"  • {failed_file.name}: {error}")

            if successful_files:
                logger.info("\nSuccessful files:")
                for successful_file, result in successful_files:
                    logger.info(f"  • {successful_file.name} → {result.name}")

        # save batch results if enabled
        if batch_manager:
            try:
                batch_file = batch_manager.save_results()
                logger.info(f"\nBatch results saved to: {batch_file}")
            except Exception as e:
                logger.warning(f"Failed to save batch results: {e}")

        # exit with appropriate code
        if failed_files and not successful_files:
            # all files failed
            exit_application("All files failed to process.", EXIT_FAIL)
        elif failed_files:
            # some files failed
            exit_application(
                f"Processing completed with {len(failed_files)} failures.", EXIT_FAIL
            )
        # else: all successful, continue to normal exit

    except KeyboardInterrupt:
        # mark any in-progress batch results as failed
        if batch_manager:
            for result in batch_manager.results:
                if result.status == "processing":
                    result.mark_failure("Interrupted by user")
            try:
                batch_file = batch_manager.save_results()
                logger.info(f"\nBatch results saved to: {batch_file}")
            except Exception:
                # don't fail on batch save during interrupt
                pass

        logger.info("\nProcessing interrupted by user.")
        exit_application("Processing was interrupted.", EXIT_FAIL)
    except Exception as e:
        # mark any in-progress batch results as failed
        if batch_manager:
            for result in batch_manager.results:
                if result.status == "processing":
                    result.mark_failure(f"Unexpected error: {e}")
            try:
                batch_file = batch_manager.save_results()
                logger.info(f"\nBatch results saved to: {batch_file}")
            except Exception:
                # don't fail on batch save during error
                pass

        # only catch unexpected errors here
        logger.debug(traceback.format_exc())
        exit_application(f"Unexpected error: {e}", EXIT_FAIL)


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
