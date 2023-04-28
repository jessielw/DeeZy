import argparse
from pathlib import Path
from audio_encoder.utils._version import program_name, __version__
from audio_encoder.utils.exit import _exit_application, exit_fail, exit_success
from audio_encoder.utils.file_parser import FileParser
from audio_encoder.utils.dependencies import DependencyNotFoundError, FindDependencies
from audio_encoder.audio_encoders.dee.dd import DDEncoderDEE
from audio_encoder.payloads.dd import DDPayload
from audio_encoder.enums import case_insensitive_enum, enum_choices
from audio_encoder.enums.shared import ProgressMode, StereoDownmix
from audio_encoder.enums.dd import DolbyDigitalChannels
from audio_encoder.enums.ddp import DolbyDigitalPlusChannels
from audio_encoder.info import AudioStreamViewer


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


def _main(base_wd: Path):
    # define tools
    # TODO might be able to still handle the tools better?
    try:
        tools = FindDependencies().get_dependencies(base_wd)
    except DependencyNotFoundError as e:
        _exit_application(e, exit_fail)
    ffmpeg_path = Path(tools.ffmpeg)
    dee_path = Path(tools.dee)

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
        "-t",
        "--track-index",
        type=int,
        default=0,
        help="The index of the audio track to use.",
    )
    encode_group.add_argument(
        "-b", "--bitrate", type=int, required=False, help="The bitrate in Kbps."
    )
    encode_group.add_argument(
        "-d", "--delay", type=int, default=0, help="The delay in milliseconds."
    )
    encode_group.add_argument(
        "-k",
        "--keep-temp",
        action="store_true",
        help="Keeps the temp files after finishing (usually a wav and an xml for DEE).",
    )
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
        metavar=enum_choices(DolbyDigitalChannels),
        help="The number of channels.",
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
        metavar=enum_choices(DolbyDigitalPlusChannels),
        help="The number of channels.",
    )
    encode_ddp_parser.add_argument(
        "-n", "--normalize", action="store_true", help="Normalize audio for DDP."
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
    # TODO: Add arg options if required

    #############################################################
    ## Info Command (placeholder, would print stream info for the input file(s)) ###
    #############################################################
    # Info command parser
    info_parser = subparsers.add_parser("info", parents=[input_group])
    # TODO: Add arg options if required

    #############################################################
    ######################### Execute ###########################
    #############################################################
    # parse the arguments
    args = parser.parse_args()

    if not args.sub_command:
        if not hasattr(args, "version"):
            parser.print_usage()
        # TODO maybe exit this with _exit_application printing a message?
        exit()

    if not hasattr(args, "input") or not args.input:
        # TODO maybe exit this with _exit_application printing a message?
        exit()

    # parse all possible file inputs
    # TODO We will need to decide what to do when multiple file inputs
    # don't have the track provided by the user?
    # Additionally is this the best place to do this?
    file_inputs = FileParser().parse_input_s(args.input)
    if not file_inputs:
        _exit_application("No input files we're found.", exit_fail)

    if args.sub_command == "encode":
        # TODO Display banner here?

        # TODO DO we print this here as well?
        # print message
        # print(f"Processing input: {Path(args.input).name}")

        if args.format_command == "dd":
            # TODO We will need to catch all expected expectations possible and wrap this in a try except
            # with the exit application output. That way we're not catching all generic issues.
            # _exit_application(e, exit_fail)
            # TODO we need to catch all errors that we know will happen here in the scope

            # update payload
            # TODO prevent duplicate payload code somehow
            for input_file in file_inputs:
                payload = DDPayload()
                payload.file_input = input_file
                payload.track_index = args.track_index
                payload.bitrate = args.bitrate
                payload.delay = args.delay
                payload.temp_dir = args.temp_dir
                payload.keep_temp = args.keep_temp
                payload.file_output = args.output
                payload.progress_mode = args.progress_mode
                payload.stereo_mix = args.stereo_down_mix
                payload.channels = args.channels

                # TODO Not sure if this is how we wanna inject, but for now...
                payload.ffmpeg_path = ffmpeg_path
                payload.dee_path = dee_path

                # encoder
                dd = DDEncoderDEE().encode(payload)

        elif args.format_command == "ddp":
            # Encode DDP
            pass

    # Find
    elif args.sub_command == "find":
        # TODO ensure this is done the best way possible.
        file_names = []
        for input_file in file_inputs:
            # if name only is used, print only the name of the file.
            if args.name:
                input_file = input_file.name

            # append file to file_names (ensuring they are strings for the .join method)
            file_names.append(str(input_file))

            # Join the file names with newlines
            found_files = "\n".join(file_names)

        _exit_application(found_files, exit_success)

    # Info
    elif args.sub_command == "info":
        # TODO this probably needs handled in a cleaner way.
        # could use list comprehension here but will be harder to
        # add args if we add them later?
        track_s_info = ""
        for input_file in file_inputs:
            info = AudioStreamViewer().parse_audio_streams(input_file)
            track_s_info = (
                track_s_info
                + f"File: {input_file.name}\nAudio tracks: {info.track_list}\n"
                + info.media_info
                + "\n\n"
            )
        _exit_application(track_s_info, exit_success)
