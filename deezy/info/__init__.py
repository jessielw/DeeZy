import shutil
from dataclasses import dataclass
from pathlib import Path

from pymediainfo import MediaInfo, Track

from deezy.track_info.mediainfo import MediainfoParser


@dataclass(slots=True)
class AudioStreams:
    media_info: str | None = None
    track_list: list[int] | None = None


def parse_audio_streams(file_input: Path) -> AudioStreams:
    """Parse audio streams information from a media file and return an instance
    of AudioStreams class containing the formatted string and a list of audio track IDs.

    Args:
        file_input (Path): File input path.

    Returns:
        dict: A dictionary containing two keys: "track_output" (a formatted string containing information
        about the audio tracks) and "track_list" (a list of audio track IDs).
    """
    # media info object
    media_info_obj = MediaInfo.parse(Path(file_input))

    # list of tracks to return
    track_list = []

    # variable to output a final string
    media_info_track_string = ""

    # used to detect the max size of the terminal - 10
    columns = min(shutil.get_terminal_size().columns, 100) - 10

    # ensure there is audio tracks in the parsed object
    if (
        not media_info_obj.general_tracks[0].count_of_audio_streams
        or media_info_obj.general_tracks[0].count_of_audio_streams == 0
    ):
        raise ValueError("Input file does not have any audio tracks.")

    # loop through the audio tracks
    for track in media_info_obj.tracks:
        if track.track_type == "Audio":
            # audio track id
            audio_track_id = ""
            if track.stream_identifier or track.stream_identifier == 0:
                audio_track_id = (
                    f"{calculate_space('Track')}: {str(int(track.stream_identifier))}\n"
                )
                track_list.append(int(track.stream_identifier))

            # audio format
            audio_format = ""
            get_audio_format = safe_get_audio_format(track)
            if track.format:
                audio_format = f"{calculate_space('Codec')}: {get_audio_format} - ({track.commercial_name})\n"

            # audio channel(s)
            audio_channel_s = ""
            t_channels = MediainfoParser.get_channels(track)
            if t_channels is not None:
                channels_dict = {
                    1: "1.0",
                    2: "2.0",
                    3: "2.1",
                    4: "4.0",
                    5: "4.1",
                    6: "5.1",
                    7: "7.1",
                }
                show_channels = channels_dict.get(t_channels, t_channels)
                audio_channel_s = f"{calculate_space('Channels')}: {show_channels} - {track.channel_layout}\n"

            # audio bit-rate-mode
            audio_bitrate_mode = ""
            if track.bit_rate_mode:
                # Try to get secondary string of audio bit rate mode
                if track.other_bit_rate_mode:
                    audio_bitrate_mode = (
                        f"{calculate_space('Bit rate mode')}: "
                        f"{track.bit_rate_mode} / {track.other_bit_rate_mode[0]}\n"
                    )
                else:
                    audio_bitrate_mode = (
                        f"{calculate_space('Bit rate mode')}: {track.bit_rate_mode}\n"
                    )

            # audio bit-rate
            audio_bitrate = ""
            if track.other_bit_rate:
                audio_bitrate = (
                    f"{calculate_space('Bit rate')}: {track.other_bit_rate[0]}\n"
                )

            # audio language
            audio_language = ""
            if track.other_language:
                audio_language = (
                    f"{calculate_space('Language')}: {track.other_language[0]}\n"
                )

            # audio title
            audio_title = ""
            if track.title:
                # shorten track title if it's over 40 characters long
                if len(track.title) > 40:
                    audio_title = f"{calculate_space('Title')}: {track.title[:40]}...\n"
                else:
                    audio_title = f"{calculate_space('Title')}: {track.title}\n"

            # sampling rate
            audio_sampling_rate = ""
            if track.other_sampling_rate:
                audio_sampling_rate = f"{calculate_space('Sampling Rate')}: {track.other_sampling_rate[0]}\n"

            # duration
            audio_duration = ""
            if track.other_duration:
                audio_duration = (
                    f"{calculate_space('Duration')}: {track.other_duration[0]}\n"
                )

            # delay
            audio_delay = ""
            # TODO This might need to be adjusted to detect delay from mp4 sources as well
            if track.delay and track.delay != 0:
                audio_delay = (
                    f"{calculate_space('Delay')}: {track.delay}ms"
                    + f"{calculate_space('Delay to Video')}: {track.delay_relative_to_video}ms\n"
                )

            # stream size
            audio_track_stream_size = ""
            if track.other_stream_size:
                audio_track_stream_size = (
                    f"{calculate_space('Stream size')}: {track.other_stream_size[4]}\n"
                )

            # bit depth
            audio_track_bit_depth = ""
            if track.other_bit_depth:
                audio_track_bit_depth = (
                    f"{calculate_space('Bit Depth')}: {(track.other_bit_depth[0])}\n"
                )

            # compression
            audio_track_compression = ""
            if track.compression_mode:
                audio_track_compression = (
                    f"{calculate_space('Compression')}: {track.compression_mode}\n"
                )

            # default
            audio_track_default = ""
            if track.default:
                audio_track_default = f"{calculate_space('Default')}: {track.default}\n"

            # forced
            audio_track_forced = ""
            if track.forced:
                audio_track_forced = f"{calculate_space('Forced')}: {track.forced}"

            audio_track_info = str(
                audio_track_id
                + audio_format
                + audio_channel_s
                + audio_bitrate_mode
                + audio_bitrate
                + audio_sampling_rate
                + audio_delay
                + audio_duration
                + audio_language
                + audio_title
                + audio_track_stream_size
                + audio_track_bit_depth
                + audio_track_compression
                + audio_track_default
                + audio_track_forced
            )

            media_info_track_string = media_info_track_string + (
                columns * "-" + "\n" + audio_track_info + "\n" + columns * "-" + "\n"
            )

    # return {"track_output": media_info_track_string, "track_list": track_list}
    streams = AudioStreams(media_info=media_info_track_string, track_list=track_list)
    return streams


def calculate_space(title: str, character_space: int = 20) -> str:
    """
    Calculate the required amount of space needed to align a title string in a fixed width format.

    Args:
        title (str): The string to be aligned.
        character_space (int, optional): The total width of the space allocated for the aligned string. Defaults to 20.

    Returns:
        str: A string containing the input `title` and padding spaces to align with the `character_space`.

    """
    return f"{title}{' ' * (character_space - len(title))}"


def safe_get_audio_format(a_track: Track) -> str:
    if a_track.other_format and isinstance(a_track.other_format, list):
        return a_track.other_format[0]
    else:
        return a_track.format
