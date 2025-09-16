import argparse
from dataclasses import dataclass

from deezy.enums.shared import TrackType


@dataclass(slots=True, frozen=True)
class TrackIndex:
    """
    Represents a track index with optional track type prefix.

    Supports FFmpeg-style notation:
    - a:N (audio track N - like ffmpeg 0:a:N)
    - s:N (stream index N - like ffmpeg 0:N, any track type)
    - N (defaults to a:N - audio track N)

    Attributes:
        track_type: The type of track (audio, stream)
        index: The zero-based index of the track
    """

    track_type: TrackType
    index: int

    def __str__(self) -> str:
        """Return FFmpeg-style string representation."""
        return f"{self.track_type.value}:{self.index}"

    def __post_init__(self) -> None:
        """Validate track index after initialization."""
        if self.index < 0:
            raise ValueError(f"Track index must be non-negative, got {self.index}")

    @classmethod
    def from_string(cls, value: str) -> "TrackIndex":
        """
        Parse track index from string input.

        Args:
            value: Input string (e.g., "a:2", "s:1", "3")

        Returns:
            TrackIndex object

        Raises:
            argparse.ArgumentTypeError: If input format is invalid
        """
        value = value.strip()

        if ":" in value:
            # handle "a:N" or "s:N" format
            parts = value.split(":", 1)
            if len(parts) != 2:
                raise argparse.ArgumentTypeError(
                    f"Invalid track format '{value}'. Expected 'a:N', 's:N', or 'N'"
                )

            track_type_str, index_str = parts

            # validate track type
            try:
                track_type = TrackType(track_type_str)
            except ValueError:
                valid_types = ", ".join([f"'{t.value}'" for t in TrackType])
                raise argparse.ArgumentTypeError(
                    f"Invalid track type '{track_type_str}'. Valid types: {valid_types}"
                )

            # validate index
            try:
                index = int(index_str)
                if index < 0:
                    raise argparse.ArgumentTypeError(
                        f"Track index must be non-negative, got {index}"
                    )
            except ValueError:
                raise argparse.ArgumentTypeError(
                    f"Invalid track index '{index_str}'. Must be a number"
                )
        else:
            # handle plain number format (defaults to audio)
            try:
                index = int(value)
                if index < 0:
                    raise argparse.ArgumentTypeError(
                        f"Track index must be non-negative, got {index}"
                    )
                track_type = TrackType.AUDIO  # default to audio
            except ValueError:
                raise argparse.ArgumentTypeError(
                    f"Invalid track index '{value}'. Expected 'a:N', 's:N',  or 'N'"
                )

        return cls(track_type=track_type, index=index)

    @classmethod
    def audio(cls, index: int) -> "TrackIndex":
        """Create an audio track index."""
        return cls(track_type=TrackType.AUDIO, index=index)

    @classmethod
    def stream(cls, index: int) -> "TrackIndex":
        """Create a stream track index (any track type by stream index)."""
        return cls(track_type=TrackType.STREAM, index=index)
