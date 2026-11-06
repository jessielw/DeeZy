from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from deezy.enums.atmos import AtmosMode
from deezy.enums.codec_format import CodecFormat
from deezy.enums.shared import DDEncodingMode, DeeDelay, DeeFPS
from deezy.payloads.ac4 import Ac4Payload
from deezy.payloads.atmos import AtmosPayload
from deezy.payloads.dd import DDPayload
from deezy.payloads.ddp import DDPPayload


@dataclass(frozen=True, slots=True)
class DeeJobFiles:
    """The files and folders one DEE job works with."""

    input_file: Path
    # where DEE encodes to (inside the temp directory)
    output_file: Path
    temp_dir: Path
    # shared stem for this job's temp artifacts
    job_name: str
    codec_format: CodecFormat


class DeeBackend(ABC):
    """
    Turns an encode job into the command line for one flavour of DEE.

    Encoders decide *what* to encode (channels, bitrate, delay, input prep);
    a backend only decides *how to ask DEE* for it, so the same encoder code
    drives both the single ``dee`` executable (JSON job files) and the split
    per-codec encoder executables (command line options).
    """

    __slots__ = ("dee_path",)

    def __init__(self, dee_path: Path) -> None:
        self.dee_path = dee_path

    @abstractmethod
    def dd_command(
        self,
        payload: DDPayload | DDPPayload,
        files: DeeJobFiles,
        *,
        downmix_mode_off: bool,
        bitrate: int,
        fps: DeeFPS,
        delay: DeeDelay | None,
        dd_mode: DDEncodingMode,
    ) -> list[str]:
        """Command for a Dolby Digital / Dolby Digital Plus encode."""

    @abstractmethod
    def atmos_command(
        self,
        payload: AtmosPayload,
        files: DeeJobFiles,
        *,
        bitrate: int,
        fps: DeeFPS,
        delay: DeeDelay | None,
        atmos_mode: AtmosMode,
    ) -> list[str]:
        """Command for a Dolby Digital Plus Atmos (JOC) encode."""

    @abstractmethod
    def ac4_command(
        self,
        payload: Ac4Payload,
        files: DeeJobFiles,
        *,
        bitrate: int,
        fps: DeeFPS,
        delay: DeeDelay | None,
        atmos_enabled: bool,
    ) -> list[str]:
        """Command for an immersive stereo AC-4 encode."""
