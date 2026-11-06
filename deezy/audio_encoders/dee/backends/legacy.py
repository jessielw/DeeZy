from deezy.audio_encoders.dee.backends.base import DeeBackend, DeeJobFiles
from deezy.audio_encoders.dee.json.dee_json_generator import DeeJSONGenerator
from deezy.enums.atmos import AtmosMode
from deezy.enums.shared import DDEncodingMode, DeeDelay, DeeFPS
from deezy.payloads.ac4 import Ac4Payload
from deezy.payloads.atmos import AtmosPayload
from deezy.payloads.dd import DDPayload
from deezy.payloads.ddp import DDPPayload
from deezy.utils.logger import logger
from deezy.utils.paths import long_path_str


class LegacyDeeBackend(DeeBackend):
    """The single ``dee`` executable, driven by a JSON job file."""

    __slots__ = ()

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
        json_path = self._generator(files).dd_json(
            payload=payload,
            downmix_mode_off=downmix_mode_off,
            bitrate=bitrate,
            fps=fps,
            delay=delay,
            temp_dir=files.temp_dir,
            dd_mode=dd_mode,
        )
        return self._json_command(json_path)

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
        json_path = self._generator(files).atmos_json(
            payload=payload,
            bitrate=bitrate,
            fps=fps,
            delay=delay,
            temp_dir=files.temp_dir,
            atmos_mode=atmos_mode,
        )
        return self._json_command(json_path)

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
        json_path = self._generator(files).ac4_json(
            payload=payload,
            bitrate=bitrate,
            fps=fps,
            delay=delay,
            temp_dir=files.temp_dir,
            atmos_enabled=atmos_enabled,
        )
        return self._json_command(json_path)

    @staticmethod
    def _generator(files: DeeJobFiles) -> DeeJSONGenerator:
        return DeeJSONGenerator(
            input_file_path=files.input_file,
            output_file_path=files.output_file,
            output_dir=files.temp_dir,
            codec_format=files.codec_format,
            job_name=files.job_name,
        )

    def _json_command(self, json_path) -> list[str]:
        logger.debug(f"{json_path=}.")
        return [
            str(self.dee_path),
            "--progress-interval",
            "500",
            "--diagnostics-interval",
            "90000",
            "--verbose",
            "-j",
            long_path_str(json_path),
        ]
