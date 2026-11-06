from pathlib import Path

from deezy.audio_encoders.dee.backends.base import DeeBackend, DeeJobFiles
from deezy.enums.ac4 import Ac4EncodingProfile
from deezy.enums.atmos import AtmosMode
from deezy.enums.shared import (
    DDEncodingMode,
    DeeDelay,
    DeeDelayModes,
    DeeFPS,
    MeteringMode,
    StereoDownmix,
)
from deezy.exceptions import UnsupportedDeeFeatureError
from deezy.payloads.ac4 import Ac4Payload
from deezy.payloads.atmos import AtmosPayload
from deezy.payloads.dd import DDPayload
from deezy.payloads.ddp import DDPPayload
from deezy.payloads.shared import LoudnessPayload
from deezy.utils.dependencies import split_dee_tool
from deezy.utils.logger import logger
from deezy.utils.paths import long_path_str

DDP_TOOL = "dee_ddp_encoder"
DDP_JOC_TOOL = "dee_ddpjoc_encoder"
AC4_IMS_TOOL = "dee_ac4ims_encoder"


def _flag(value: bool) -> str:
    return "1" if value else "0"


def _options(options: dict[str, str]) -> str:
    """DEE's `key=value:key=value` option list."""
    return ":".join(f"{key}={value}" for key, value in options.items())


