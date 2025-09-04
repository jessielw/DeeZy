import argparse
from pathlib import Path

from cli.utils import CustomHelpFormatter, _validate_track_index
from deezy.audio_encoders.dee.dd import DDEncoderDEE
from deezy.audio_encoders.dee.ddp import DDPEncoderDEE
from deezy.enums import case_insensitive_enum, enum_choices
from deezy.enums.dd import DolbyDigitalChannels
from deezy.enums.ddp import DolbyDigitalPlusChannels
from deezy.enums.shared import DeeDRC, ProgressMode, StereoDownmix
from deezy.info import AudioStreamViewer
from deezy.payloads.dd import DDPayload
from deezy.payloads.ddp import DDPPayload
from deezy.utils._version import __version__, program_name
from deezy.utils.dependencies import DependencyNotFoundError, FindDependencies
from deezy.utils.exit import EXIT_FAIL, EXIT_SUCCESS, exit_application
from deezy.utils.file_parser import parse_input_s


def cli_parser(base_wd: Path):
    # Top-level parser
    parser = argparse.ArgumentParser(prog=program_name)

    # Add a global -v flag
    parser.add_argument(
        "-v", "--version", action="version", version=f"%(prog)s {__version__}"
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
        help="Path to DEE (Dolby Encoding Engine) executable.",
    )
    encode_group.add_argument(
        "-t",
        "--track-index",
        type=_validate_track_index,
        default=0,
        help="The index of the audio track to use.",
    )
    encode_group.add_argument(
        "-b", "--bitrate", type=int, required=False, help="The bitrate in Kbps."
    )
    encode_group.add_argument(
        "-d",
        "--delay",
        type=str,
        help="The delay in milliseconds or seconds. Note '-d=' is required! (-d=-10ms / -d=10s).",
    )
    encode_group.add_argument(
        "-k",
        "--keep-temp",
        action="store_true",
        help="Keeps the temp files after finishing (usually a wav and an xml for DEE).",
    )
    # TODO add a SILENT mode (already in enums)
    encode_group.add_argument(
        "-p",
        "--progress-mode",
        type=case_insensitive_enum(ProgressMode),
        default=ProgressMode.STANDARD,
        choices=list(ProgressMode),
        metavar=enum_choices(ProgressMode),
        help="Sets progress output mode verbosity.",
    )
    encode_group.add_argument(
        "-tmp",
        "--temp-dir",
        type=str,
        help="Path to store temporary files to. If not specified this will automatically happen in the temp dir of the os.",
    )
    encode_group.add_argument(
        "-o",
        "--output",
        type=str,
        help="The output file path. If not specified we will attempt to automatically add Delay/Language string to output file name.",
    )

    # downmix group
    downmix_group = argparse.ArgumentParser(add_help=False)
    downmix_group.add_argument(
        "-s",
        "--stereo-down-mix",
        type=case_insensitive_enum(StereoDownmix),
        choices=list(StereoDownmix),
        default=StereoDownmix.STANDARD,
        metavar=enum_choices(StereoDownmix),
        help="Down mix method for stereo.",
    )

    ### Dolby Digital Command ###
    encode_dd_parser = encode_subparsers.add_parser(
        "dd",
        parents=[input_group, encode_group, downmix_group],
        formatter_class=lambda prog: CustomHelpFormatter(
            prog,
            width=78,
            max_help_position=3,
        ),
    )
    encode_dd_parser.add_argument(
        "-c",
        "--channels",
        type=case_insensitive_enum(DolbyDigitalChannels),
        choices=list(DolbyDigitalChannels),
        default=DolbyDigitalChannels.AUTO,
        metavar=enum_choices(DolbyDigitalChannels),
        help="The number of channels.",
    )
    # TODO this will likely only be valid for DEE, so we'll need to
    # decide what we want to do here
    encode_dd_parser.add_argument(
        "-drc",
        "--dynamic-range-compression",
        type=case_insensitive_enum(DeeDRC),
        choices=list(DeeDRC),
        metavar=enum_choices(DeeDRC),
        default=DeeDRC.MUSIC_LIGHT,
        help="Dynamic range compression settings.",
    )

    ### Dolby Digital Plus Command ###
    encode_ddp_parser = encode_subparsers.add_parser(
        "ddp",
        parents=[input_group, encode_group, downmix_group],
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
        choices=list(DolbyDigitalPlusChannels),
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
    encode_ddp_parser.add_argument(
        "-drc",
        "--dynamic-range-compression",
        type=case_insensitive_enum(DeeDRC),
        choices=list(DeeDRC),
        metavar=enum_choices(DeeDRC),
        default=DeeDRC.MUSIC_LIGHT,
        help="Dynamic range compression settings.",
    )

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
    ######################### Execute ###########################
    #############################################################
    # parse the arguments
    args = parser.parse_args()

    if not args.sub_command:
        if not hasattr(args, "version"):
            parser.print_usage()
        exit_application("", EXIT_FAIL)

    # detect tool dependencies
    ffmpeg_arg = args.ffmpeg if hasattr(args, "ffmpeg") else None
    truehdd_arg = args.truehdd if hasattr(args, "truehdd") else None
    dee_arg = args.dee if hasattr(args, "dee") else None
    try:
        tools = FindDependencies().get_dependencies(
            base_wd, ffmpeg_arg, truehdd_arg, dee_arg
        )
    except DependencyNotFoundError as e:
        exit_application(str(e), EXIT_FAIL)
    ffmpeg_path = Path(tools.ffmpeg)
    truehdd_path = Path(tools.truehdd)
    dee_path = Path(tools.dee)

    if not hasattr(args, "input") or not args.input:
        exit_application("", EXIT_FAIL)

    if args.sub_command not in {"find", "info"}:
        if (
            not hasattr(args, "channels")
            or not args.channels
            or int(args.channels.value) == 0
        ):
            print(
                "No channel(s) specified, will automatically detect highest quality supported channel based on codec."
            )

        if not hasattr(args, "bitrate") or not args.bitrate:
            print("No bitrate specified, defaulting to 448k.")
            setattr(args, "bitrate", 448)

    # parse all possible file inputs
    # TODO We will need to decide what to do when multiple file inputs
    # don't have the track provided by the user?
    # Additionally is this the best place to do this?
    file_inputs = parse_input_s(args.input)
    if not file_inputs:
        exit_application("No input files we're found.", EXIT_FAIL)

    if args.sub_command == "encode":
        # encode Dolby Digital
        if args.format_command == "dd":
            # TODO We will need to catch all expected expectations possible and wrap this in a try except
            # with the exit application output. That way we're not catching all generic issues.
            # exit_application(e, EXIT_FAIL)
            # TODO we need to catch all errors that we know will happen here in the scope

            # update payload
            try:
                for input_file in file_inputs:
                    payload = DDPayload(
                        file_input=input_file,
                        track_index=args.track_index,
                        bitrate=args.bitrate,
                        delay=args.delay,
                        temp_dir=Path(args.temp_dir) if args.temp_dir else None,
                        keep_temp=args.keep_temp,
                        file_output=Path(args.output) if args.output else None,
                        progress_mode=args.progress_mode,
                        stereo_mix=args.stereo_down_mix,
                        channels=args.channels,
                        drc=args.dynamic_range_compression,
                        ffmpeg_path=ffmpeg_path,
                        truehdd_path=truehdd_path,
                        dee_path=dee_path,
                    )
                    dd = DDEncoderDEE().encode(payload)
                    print(f"Job successful! Output file path:\n{dd}")
            except Exception as e:
                exit_application(str(e), EXIT_FAIL)

        # Encode Dolby Digital Plus
        elif args.format_command == "ddp":
            # TODO We will need to catch all expected expectations possible and wrap this in a try except
            # with the exit application output. That way we're not catching all generic issues.
            # exit_application(e, EXIT_FAIL)
            # TODO we need to catch all errors that we know will happen here in the scope

            # update payload
            # TODO prevent duplicate payload code somehow
            try:
                for input_file in file_inputs:
                    payload = DDPPayload(
                        file_input=input_file,
                        track_index=args.track_index,
                        bitrate=args.bitrate,
                        delay=args.delay,
                        temp_dir=Path(args.temp_dir) if args.temp_dir else None,
                        keep_temp=args.keep_temp,
                        file_output=Path(args.output) if args.output else None,
                        progress_mode=args.progress_mode,
                        stereo_mix=args.stereo_down_mix,
                        channels=args.channels,
                        normalize=args.normalize,
                        drc=args.dynamic_range_compression,
                        atmos=args.atmos,
                        no_bed_conform=args.no_bed_conform,
                        ffmpeg_path=ffmpeg_path,
                        truehdd_path=truehdd_path,
                        dee_path=dee_path,
                    )

                    # encoder
                    ddp = DDPEncoderDEE(payload).encode()
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
            info = AudioStreamViewer().parse_audio_streams(input_file)
            if info.media_info:
                track_s_info = (
                    track_s_info
                    + f"File: {input_file.name}\nAudio tracks: {info.track_list}\n"
                    + info.media_info
                    + "\n\n"
                )
        exit_application(track_s_info, EXIT_SUCCESS)
