from pathlib import Path
import re

from pymediainfo import MediaInfo, Track

from deezy.enums.shared import TrackType
from deezy.exceptions import MediaInfoError
from deezy.track_info.audio_track_info import AudioTrackInfo
from deezy.track_info.track_index import TrackIndex


class MediainfoParser:
    __slots__ = ("file_input", "track_index", "mi_obj", "mi_audio_obj")

    def __init__(self, file_input: Path, track_index: TrackIndex) -> None:
        # parse file with mediainfo
        self.file_input = file_input
        self.track_index = track_index
        self.mi_obj = MediaInfo.parse(file_input, legacy_stream_display=True)
        self.mi_audio_obj = self._verify_audio_track(track_index)

    def get_audio_track_info(self) -> AudioTrackInfo:
        """
        Returns an AudioTrackInfo object with metadata for the audio track at the specified index in the input file.
        """
        # initiate AudioTrackInfo class
        audio_info = AudioTrackInfo(
            mi_track=self.mi_audio_obj,
            auto_name=self._generate_output_filename(),
            is_raw_audio=self.is_raw_audio(),
            fps=self._get_fps(),
            audio_only=False,
            recommended_free_space=self._recommended_free_space(),
            duration=self._get_duration(),
            sample_rate=self.mi_audio_obj.sampling_rate,
            bit_depth=self.mi_audio_obj.bit_depth,
            channels=self.get_channels(self.mi_audio_obj),
            thd_atmos=self._is_thd_atmos(),
        )

        # return object
        return audio_info

    def _verify_audio_track(self, track_index: TrackIndex) -> Track:
        """
        Checks that the specified track index in the given MediaInfo object corresponds to an audio track.

        Args:
            track_index: TrackIndex.

        Returns:
            Track: MediaInfo Track object.

        Raises:
            MediaInfoError: If the specified track index does not correspond to an audio track.
        """
        try:
            if track_index.track_type is TrackType.STREAM:
                track_info = self.get_track_by_stream_index(
                    self.mi_obj, track_index.index
                )
            else:
                track_info = self.mi_obj.audio_tracks[track_index.index]
            if track_info.track_type != "Audio":
                raise MediaInfoError(
                    f"Selected track #{track_index} ({track_info}) is not an audio track."
                )
            else:
                return track_info
        except IndexError:
            raise MediaInfoError(f"Selected track #{track_index} does not exist.")

    def _get_fps(self) -> float | None:
        """
        Get the frames per second (fps) for the video track in the media info object.

        Returns:
            fps (float or None): The frames per second (fps) for the video track, or None if there is no video track.
        """
        for mi_track in self.mi_obj.tracks:
            if mi_track.track_type == "Video":
                return float(mi_track.frame_rate) if mi_track.frame_rate else None

    def _recommended_free_space(self) -> int | None:
        """
        Determine the recommended temporary file size needed for processing.

        Returns:
            size (int or None): Recommended size in bytes.
        """
        selected_audio_track_size = self.mi_audio_obj.stream_size
        if selected_audio_track_size:
            try:
                return int(selected_audio_track_size)
            except ValueError:
                general_track = self.mi_obj.general_tracks[0]
                video_streams = general_track.count_of_video_streams
                audio_streams = general_track.count_of_audio_streams

                if video_streams and audio_streams:
                    return int(int(general_track.stream_size) * 0.12)
                else:
                    return int(int(general_track.stream_size) * 1.1)

    def _get_duration(self) -> float | None:
        """
        Retrieve the duration of a specified track in milliseconds.

        Returns:
            duration (float or None): The duration of the specified track in milliseconds, or
            None if the duration cannot be retrieved.
        """
        duration = self.mi_audio_obj.duration
        return float(duration) if duration else None

    def _is_thd_atmos(self) -> bool:
        """Check if track is a THD Atmos file."""
        if self.mi_audio_obj.commercial_name == "Dolby TrueHD with Dolby Atmos":
            return True
        return False

    def _generate_output_filename(self) -> Path:
        """Automatically generate an output file name

        Returns:
            Path: Path of a automatically generated filename
        """
        # placeholder extension
        extension = ".tmp"

        # base directory/name
        base_dir = Path(self.file_input).parent
        base_name = Path(Path(self.file_input).name).with_suffix("")

        # if track index is 0 we can assume this audio is in a raw format
        if self.track_index == 0:
            file_name = f"{base_name}{extension}"
            return Path(base_dir / Path(file_name))

        # if track index is anything other than 0, we can assume it's likely in a container of some
        # sort, so we'll go ahead and attempt to detect delay/language to inject into the title.
        else:
            delay = self._delay_detection()
            language = self._language_detection()
            file_name = f"{base_name}_{language}_{delay}{extension}"
            return Path(base_dir / Path(file_name))

    def _delay_detection(self):
        """Detect delay relative to video to inject into filename

        Returns:
            str: Returns a formatted delay string
        """
        if self.file_input.suffix == ".mp4":
            if self.mi_audio_obj.source_delay:
                delay_string = f"[delay {str(self.mi_audio_obj.source_delay)}ms]"
            else:
                delay_string = str("[delay 0ms]")
        else:
            if self.mi_audio_obj.delay_relative_to_video:
                delay_string = (
                    f"[delay {str(self.mi_audio_obj.delay_relative_to_video)}ms]"
                )
            else:
                delay_string = str("[delay 0ms]")
        return delay_string

    def _language_detection(self):
        """
        Detect language of input track, returning language in the format of
        "eng" instead of "en" or "english."

        Returns:
            str: Returns a formatted language string
        """
        if self.mi_audio_obj.other_language:
            l_lengths = [len(lang) for lang in self.mi_audio_obj.other_language]
            l_index = next(
                (i for i, length in enumerate(l_lengths) if length == 3), None
            )
            language_string = (
                f"[{self.mi_audio_obj.other_language[l_index]}]"
                if l_index is not None
                else "[und]"
            )
        else:
            language_string = "[und]"
        return language_string

    def is_raw_audio(self) -> bool:
        """
        Helper method to determine if the input is just raw audio.

        Checks if count of audio streams is greater than 1 and ensures
        there are any other tracks.
        """
        try:
            general = self.mi_obj.general_tracks[0]
            audio_streams = int(getattr(general, "count_of_audio_streams", 0) or 0)
            if audio_streams != 1:
                return False
            other_tracks = sum(
                int(getattr(general, key, 0) or 0)
                for key in (
                    "count_of_video_streams",
                    "count_of_text_streams",
                    "count_of_menu_streams",
                )
            )
            return other_tracks == 0
        except (IndexError, AttributeError, ValueError):
            return False

    @staticmethod
    def get_channels(mi_audio_obj: Track) -> int:
        """
        Get the number of audio channels for the specified track.

        The added complexity for 'check_other' is to ensure we get a report
        of the highest potential channel count.

        Returns:
            The number of audio channels as an integer.
        """
        if isinstance(mi_audio_obj.channel_s, int):
            base_channels = mi_audio_obj.channel_s
        else:
            base_channels = max(
                int(x) for x in re.findall(r"\d+", str(mi_audio_obj.channel_s)) if x
            )
        check_other = re.search(r"\d+", str(mi_audio_obj.other_channel_s[0]))
        check_other_2 = str(mi_audio_obj.channel_s__original)

        # create a list of values to find the maximum
        values = [base_channels]

        if check_other:
            values.append(int(check_other.group()))

        if check_other_2.isdigit():
            values.append(int(check_other_2))

        return max(values)

    @staticmethod
    def get_track_by_stream_index(mi: MediaInfo, idx: int) -> Track:
        """Get track by FFMPEG style stream index (+1 to skip general track)."""
        return mi.tracks[idx + 1]
