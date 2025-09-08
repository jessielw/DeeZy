import argparse
from pathlib import Path
from pprint import pprint

from cli.utils import (
    CustomHelpFormatter,
    dialnorm_options,
    int_0_100,
    validate_track_index,
)
from deezy.audio_encoders.dee.dd import DDEncoderDEE
from deezy.audio_encoders.dee.ddp import DDPEncoderDEE
from deezy.config import get_config_integration
from deezy.enums import case_insensitive_enum, enum_choices
from deezy.enums.dd import DolbyDigitalChannels
from deezy.enums.ddp import DolbyDigitalPlusChannels
from deezy.enums.shared import DeeDRC, LogLevel, MeteringMode, StereoDownmix
from deezy.info import parse_audio_streams
from deezy.payloads.dd import DDPayload
from deezy.payloads.ddp import DDPPayload
from deezy.utils._version import __version__, program_name
from deezy.utils.dependencies import DependencyNotFoundError, FindDependencies
from deezy.utils.exit import EXIT_FAIL, EXIT_SUCCESS, exit_application
from deezy.utils.file_parser import parse_input_s
from deezy.utils.logger import logger_manager, logger


def cli_parser(base_wd: Path):
    # Top-level parser
    parser = argparse.ArgumentParser(prog=program_name)
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
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

    # Sub-command parser
    subparsers = parser.add_subparsers(dest="sub_command")

    #############################################################
    ### Common args (re-used across one or more sub commands) ###
    #############################################################
    # Input files argument group
    input_group = argparse.ArgumentParser(add_help=False)
    input_group.add_argument(
        "input", nargs="+", help="Input file paths or directories", metavar="INPUT"
    )

    #############################################################
    ###################### Encode Command #######################
    #############################################################
    # Encode command parser
    encode_parser = subparsers.add_parser("encode")
    encode_subparsers = encode_parser.add_subparsers(
        dest="format_command", required=True
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
    encode_group.add_argument(
        "--preset",
        type=str,
        help="Use a predefined configuration preset from config file.",
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

    # down mixing metadata
    downmix_metadata_group = argparse.ArgumentParser(add_help=False)
    downmix_metadata_group.add_argument(
        "--stereo-down-mix",
        type=case_insensitive_enum(StereoDownmix),
        choices=tuple(StereoDownmix),
        default=StereoDownmix.LORO,
        metavar=enum_choices(StereoDownmix),
        help="Down mix method for stereo.",
    )
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

    ### Dolby Digital Command ###
    encode_dd_parser = encode_subparsers.add_parser(
        "dd",
        parents=(
            input_group,
            encode_group,
            codec_group,
            shared_loudness_args,
            dd_ddp_only_group,
            downmix_metadata_group,
        ),
        formatter_class=lambda prog: CustomHelpFormatter(
            prog,
            width=78,
            max_help_position=3,
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
    encode_dd_parser.add_argument(
        "--metering-mode",
        type=case_insensitive_enum(MeteringMode),
        choices=tuple(MeteringMode),
        metavar=enum_choices(MeteringMode),
        default=MeteringMode.MODE_1770_3,
        help="Loudness measuring mode according to one of the broadcast standards.",
    )

    ### Dolby Digital Plus Command ###
    encode_ddp_parser = encode_subparsers.add_parser(
        "ddp",
        # parents=[input_group, encode_group, downmix_group],
        formatter_class=lambda prog: CustomHelpFormatter(
            prog,
            width=78,
            max_help_position=3,
        ),
    )
    encode_ddp_parser.add_argument(
        "-c",
        "--channels",
        type=case_insensitive_enum(DolbyDigitalPlusChannels),
        choices=tuple(DolbyDigitalPlusChannels),
        default=DolbyDigitalPlusChannels.AUTO,
        metavar=enum_choices(DolbyDigitalPlusChannels),
        help="The number of channels.",
    )
    encode_ddp_parser.add_argument(
        "-n",
        "--normalize",
        action="store_true",
        help="Normalize audio for DDP (ignored for DDP channels above 6).",
    )
    encode_ddp_parser.add_argument(
        "--atmos",
        action="store_true",
        help=(
            "Enable Atmos encoding mode for TrueHD input files with Atmos content "
            "(automatically falls back to DDP if no Atmos is detected)."
        ),
    )
    encode_ddp_parser.add_argument(
        "--no-bed-conform",
        action="store_true",
        help="Disable bed conform for Atmos",
    )
    # TODO: need to re add this like dd but with it's own default
    # encode_ddp_parser.add_argument(
    #     "-drc",
    #     "--dynamic-range-compression",
    #     type=case_insensitive_enum(DeeDRC),
    #     choices=tuple(DeeDRC),
    #     metavar=enum_choices(DeeDRC),
    #     default=DeeDRC.FILM_LIGHT,
    #     help="Dynamic range compression settings.",
    # )

    #############################################################
    ## Find Command (placeholder, expect this would essentially just run
    ## the globs and print the filepaths it finds)
    #############################################################
    # Find command parser
    find_parser = subparsers.add_parser("find", parents=[input_group])
    find_parser.add_argument(
        "-n",
        "--name",
        action="store_true",
        help="Only display names instead of full paths.",
    )

    #############################################################
    ## Info Command (placeholder, would print stream info for the input file(s)) ###
    #############################################################
    # Info command parser
    _info_parser = subparsers.add_parser("info", parents=[input_group])

    #############################################################
    ## Config Command ###
    #############################################################
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

    # Info config subcommand
    info_parser = config_subparsers.add_parser(
        "info", help="Show configuration information"
    )
    info_parser.add_argument("--path", type=str, help="Show specific config file path")

    #############################################################
    ######################### Execute ###########################
    #############################################################
    # parse the arguments
    args = parser.parse_args()

    # init logger
    logger_manager.set_level(args.log_level.to_logging_level())

    if not args.sub_command:
        if not hasattr(args, "version"):
            parser.print_usage()
        exit_application("", EXIT_FAIL)

    # load configuration and apply defaults if not a config command
    config_integration = None
    if args.sub_command != "config":
        config_integration = get_config_integration()
        config_integration.load_config()

        # apply config defaults for encoding commands
        if args.sub_command == "encode":
            format_type = getattr(args, "format_command", None)

            # handle preset if specified
            if hasattr(args, "preset") and args.preset:
                preset_config = config_integration.loader.get_preset(args.preset)
                if preset_config is None:
                    available_presets = config_integration.loader.list_presets()
                    preset_list = (
                        ", ".join(available_presets) if available_presets else "None"
                    )
                    exit_application(
                        f"Preset '{args.preset}' not found. Available presets: {preset_list}",
                        EXIT_FAIL,
                    )

                # apply preset values to args (only if not already set by CLI)
                for key, value in preset_config.items():
                    if key == "format":
                        continue  # skip format since it's handled by subcommand

                    # convert key to arg attribute name
                    arg_name = key.replace("-", "_")

                    # only set if not already provided via CLI
                    if not hasattr(args, arg_name) or getattr(args, arg_name) is None:
                        # handle enum conversions
                        if arg_name == "channels":
                            if format_type == "ddp":
                                value = (
                                    DolbyDigitalPlusChannels(value)
                                    if isinstance(value, str)
                                    else value
                                )
                            elif format_type == "dd":
                                value = (
                                    DolbyDigitalChannels(value)
                                    if isinstance(value, str)
                                    else value
                                )
                        elif arg_name == "drc":
                            value = DeeDRC(value) if isinstance(value, str) else value
                        elif arg_name == "stereo_mix":
                            value = (
                                StereoDownmix(value)
                                if isinstance(value, str)
                                else value
                            )

                        setattr(args, arg_name, value)

            args = config_integration.merge_args_with_config(args, format_type)

    # detect tool dependencies
    ffmpeg_arg = None
    truehdd_arg = None
    dee_arg = None
    atmos_required = False
    ffmpeg_path = None
    truehdd_path = None
    dee_path = None

    if args.sub_command not in {"config"}:
        # get dependency paths from CLI args or config
        if config_integration:
            ffmpeg_arg = (
                args.ffmpeg
                if hasattr(args, "ffmpeg") and args.ffmpeg
                else config_integration.get_dependency_path("ffmpeg")
            )
            truehdd_arg = (
                args.truehdd
                if hasattr(args, "truehdd") and args.truehdd
                else config_integration.get_dependency_path("truehdd")
            )
            dee_arg = (
                args.dee
                if hasattr(args, "dee") and args.dee
                else config_integration.get_dependency_path("dee")
            )
        else:
            ffmpeg_arg = args.ffmpeg if hasattr(args, "ffmpeg") else None
            truehdd_arg = args.truehdd if hasattr(args, "truehdd") else None
            dee_arg = args.dee if hasattr(args, "dee") else None

        # check if Atmos is being used (only available for DDP)
        atmos_required = (
            hasattr(args, "atmos")
            and args.atmos
            and args.sub_command == "encode"
            and hasattr(args, "format_command")
            and args.format_command == "ddp"
        )

    if args.sub_command not in {"config"}:
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
        ffmpeg_path = Path(tools.ffmpeg)
        truehdd_path = Path(tools.truehdd) if tools.truehdd else None
        dee_path = Path(tools.dee)

        if not hasattr(args, "input") or not args.input:
            exit_application("", EXIT_FAIL)

        if args.sub_command not in ("find", "info"):
            # config system now handles defaults, but provide fallbacks for edge cases
            if (
                not hasattr(args, "channels")
                or not args.channels
                or int(args.channels.value) == 0
            ):
                print(  # TODO: use logger
                    "No channels specified, will automatically detect highest quality "
                    "supported channel based on codec."
                )

            # final fallback for bitrate if config system didn't set it
            # TODO: this needs to happen based on channel
            # cli > config > defaults
            # if not hasattr(args, "bitrate") or args.bitrate is None:
            #     print("No bitrate specified, defaulting to 448k.")
            #     setattr(args, "bitrate", 448)

        # parse all possible file inputs
        file_inputs = parse_input_s(args.input)
        if not file_inputs:
            exit_application("No input files we're found.", EXIT_FAIL)
    else:
        # for config command, no file inputs needed
        file_inputs = []

    if args.sub_command == "encode":
        # ensure dependency paths are available for encoding
        if ffmpeg_path is None or dee_path is None:
            exit_application(
                "Dependency paths not available for encoding commands", EXIT_FAIL
            )

        # encode Dolby Digital
        if args.format_command == "dd":
            # TODO We will need to catch all expected expectations possible and wrap this in a try except
            # with the exit application output. That way we're not catching all generic issues.
            # exit_application(e, EXIT_FAIL)
            # TODO we need to catch all errors that we know will happen here in the scope

            # update payload
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
                        bitrate=args.bitrate,  # TODO: this needs to possibly accept none or determine it here?
                        temp_dir=Path(args.temp_dir) if args.temp_dir else None,
                        delay=args.delay,
                        keep_temp=args.keep_temp,
                        file_output=Path(args.output) if args.output else None,
                        stereo_mix=args.stereo_down_mix,
                        metering_mode=args.metering_mode,
                        drc_line_mode=args.drc_line_mode,
                        drc_rf_mode=args.drc_rf_mode,
                        dialogue_intelligence=args.no_dialogue_intelligence,
                        speech_threshold=args.speech_threshold,  # int,
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
                    # pprint(payload, indent=3)
                    dd = DDEncoderDEE(payload).encode()
                    logger.info(f"Job successful! Output file path:\n{dd}")
            except Exception as e:
                exit_application(str(e), EXIT_FAIL)

        # Encode Dolby Digital Plus
        elif args.format_command == "ddp":
            # TODO We will need to catch all expected expectations possible and wrap this in a try except
            # with the exit application output. That way we're not catching all generic issues.
            # exit_application(e, EXIT_FAIL)
            # TODO we need to catch all errors that we know will happen here in the scope

            # update payload
            try:
                for input_file in file_inputs:
                    raise NotImplementedError
                    # payload = DDPPayload(
                    #     file_input=input_file,
                    #     track_index=args.track_index,
                    #     bitrate=args.bitrate,
                    #     delay=args.delay,
                    #     temp_dir=Path(args.temp_dir) if args.temp_dir else None,
                    #     keep_temp=args.keep_temp,
                    #     file_output=Path(args.output) if args.output else None,
                    #     stereo_mix=args.stereo_down_mix,
                    #     channels=args.channels,
                    #     normalize=args.normalize,
                    #     drc=args.dynamic_range_compression,
                    #     atmos=args.atmos,
                    #     no_bed_conform=args.no_bed_conform,
                    #     ffmpeg_path=ffmpeg_path,
                    #     truehdd_path=truehdd_path,
                    #     dee_path=dee_path,
                    # )

                    # # encoder
                    # ddp = DDPEncoderDEE(payload).encode()
                    print(f"Job successful! Output file path:\n{ddp}")
            except Exception as e:
                # TODO not sure if we wanna exit or continue for batch?
                exit_application(str(e), EXIT_FAIL)

    elif args.sub_command == "find":
        file_names = []
        for input_file in file_inputs:
            # if name only is used, print only the name of the file.
            if args.name:
                input_file = input_file.name
            file_names.append(str(input_file))

        exit_application("\n".join(file_names), EXIT_SUCCESS)

    elif args.sub_command == "info":
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

    elif args.sub_command == "config":
        # config commands need their own integration instance
        if config_integration is None:
            config_integration = get_config_integration()

        if args.config_command == "generate":
            try:
                output_path = Path(args.output) if args.output else None

                if args.from_args:
                    # for generating from args, we need to parse the full command
                    # this is a bit tricky since we're in the middle of execution
                    # for now, just use default generation
                    config_path = config_integration.generate_config(
                        output_path=output_path, overwrite=args.overwrite
                    )
                else:
                    config_path = config_integration.generate_config(
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
                        exit_application(
                            f"Config file not found: {config_path}", EXIT_FAIL
                        )
                else:
                    config_integration.load_config()
                    if config_integration.loader.config_path:
                        info_text = f"Active config file: {config_integration.loader.config_path}\n"
                        info_text += f"Presets available: {', '.join(config_integration.loader.list_presets()) or 'None'}"
                    else:
                        info_text = (
                            "No configuration file found. Using built-in defaults.\n"
                        )
                        from deezy.config.defaults import get_default_config_path

                        info_text += (
                            f"Default config location: {get_default_config_path()}"
                        )

                    exit_application(info_text, EXIT_SUCCESS)
            except Exception as e:
                exit_application(f"Failed to load config info: {e}", EXIT_FAIL)