class SplitDeeBackend(DeeBackend):
    """
    The per-codec DEE encoder executables, driven by command line options.

    ``dee_path`` is the folder holding them. Options these tools do not offer
    raise `UnsupportedDeeFeatureError` rather than being silently dropped, so
    an encode never comes out different from what was asked for.
    """

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
        if dd_mode in (DDEncodingMode.BLURAY, DDEncodingMode.DDP71):
            # the tool only offers mono, stereo and 5.1 output layouts and would
            # quietly hand back a 5.1 stream for a 7.1 request
            raise UnsupportedDeeFeatureError(
                "Dolby Digital Plus 7.1 encoding (including Blu-ray) is not "
                "available with the split DEE encoders. Use a DEE that provides "
                "the single 'dee' executable."
            )
        self._reject_custom_dialnorm(payload)

        encoder = {
            "drc_profile_line": payload.drc_line_mode.to_dee_cmd(),
            "drc_profile_rf": payload.drc_rf_mode.to_dee_cmd(),
            "lfe_filter": _flag(payload.lfe_lowpass_filter),
            "surround_90deg_phase_shift": _flag(payload.surround_90_degree_phase_shift),
            "surround_3dB_attenuation": _flag(payload.surround_3db_attenuation),
            "preferred_downmix_mode": (
                StereoDownmix.NOT_INDICATED
                if downmix_mode_off
                else payload.preferred_downmix_mode
            ).to_dee_cmd(),
            "loro_cmix": payload.loro_center_mix_level,
            "loro_smix": payload.loro_surround_mix_level,
            "ltrt_cmix": payload.ltrt_center_mix_level,
            "ltrt_smix": payload.ltrt_surround_mix_level,
        }
        mode = "dd" if dd_mode is DDEncodingMode.DD else "ddp"

        # the JSON flow calls "no downmix" 'off', the command line calls it 'auto'
        channels = "off" if downmix_mode_off else payload.channels.to_dee_cmd()
        if channels == "off":
            channels = "auto"

        return [
            *self._common_args(
                DDP_TOOL,
                files,
                input_format="wav",
                temp_dir=True,
                bitrate=bitrate,
                fps=fps,
                delay=delay,
                payload=payload,
            ),
            "-c",
            channels,
            "-e",
            f"{mode}:{_options(encoder)}",
        ]

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
        if atmos_mode is AtmosMode.BLURAY:
            raise UnsupportedDeeFeatureError(
                "Blu-ray (7.1) Atmos encoding is not available with the split DEE "
                "encoders. Use a DEE that provides the single 'dee' executable."
            )
        self._reject_custom_dialnorm(payload)

        encoder = {
            "preferred_downmix_mode": payload.preferred_downmix_mode.to_dee_cmd(),
            "loro_cmix": payload.loro_center_mix_level,
            "loro_smix": payload.loro_surround_mix_level,
            "ltrt_cmix": payload.ltrt_center_mix_level,
            "ltrt_smix": payload.ltrt_surround_mix_level,
            "drc_profile_line": payload.drc_line_mode.to_dee_cmd(),
            "drc_profile_rf": payload.drc_rf_mode.to_dee_cmd(),
        }
        return [
            *self._common_args(
                DDP_JOC_TOOL,
                files,
                input_format="atmos_mezz",
                bitrate=bitrate,
                fps=fps,
                delay=delay,
                payload=payload,
            ),
            "-e",
            _options(encoder),
        ]

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
        if payload.ims_legacy_presentation:
            # kept for backwards compatibility with commands written for the
            # single 'dee' executable; the split encoder has no such option
            logger.warning(
                "--ims-legacy-presentation is not available with the split DEE "
                "encoders and will be ignored."
            )
        if payload.encoding_profile is not Ac4EncodingProfile.IMS:
            raise UnsupportedDeeFeatureError(
                f"--encoding-profile {payload.encoding_profile} is not available "
                "with the split DEE encoders."
            )

        encoder = {
            "drc_profile_ddp": payload.ddp_drc.to_dee_cmd(),
            "drc_profile_flat_panel": payload.flat_panel_drc.to_dee_cmd(),
            "drc_profile_home_theatre": payload.home_theatre_drc.to_dee_cmd(),
            "drc_profile_portable_hp": payload.portable_headphones_drc.to_dee_cmd(),
            "drc_profile_portable_spkr": payload.portable_speakers_drc.to_dee_cmd(),
        }
        return [
            *self._common_args(
                AC4_IMS_TOOL,
                files,
                input_format="atmos_mezz" if atmos_enabled else "wav",
                bitrate=bitrate,
                fps=fps,
                delay=delay,
                payload=payload,
            ),
            "-e",
            _options(encoder),
        ]

    def _common_args(
        self,
        tool: str,
        files: DeeJobFiles,
        *,
        input_format: str,
        bitrate: int,
        fps: DeeFPS,
        delay: DeeDelay | None,
        payload: LoudnessPayload,
        temp_dir: bool = False,
    ) -> list[str]:
        """
        Options every split encoder takes, in a stable order.

        ``temp_dir`` is for the encoders that have a ``--temp-dir`` option
        (only the DDP one does); the others manage their temp files themselves.
        """
        return [
            str(split_dee_tool(Path(self.dee_path), tool)),
            # replaced with the active log level when the job is run
            "--loglevel",
            "info",
            "--progress",
            "1",
            # DEE only ever writes into the job's own temp directory
            "--overwrite",
            "1",
            *(["--temp-dir", long_path_str(files.temp_dir)] if temp_dir else []),
            "--input-format",
            input_format,
            "-i",
            long_path_str(files.input_file),
            "-o",
            long_path_str(files.output_file),
            "--timecode-frame-rate",
            fps.to_dee_cmd(),
            *self._delay_args(delay),
            "--data-rate",
            str(bitrate),
            "--loudness-management",
            self._loudness(payload),
        ]

    @staticmethod
    def _delay_args(delay: DeeDelay | None) -> list[str]:
        if not delay:
            return []
        seconds = f"{delay.to_seconds():.6f}"
        if delay.MODE is DeeDelayModes.NEGATIVE:
            # trim the start of the audio
            return ["--start", seconds]
        # prepend silence, nothing appended
        return ["--add-silence", f"{seconds}:0"]

    @staticmethod
    def _loudness(payload: LoudnessPayload) -> str:
        # these encoders measure to ITU-R BS.1770-4 only
        if payload.metering_mode is not MeteringMode.MODE_1770_4:
            logger.info(
                f"Metering mode {payload.metering_mode} is not offered by the split "
                "DEE encoders, measuring with 1770-4."
            )
        return "measure_only:" + _options(
            {
                "preset": "manual",
                "dialogue_intelligence": _flag(payload.dialogue_intelligence),
                "speech_threshold": str(payload.speech_threshold),
            }
        )

    @staticmethod
    def _reject_custom_dialnorm(payload: LoudnessPayload) -> None:
        if int(getattr(payload, "custom_dialnorm", 0) or 0) != 0:
            raise UnsupportedDeeFeatureError(
                "--custom-dialnorm is not available with the split DEE encoders. "
                "Use a DEE that provides the single 'dee' executable."
            )
