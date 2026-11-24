from __future__ import annotations

from pathlib import Path
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pymediainfo import MediaInfo, Track

from deezy.enums.shared import TrackType
from deezy.exceptions import InvalidAtmosInputError, MediaInfoError
from deezy.track_info.audio_track_info import AudioTrackInfo
from deezy.track_info.damf import Damf, damf_header_of, is_damf, read_damf
from deezy.track_info.track_index import TrackIndex
from deezy.track_info.utils import (
    clean_title,
    parse_delay_from_file,
    strip_delay_from_file_string_and_cleanse,
)

# a [] or () pair with nothing but whitespace inside
_EMPTY_BRACKETS = re.compile(r"\[\s*\]|\(\s*\)")


class MediainfoParser:
    __slots__ = (
        "file_input",
        "track_index",
        "damf",
        "mi_obj",
        "mi_audio_obj",
        "guess",
    )

    def __init__(self, file_input: Path, track_index: TrackIndex) -> None:
        # parse file with mediainfo
        self.file_input = file_input
        self.track_index = track_index
        header = damf_header_of(file_input)
        if header:
            raise InvalidAtmosInputError(
                f"{file_input.name} is part of a DAMF master; give its header, "
                f"{header.name}."
            )
        # a DAMF master's audio is its one track
        self.damf: Damf | None = read_damf(file_input) if is_damf(file_input) else None
        from pymediainfo import MediaInfo

        self.mi_obj = MediaInfo.parse(
            self.damf.audio if self.damf else file_input, legacy_stream_display=True
        )
        self.mi_audio_obj = self._verify_audio_track(track_index)
        from guessit import guessit

        self.guess = guessit(self.file_input.name)

    def get_audio_track_info(self) -> AudioTrackInfo:
        """
        Returns an AudioTrackInfo object with metadata for the audio track at the specified index in the input file.
        """
        counts = self._channel_counts(self.mi_audio_obj)
        dtsx_bed_71 = (
            self.mi_audio_obj.format == "DTS"
            and "X" in (self.mi_audio_obj.format_additionalfeatures or "").split()
            and 8 in counts
            and max(counts) in (8, 12)
        )
        audio_info = AudioTrackInfo(
            mi_track=self.mi_audio_obj,
            channels=8 if dtsx_bed_71 else max(counts),
            dtsx_bed_71=dtsx_bed_71,
            delay_relative_to_video=self._detect_relative_delay(self.mi_audio_obj),
            fps=self._get_fps(),
            audio_only=False,
            recommended_free_space=self._recommended_free_space(),
            duration=self._get_duration(),
            sample_rate=self._sample_rate(self.mi_audio_obj),
            bit_depth=self.mi_audio_obj.bit_depth,
            thd_atmos=self._is_thd_atmos(),
            adm_atmos_wav=self._is_adm_atmos_wav(),
            lfe=self._has_lfe(),
        )
        if audio_info.thd_atmos:
            audio_info.atmos_elements = self._thd_atmos_elements()
        if self.damf:
            # MediaInfo misreads a CAF file's length
            audio_info.channels = self.damf.channels
            audio_info.duration = self.damf.duration_ms
            audio_info.sample_rate = self.damf.sample_rate
            audio_info.bit_depth = self.damf.bit_depth
            audio_info.recommended_free_space = self.damf.size
            audio_info.damf_atmos = True

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
            raise MediaInfoError(
                f"Selected track #{track_index} does not exist."
            ) from None

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

    def _has_lfe(self) -> bool | None:
        """
        Whether the track has an LFE channel, from MediaInfo's channel layout
        ('L R C Ls Rs' has none) or its channel positions; None when it gives
        neither.
        """
        track = self.mi_audio_obj
        layout = str(getattr(track, "channel_layout", None) or "").split()
        if layout:
            return any(name.upper().startswith("LFE") for name in layout)
        positions = str(getattr(track, "channel_positions", None) or "")
        if positions.strip():
            return "LFE" in positions.upper()
        return None

    def _thd_atmos_elements(self) -> int | None:
        """
        The elements a TrueHD Atmos stream codes: its bed channels plus its
        dynamic objects (an LFE bed and 15 objects are 16), or None when
        MediaInfo doesn't say. The count follows DEE's number_of_elements, not
        the master's; the '16-ch' MediaInfo reports as a feature is the same
        for every stream, so it isn't a count.
        """
        track = self.mi_audio_obj
        try:
            beds = int(track.bed_channel_count)
            objects = int(track.number_of_dynamic_objects)
        except (AttributeError, TypeError, ValueError):
            return None
        return beds + objects

    def _is_adm_atmos_wav(self) -> bool:
        """Check if track is a ADM BWF file."""
        if self.file_input.suffix.lower() != ".wav":
            return False
        adm = getattr(self.mi_audio_obj, "admprofile_format", None)
        if adm and "Atmos" in str(adm):
            return True
        return False

    def generate_output_filename(
        self,
        delay_was_stripped: bool,
        delay_relative_to_video: int,
        suffix: str,
        output_channels: str,
        worker_id: str | None,
    ) -> Path:
        """
        Automatically generate an output file name keeping some attributes.

        Args:
            delay_was_stripped: Whether or not delay was stripped
            delay_relative_to_video: Delay relative to video in container
            suffix: File extension/suffix (".ac3", ".ec3", ".ac4")
            output_channels: Output channel string (1.0, 2.0, etc.)
            worker_id: Optional worker ID for parallel processing (e.g., "f1", "f2")

        Returns:
            Path: Path of a automatically generated filename
        """
        # base directory/name
        base_dir = self.file_input.parent

        # get attributes from guessit
        # if we can't get title from guessit we'll fall back to the base title stripping
        # delay values and cleaning it up
        title = (
            self.guess.get("title")
            if self.guess.get("title")
            else strip_delay_from_file_string_and_cleanse(self.file_input).stem
        )
        year = self.guess.get("year")
        lang = self._get_lang_alpha3(self.guess.get("language"))

        # context extraction
        season = self.guess.get("season")
        episode = self.guess.get("episode")
        source = self._extract_source_info()
        channels = output_channels or ""

        # get attributes from mediainfo
        mi_lang = self._language_detection()

        # delay
        delay = self._delay_detection(delay_was_stripped, delay_relative_to_video)

        # construct new clean path with enhanced context
        name_parts: list[str] = [title or ""]

        # add season/episode info for TV shows
        if season is not None and episode is not None:
            name_parts.append(f"S{season:02d}E{episode:02d}")
        elif season is not None:
            name_parts.append(f"S{season:02d}")

        # add year if available
        if year:
            name_parts.append(str(year))

        # add source and format context in brackets
        context_parts = []
        if source:
            context_parts.append(source)
        lang_str = mi_lang or lang
        if lang_str:
            context_parts.append(lang_str)
        if channels:
            context_parts.append(channels)
        if worker_id:
            context_parts.append(worker_id)

        if context_parts:
            name_parts.append(f"[{'_'.join(context_parts)}]")

        # add delay if present
        if delay:
            name_parts.append(delay)

        new_base_name = " ".join(name_parts)
        return base_dir / Path(str(re.sub(r"\s{2,}", " ", new_base_name)) + suffix)

    def render_output_template(
        self,
        template: str,
        suffix: str,
        output_channels: str,
        delay_was_stripped: bool,
        delay_relative_to_video: int,
        worker_id: str | None = None,
    ) -> Path:
        """
        Render an output filename from a lightweight template using available metadata.

        Supported tokens: {title}, {year}, {stem}, {stem-cleaned}, {source}, {lang}, {channels}, {worker},
        {delay}, and {opt-delay}.

        The method is intentionally small and forgiving: missing tokens are replaced with
        empty strings and values are sanitized for filesystem use. This does not replace the
        existing automatic generation logic; it provides an alternate, opt-in path.
        """
        base_dir = self.file_input.parent

        # token values with sensible fallbacks
        stem = strip_delay_from_file_string_and_cleanse(self.file_input).stem
        stem_cleaned = (
            clean_title(self.file_input.stem) if ("{stem-cleaned}" in template) else ""
        )
        title = self.guess.get("title") or stem
        year = str(self.guess.get("year")) if self.guess.get("year") else ""
        source = self._extract_source_info() or ""
        mi_lang = self._language_detection()
        lang = mi_lang or self._get_lang_alpha3(self.guess.get("language")) or ""
        channels = output_channels or ""
        worker = worker_id or ""

        # delay
        delay = self._delay_detection(delay_was_stripped, delay_relative_to_video)

        mapping = {
            "title": str(title),
            "year": year,
            "stem": stem,
            "stem-cleaned": stem_cleaned,
            "source": str(source),
            "lang": str(lang),
            "channels": str(channels),
            "worker": str(worker),
            "delay": str(delay) if delay else "",
            "opt-delay": "",
        }

        # only include when delay is present and non-zero
        try:
            d_val = mapping.get("delay", "")
            if d_val and not re.match(r"DELAY\s*0", d_val):
                mapping["opt-delay"] = d_val
            else:
                mapping["opt-delay"] = ""
        except Exception:
            mapping["opt-delay"] = ""

        rendered = template
        for key, val in mapping.items():
            # {stem-cleaned} stands in for {stem}
            if key == "stem" and mapping["stem-cleaned"]:
                val = ""
            rendered = rendered.replace(f"{{{key}}}", val)

        # sanitize filename: remove problematic characters
        rendered = re.sub(r"[<>:\"/\\|?*]", "_", rendered)
        # drop the brackets a token left empty ("{title} [{lang}]" with no
        # language), then collapse the whitespace around them
        previous = None
        while previous != rendered:
            previous, rendered = rendered, _EMPTY_BRACKETS.sub("", rendered)
        rendered = re.sub(r"\s{2,}", " ", rendered).strip()
        # a template that renders to nothing is named after the source
        if not rendered:
            rendered = stem

        return base_dir / Path(rendered + suffix)

    def _delay_detection(
        self,
        delay_was_stripped: bool,
        delay_relative_to_video: int,
    ) -> str | None:
        """
        Compute delay string.

        Returns:
            str: Returns a formatted delay string
        """
        # if delay was stripped we don't need to run any logic on delay detection.
        # stripped delay means the encoder will effectively set the delay relative
        # to video to 0.
        if delay_was_stripped:
            return "DELAY 0ms"
        else:
            # if we have 0 delay from the container we'll try to parse it from the filename
            if delay_relative_to_video == 0:
                delay_from_file = parse_delay_from_file(self.file_input)
                return f"DELAY {delay_from_file}" if delay_from_file else None
            # use delay from the container
            else:
                return f"DELAY {delay_relative_to_video}ms"

    def _language_detection(self) -> str | None:
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
            return (
                f"{self.mi_audio_obj.other_language[l_index]}"
                if l_index is not None
                else None
            )

    def _extract_source_info(self) -> str | None:
        """Extract source information from filename or MediaInfo."""
        filename_lower = self.file_input.name.lower()

        # check for common source indicators
        if "remux" in filename_lower:
            return "Remux"
        elif "bluray" in filename_lower or "blu-ray" in filename_lower:
            return "BluRay"
        elif "web-dl" in filename_lower or "webdl" in filename_lower:
            return "WEB-DL"
        elif "webrip" in filename_lower:
            return "WEBRip"
        elif "hdtv" in filename_lower:
            return "HDTV"
        elif "dvd" in filename_lower:
            return "DVD"

        # fallback to filename parsing
        if "truehd" in filename_lower:
            if "atmos" in filename_lower:
                return "TrueHD.Atmos"
            return "TrueHD"
        elif "dts" in filename_lower:
            return "DTS"
        elif "ddp" in filename_lower or "dd+" in filename_lower:
            if "atmos" in filename_lower:
                return "DDP.Atmos"
            return "DDP"
        elif "flac" in filename_lower:
            return "FLAC"

    @staticmethod
    def _get_lang_alpha3(lang: Any) -> str | None:
        """
        Language from guessit can be a list of Language objects or a single Language object.
        We're determining which and getting the alpha3 code if it exists.
        """
        # duck-typed on `alpha3` so babelfish isn't imported at startup
        language = None
        if isinstance(lang, list):
            candidate = lang[0] if lang else None
        else:
            candidate = lang
        if hasattr(candidate, "alpha3"):
            language = candidate
        return language.alpha3 if language else None

    @staticmethod
    def _sample_rate(track: Track) -> int | None:
        """First reported layer rate in Hz. Older DTS:X reports leave the object layer blank."""
        for value in (track.sampling_rate, *(track.other_sampling_rate or ())):
            for layer in str(value).split("/"):
                match = re.fullmatch(
                    r"(\d+(?:\.\d+)?)(k?hz)?", "".join(layer.lower().split())
                )
                if match:
                    rate = float(match[1]) * (1000 if match[2] == "khz" else 1)
                    if rate.is_integer() and rate > 0:
                        return int(rate)
        return None

    @staticmethod
    def _channel_counts(track: Track) -> set[int]:
        """Counts for the presentations and core reported on this track."""
        values = (
            track.channel_s,
            *(track.other_channel_s or ()),
            track.channel_s__original,
        )
        counts = {int(n) for value in values for n in re.findall(r"\d+", str(value))}
        if not counts:
            raise MediaInfoError("MediaInfo did not report an audio channel count.")
        return counts

    @staticmethod
    def get_channels(mi_audio_obj: Track) -> int:
        """Highest reported channel count for the source info display."""
        return max(MediainfoParser._channel_counts(mi_audio_obj))

    @staticmethod
    def _detect_relative_delay(mi_audio_obj: Track) -> int:
        """
        Pretty much all containers store delay in 'delay_relative_to_video' but
        for some reason mp4 stores it in 'source_delay'. We'll attempt to get it from
        both.
        """
        for field in ("delay_relative_to_video", "source_delay"):
            val = getattr(mi_audio_obj, field, None)
            if val is None:
                continue
            try:
                return int(val)
            except (TypeError, ValueError):
                continue
        return 0

    @staticmethod
    def get_track_by_stream_index(mi: MediaInfo, idx: int) -> Track:
        """Get track by FFMPEG style stream index (+1 to skip general track)."""
        return mi.tracks[idx + 1]
