from audio_encoder.media_info.audio_track_info import AudioTrackInfo
from pymediainfo import MediaInfo
from pathlib import Path
from re import search


class MediaInfoError(Exception):
    """Custom class for MediaInfo errors"""

    pass


class MediainfoParser:
    def get_track_by_id(self, file_input: Path, track_index: int):
        """Returns an AudioTrackInfo object with metadata for the audio track at the specified index in the input file.

        Parameters:
            file_input (Path): The input file to extract audio track metadata from.
            track_index (int): The index of the audio track to extract metadata for.

        Returns:
            AudioTrackInfo: An object with the extracted audio track metadata, including fps, duration, sample rate, bit depth, and channels.

        Raises:
            MediaInfoError: If the specified track index is out of range or the specified track is not an audio track.
        """
        # parse the input file with MediaInfo lib
        mi_object = MediaInfo.parse(file_input)

        # verify
        self._verify_track_index(mi_object, track_index)
        self._verify_audio_track(mi_object, track_index)

        # initiate AudioTrackInfo class
        audio_info = AudioTrackInfo()

        # update AudioTrackInfo with needed values
        audio_info.fps = self._get_fps(mi_object)
        audio_info.duration = self._get_duration(mi_object, track_index)
        audio_info.sample_rate = mi_object.tracks[track_index + 1].sampling_rate
        audio_info.bit_depth = mi_object.tracks[track_index + 1].bit_depth
        audio_info.channels = self._get_channels(mi_object, track_index)

        # return object
        return audio_info

    @staticmethod
    def _verify_track_index(mi_object, track_index):
        """
        Verify that the requested track exists in the MediaInfo object.

        Args:
            mi_object (MediaInfo): A MediaInfo object containing information about a media file.
            track_index (int): The index of the requested track.

        Raises:
            MediaInfoError: If the requested track does not exist in the MediaInfo object.
        """
        try:
            mi_object.tracks[track_index + 1]
        except IndexError:
            raise MediaInfoError(f"Selected track #{track_index} does not exist.")

    @staticmethod
    def _verify_audio_track(mi_object, track_index):
        """
        Checks that the specified track index in the given MediaInfo object corresponds to an audio track.

        Args:
            mi_object: A MediaInfo object.
            track_index: An integer representing the index of the track to be verified.

        Raises:
            MediaInfoError: If the specified track index does not correspond to an audio track.
        """
        track_info = mi_object.tracks[track_index + 1].track_type
        if track_info != "Audio":
            raise MediaInfoError(
                f"Selected track #{track_index} ({track_info}) is not an audio track."
            )

    @staticmethod
    def _get_fps(mi_object):
        """
        Get the frames per second (fps) for the video track in the media info object.

        Args:
            mi_object (MediaInfo): A MediaInfo object.

        Returns:
            fps (float or None): The frames per second (fps) for the video track, or None if there is no video track.
        """
        for mi_track in mi_object.tracks:
            if mi_track.track_type == "Video":
                fps = mi_track.frame_rate
                break
            else:
                fps = None
        return fps

    @staticmethod
    def _get_duration(mi_object, track_index):
        """
        Retrieve the duration of a specified track in milliseconds.

        Parameters:
            mi_object (MediaInfoDLL.MediaInfo): A MediaInfo object containing information about a media file.
            track_index (int): The index of the track for which to retrieve the duration.

        Returns:
            duration (float or None): The duration of the specified track in milliseconds, or None if the duration cannot be retrieved.
        """
        duration = mi_object.tracks[track_index + 1].duration
        if duration:
            duration = float(duration)
        return duration

    @staticmethod
    def _get_channels(mi_object, track_index):
        """
        Get the number of audio channels for the specified track.

        Args:
            mi_object (MediaInfo): A MediaInfo object containing information about the media file.
            track_index (int): The index of the track to extract information from.

        Returns:
            The number of audio channels as an integer.
        """
        track = mi_object.tracks[track_index + 1]
        base_channels = track.channel_s
        check_other = search(r"\d+", str(track.other_channel_s[0]))
        if check_other:
            return max(int(base_channels), int(check_other.group()))
        else:
            return base_channels
