import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from deezy.enums.ac4 import Ac4EncodingProfile
from deezy.enums.atmos import AtmosMode, WarpMode
from deezy.enums.shared import DeeDRC, MeteringMode, StereoDownmix
from deezy.payloads.ac4 import Ac4Payload
from deezy.payloads.atmos import AtmosPayload
from deezy.payloads.dd import DDPayload
from deezy.payloads.ddp import DDPPayload


@dataclass(slots=True)
class PayloadBuilder:
    """Helper class to build payloads from CLI arguments safely."""

    @staticmethod
    def safe_get(args: argparse.Namespace, attr: str, default: Any = None) -> Any:
        """Safely get attribute from args namespace."""
        return getattr(args, attr, default)

    @classmethod
    def _build_core_fields(
        cls,
        args: argparse.Namespace,
        file_input: Path,
        ffmpeg_path: Path,
        truehdd_path: Path | None,
        dee_path: Path,
    ) -> dict:
        """Build core fields common to all payloads."""
        return {
            "no_progress_bars": cls.safe_get(args, "no_progress_bars", False),
            "ffmpeg_path": ffmpeg_path,
            "truehdd_path": truehdd_path,
            "dee_path": dee_path,
            "file_input": file_input,
            "track_index": cls.safe_get(args, "track_index", 0),
            "bitrate": cls.safe_get(args, "bitrate"),
            "temp_dir": Path(args.temp_dir) if cls.safe_get(args, "temp_dir") else None,
            "delay": cls.safe_get(args, "delay"),
            "reuse_temp_files": cls.safe_get(args, "reuse_temp_files", False),
            # keep_temp is automatically enabled when reuse_temp_files is requested
            "keep_temp": cls.safe_get(args, "keep_temp", False)
            or cls.safe_get(args, "reuse_temp_files", False),
            "file_output": Path(args.output) if cls.safe_get(args, "output") else None,
            "output_template": cls.safe_get(args, "output_template"),
            "output_preview": cls.safe_get(args, "output_preview", False),
            "worker_id": cls.safe_get(args, "worker_id"),
            "batch_output_dir": Path(cls.safe_get(args, "batch_output_dir"))
            if cls.safe_get(args, "batch_output_dir")
            else None,
            "overwrite": cls.safe_get(args, "overwrite", False),
        }

    @classmethod
    def _build_loudness_fields(
        cls,
        args: argparse.Namespace,
        default_metering: MeteringMode = MeteringMode.MODE_1770_3,
    ) -> dict:
        """Build loudness fields."""
        return {
            "metering_mode": cls.safe_get(args, "metering_mode", default_metering),
            "dialogue_intelligence": cls.safe_get(
                args, "no_dialogue_intelligence", True
            ),
            "speech_threshold": cls.safe_get(args, "speech_threshold", 15),
        }

    @classmethod
    def _build_dolby_fields(cls, args: argparse.Namespace) -> dict:
        """Build Dolby-specific fields."""
        return {
            "drc_line_mode": cls.safe_get(args, "drc_line_mode", DeeDRC.FILM_LIGHT),
            "drc_rf_mode": cls.safe_get(args, "drc_rf_mode", DeeDRC.FILM_LIGHT),
            "custom_dialnorm": int(cls.safe_get(args, "custom_dialnorm", 0)),
        }

    @classmethod
    def _build_stereo_mix_fields(cls, args: argparse.Namespace) -> dict:
        """Build stereo mix fields for DD/DDP."""
        return {
            "stereo_mix": cls.safe_get(args, "stereo_down_mix", StereoDownmix.LORO),
            "lfe_lowpass_filter": cls.safe_get(args, "no_low_pass_filter", True),
            "surround_90_degree_phase_shift": cls.safe_get(
                args, "no_surround_3db", True
            ),
            "surround_3db_attenuation": cls.safe_get(
                args, "no_surround_90_deg_phase_shift", True
            ),
            "loro_center_mix_level": cls.safe_get(args, "lo_ro_center", "-3"),
            "loro_surround_mix_level": cls.safe_get(args, "lo_ro_surround", "-3"),
            "ltrt_center_mix_level": cls.safe_get(args, "lt_rt_center", "-3"),
            "ltrt_surround_mix_level": cls.safe_get(args, "lt_rt_surround", "-3"),
            "preferred_downmix_mode": cls.safe_get(
                args, "stereo_down_mix", StereoDownmix.LORO
            ),
            "upmix_50_to_51": cls.safe_get(args, "upmix_50_to_51", False),
        }

    @classmethod
    def _build_downmix_only_fields(cls, args: argparse.Namespace) -> dict:
        """Build downmix metadata fields for Atmos."""
        return {
            "loro_center_mix_level": cls.safe_get(args, "lo_ro_center", "-3"),
            "loro_surround_mix_level": cls.safe_get(args, "lo_ro_surround", "-3"),
            "ltrt_center_mix_level": cls.safe_get(args, "lt_rt_center", "-3"),
            "ltrt_surround_mix_level": cls.safe_get(args, "lt_rt_surround", "-3"),
            "preferred_downmix_mode": cls.safe_get(
                args, "stereo_down_mix", StereoDownmix.LORO
            ),
        }

    @classmethod
    def build_dd_payload(
        cls,
        args: argparse.Namespace,
        file_input: Path,
        ffmpeg_path: Path,
        truehdd_path: Path | None,
        dee_path: Path,
    ) -> DDPayload:
        """Build DD payload from args."""
        payload_data = {}
        payload_data.update(
            cls._build_core_fields(
                args, file_input, ffmpeg_path, truehdd_path, dee_path
            )
        )
        payload_data.update(cls._build_loudness_fields(args))
        payload_data.update(cls._build_dolby_fields(args))
        payload_data.update(cls._build_stereo_mix_fields(args))
        payload_data["channels"] = cls.safe_get(args, "channels")

        return DDPayload(**payload_data)

    @classmethod
    def build_ddp_payload(
        cls,
        args: argparse.Namespace,
        file_input: Path,
        ffmpeg_path: Path,
        truehdd_path: Path | None,
        dee_path: Path,
    ) -> DDPPayload:
        """Build DDP payload from args."""
        payload_data = {}
        payload_data.update(
            cls._build_core_fields(
                args, file_input, ffmpeg_path, truehdd_path, dee_path
            )
        )
        payload_data.update(cls._build_loudness_fields(args))
        payload_data.update(cls._build_dolby_fields(args))
        payload_data.update(cls._build_stereo_mix_fields(args))
        payload_data["channels"] = cls.safe_get(args, "channels")

        return DDPPayload(**payload_data)

    @classmethod
    def build_atmos_payload(
        cls,
        args: argparse.Namespace,
        file_input: Path,
        ffmpeg_path: Path,
        truehdd_path: Path | None,
        dee_path: Path,
    ) -> AtmosPayload:
        """Build Atmos payload from args."""
        payload_data = {}
        payload_data.update(
            cls._build_core_fields(
                args, file_input, ffmpeg_path, truehdd_path, dee_path
            )
        )
        payload_data.update(cls._build_loudness_fields(args, MeteringMode.MODE_1770_4))
        payload_data.update(cls._build_dolby_fields(args))
        payload_data.update(cls._build_downmix_only_fields(args))

        # Atmos-specific fields
        payload_data.update(
            {
                "atmos_mode": cls.safe_get(args, "atmos_mode", AtmosMode.STREAMING),
                "thd_warp_mode": cls.safe_get(args, "thd_warp_mode", WarpMode.NORMAL),
                "bed_conform": cls.safe_get(args, "bed_conform", False),
            }
        )

        return AtmosPayload(**payload_data)

    @classmethod
    def build_ac4_payload(
        cls,
        args: argparse.Namespace,
        file_input: Path,
        ffmpeg_path: Path,
        truehdd_path: Path | None,
        dee_path: Path,
    ) -> Ac4Payload:
        """Build AC4 payload from args."""
        payload_data = {}
        payload_data.update(
            cls._build_core_fields(
                args, file_input, ffmpeg_path, truehdd_path, dee_path
            )
        )
        payload_data.update(cls._build_loudness_fields(args, MeteringMode.MODE_1770_4))

        # AC4-specific fields
        payload_data.update(
            {
                "thd_warp_mode": cls.safe_get(args, "thd_warp_mode", WarpMode.NORMAL),
                "bed_conform": cls.safe_get(args, "bed_conform", False),
                "ims_legacy_presentation": cls.safe_get(
                    args, "ims_legacy_presentation", False
                ),
                "encoding_profile": cls.safe_get(
                    args, "encoding_profile", Ac4EncodingProfile.IMS
                ),
                "ddp_drc": cls.safe_get(args, "ddp_drc", DeeDRC.FILM_LIGHT),
                "flat_panel_drc": cls.safe_get(
                    args, "flat_panel_drc", DeeDRC.FILM_LIGHT
                ),
                "home_theatre_drc": cls.safe_get(
                    args, "home_theatre_drc", DeeDRC.FILM_LIGHT
                ),
                "portable_headphones_drc": cls.safe_get(
                    args, "portable_headphones_drc", DeeDRC.FILM_LIGHT
                ),
                "portable_speakers_drc": cls.safe_get(
                    args, "portable_speakers_drc", DeeDRC.FILM_LIGHT
                ),
            }
        )

        return Ac4Payload(**payload_data)
