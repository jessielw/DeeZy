"""Bitrate syntax shared by the CLI, config and encoder commands."""

from dataclasses import dataclass
import re

AC3_CORE_RATES = (224, 256, 320, 384, 448, 512, 576, 640)


class InvalidBitrateError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SubstreamBitrate:
    independent: int
    dependent: int

    def __post_init__(self) -> None:
        if not all(32 <= rate <= 1024 for rate in (self.independent, self.dependent)):
            raise InvalidBitrateError("Each substream takes 32 to 1024 kbps.")

    @classmethod
    def parse(cls, value: str) -> "SubstreamBitrate":
        if not re.fullmatch(r"[0-9]+:[0-9]+", value):
            raise InvalidBitrateError("Expected two whole kbps values as R0:R1.")
        independent, dependent = value.split(":")
        return cls(int(independent), int(dependent))

    def __str__(self) -> str:
        return f"{self.independent}:{self.dependent}"

    def check_core(self, *, bluray: bool) -> None:
        if bluray and self.independent not in AC3_CORE_RATES:
            choices = ", ".join(map(str, AC3_CORE_RATES))
            raise InvalidBitrateError(f"The Blu-ray AC-3 core takes {choices} kbps.")


Bitrate = int | SubstreamBitrate


def parse_bitrate(value: str) -> Bitrate:
    if ":" not in value:
        return int(value)
    return SubstreamBitrate.parse(value)


def total_bitrate(value: Bitrate) -> int:
    if isinstance(value, SubstreamBitrate):
        raise InvalidBitrateError(
            f"Split bitrate {value} requires two output substreams."
        )
    return value


def split_core(fmt: str, key: str) -> str | None:
    """Core codec for an output layout or Atmos mode that accepts a split."""
    if (fmt, key) in (("ddp", "surroundex"), ("ddp-atmos", "standard")):
        return "E-AC-3"
    if (fmt, key) in (("ddp-bluray", "surroundex"), ("ddp-atmos", "bluray")):
        return "AC-3"
    return None
