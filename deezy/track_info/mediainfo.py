from pathlib import Path
from re import search

from pymediainfo import MediaInfo, Track

from deezy.exceptions import MediaInfoError
from deezy.track_info.audio_track_info import AudioTrackInfo


class MediainfoParser:
    __slots__ = ("file_input", "track_index", "mi_obj", "mi_audio_obj")

    def __init__(self, file_input: Path, track_index: int) -> None:
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
            fps=self._get_fps(),
            audio_only=False,
            recommended_free_space=self._recommended_free_space(),
            duration=self._get_duration(),
            sample_rate=self.mi_audio_obj.sampling_rate,
            bit_depth=self.mi_audio_obj.bit_depth,
            channels=self._get_channels(),
            thd_atmos=self._is_thd_atmos(),
        )

        # return object
        return audio_info

    def _verify_audio_track(self, track_index: int) -> Track:
        """
        Checks that the specified track index in the given MediaInfo object corresponds to an audio track.

        Args:
            track_index: An integer representing the index of the track to be verified.

        Returns:
            Track: MediaInfo Track object.

        Raises:
            MediaInfoError: If the specified track index does not correspond to an audio track.
        """
        try:
            track_info = self.mi_obj.audio_tracks[track_index].track_type
            if track_info != "Audio":
                raise MediaInfoError(
                    f"Selected track #{track_index} ({track_info}) is not an audio track."
                )
            else:
                return self.mi_obj.audio_tracks[track_index]
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

    def _get_channels(self) -> int:
        """
        Get the number of audio channels for the specified track.

        The added complexity for 'check_other' is to ensure we get a report
        of the highest potential channel count.

        Returns:
            The number of audio channels as an integer.
        """
        base_channels = self.mi_audio_obj.channel_s
        check_other = search(r"\d+", str(self.mi_audio_obj.other_channel_s[0]))
        check_other_2 = str(self.mi_audio_obj.channel_s__original)

        # create a list of values to find the maximum
        values = [int(base_channels)]

        if check_other:
            values.append(int(check_other.group()))

        if check_other_2.isdigit():
            values.append(int(check_other_2))

        return max(values)

    def _is_thd_atmos(self) -> bool:
        """Check if track is a THD Atmos file."""
        if self.mi_audio_obj.commercial_name == "Dolby TrueHD with Dolby Atmos":
            return True
        return False

    def _generate_output_filename(self):
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

        # if track index is equal to or greater than 1, we can assume it's likely in a container of some
        # sort, so we'll go ahead and attempt to detect delay/language to inject into the title.
        elif self.track_index >= 1:
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
