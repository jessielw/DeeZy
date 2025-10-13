import json
from copy import deepcopy
from pathlib import Path

from deezy.audio_encoders.dee.json.ac4_base import ac4_base
from deezy.audio_encoders.dee.json.atmos_base import atmos_base
from deezy.audio_encoders.dee.json.dd_base import dd_base
from deezy.enums.atmos import AtmosMode
from deezy.enums.codec_format import CodecFormat
from deezy.enums.dd import DolbyDigitalChannels
from deezy.enums.shared import DDEncodingMode, DeeDelay, DeeFPS, StereoDownmix
from deezy.payloads.ac4 import Ac4Payload
from deezy.payloads.atmos import AtmosPayload
from deezy.payloads.dd import DDPayload
from deezy.payloads.ddp import DDPPayload
from deezy.utils.utils import clean_string


class DeeJSONGenerator:
    """Handles the creation of JSON files for DEE encoding"""

    __slots__ = (
        "input_file_path",
        "output_file_path",
        "output_dir",
        "codec_format",
    )

    def __init__(
        self,
        input_file_path: Path,
        output_file_path: Path,
        output_dir: Path,
        codec_format: CodecFormat,
    ) -> None:
        """
        Args:
            input_file_path (Path): Input file path.
            output_file_path (Path): Output file path.
            output_dir (Path | str): File path only.
            codec_format (CodecFormat): Current codec format.
        """
        self.input_file_path = input_file_path
        self.output_file_path = output_file_path
        self.output_dir = output_dir
        self.codec_format = codec_format

    def dd_json(
        self,
        payload: DDPayload | DDPPayload,
        downmix_mode_off: bool,
        bitrate: int,
        fps: DeeFPS,
        delay: DeeDelay | None,
        temp_dir: Path,
        dd_mode: DDEncodingMode,
    ) -> Path:
        """Set up DD encoding."""
        # init base
        json_base = deepcopy(dd_base)

        #### input section ####
        input_section = json_base["job_config"]["input"]["audio"]["wav"]
        input_section["file_name"] = self._create_dee_file_path(self.input_file_path)
        input_section["timecode_frame_rate"] = fps.to_dee_cmd()

        #### filter section ####
        filter_section = json_base["job_config"]["filter"]["audio"]["pcm_to_ddp"]
        loudness = filter_section["loudness"]["measure_only"]
        loudness["metering_mode"] = payload.metering_mode.to_dee_cmd()
        loudness["dialogue_intelligence"] = payload.dialogue_intelligence
        loudness["speech_threshold"] = payload.speech_threshold
        filter_section["encoder_mode"] = dd_mode.get_encoder_mode()
        if not downmix_mode_off:
            filter_section["downmix_config"] = payload.channels.to_dee_cmd()
        else:
            filter_section["downmix_config"] = DolbyDigitalChannels.AUTO.to_dee_cmd()
        if delay:
            filter_section[delay.MODE.value] = delay.DELAY
        filter_section["data_rate"] = bitrate
        filter_section["timecode_frame_rate"] = fps.to_dee_cmd()
        drc = filter_section["drc"]
        drc["line_mode_drc_profile"] = payload.drc_line_mode.to_dee_cmd()
        drc["rf_mode_drc_profile"] = payload.drc_rf_mode.to_dee_cmd()
        filter_section["lfe_lowpass_filter"] = payload.lfe_lowpass_filter
        filter_section["surround_90_degree_phase_shift"] = (
            payload.surround_90_degree_phase_shift
        )
        filter_section["surround_3db_attenuation"] = payload.surround_3db_attenuation
        downmix = filter_section["downmix"]
        downmix["loro_center_mix_level"] = payload.loro_center_mix_level
        downmix["loro_surround_mix_level"] = payload.loro_surround_mix_level
        downmix["ltrt_center_mix_level"] = payload.ltrt_center_mix_level
        downmix["ltrt_surround_mix_level"] = payload.ltrt_surround_mix_level
        if not downmix_mode_off:
            downmix["preferred_downmix_mode"] = (
                payload.preferred_downmix_mode.to_dee_cmd()
            )
        else:
            downmix["preferred_downmix_mode"] = StereoDownmix.NOT_INDICATED.to_dee_cmd()
        filter_section["custom_dialnorm"] = payload.custom_dialnorm

        #### output section ####
        output_section = json_base["job_config"]["output"]
        if dd_mode.get_output_mode() == "ac3":
            output_section["ac3"]["file_name"] = self._create_dee_file_path(
                self.output_file_path
            )
            del output_section["ec3"]
        else:
            output_section["ec3"]["file_name"] = self._create_dee_file_path(
                self.output_file_path
            )
            del output_section["ac3"]

        #### misc section ####
        misc_section = json_base["job_config"]["misc"]
        # string bool lowered (true/false) - DEE expects clean_temp to be "true" when
        misc_section["temp_dir"]["clean_temp"] = "true"
        misc_section["temp_dir"]["path"] = self._create_dee_file_path(temp_dir)

        return self._write_json(json_base)

    def atmos_json(
        self,
        payload: AtmosPayload,
        bitrate: int,
        fps: DeeFPS,
        delay: DeeDelay | None,
        temp_dir: Path,
        atmos_mode: AtmosMode,
    ) -> Path:
        """Set up Atmos encoding."""
        # init base
        json_base = deepcopy(atmos_base)

        #### input section ####
        input_section = json_base["job_config"]["input"]["audio"]["atmos_mezz"]
        input_section["file_name"] = self._create_dee_file_path(self.input_file_path)
        input_section["timecode_frame_rate"] = fps.to_dee_cmd()

        #### filter section ####
        filter_section = json_base["job_config"]["filter"]["audio"][
            "encode_to_atmos_ddp"
        ]
        loudness = filter_section["loudness"]["measure_only"]
        loudness["metering_mode"] = payload.metering_mode.to_dee_cmd()
        loudness["dialogue_intelligence"] = payload.dialogue_intelligence
        loudness["speech_threshold"] = payload.speech_threshold
        filter_section["data_rate"] = bitrate
        if delay:
            filter_section[delay.MODE.value] = delay.DELAY
        filter_section["timecode_frame_rate"] = fps.to_dee_cmd()
        drc = filter_section["drc"]
        drc["line_mode_drc_profile"] = payload.drc_line_mode.to_dee_cmd()
        drc["rf_mode_drc_profile"] = payload.drc_rf_mode.to_dee_cmd()
        downmix = filter_section["downmix"]
        downmix["loro_center_mix_level"] = payload.loro_center_mix_level
        downmix["loro_surround_mix_level"] = payload.loro_surround_mix_level
        downmix["ltrt_center_mix_level"] = payload.ltrt_center_mix_level
        downmix["ltrt_surround_mix_level"] = payload.ltrt_surround_mix_level
        downmix["preferred_downmix_mode"] = payload.preferred_downmix_mode.to_dee_cmd()
        filter_section["custom_dialnorm"] = payload.custom_dialnorm

        # add encoding_backend and encoder mode if atmos 7.1 (bluray)
        if atmos_mode is AtmosMode.BLURAY:
            filter_section["encoding_backend"] = "atmosprocessor"
            filter_section["encoder_mode"] = "bluray"

        #### output section ####
        output_section = json_base["job_config"]["output"]
        output_section["ec3"]["file_name"] = self._create_dee_file_path(
            self.output_file_path
        )

        #### misc section ####
        misc_section = json_base["job_config"]["misc"]
        # string bool lowered (true/false) - DEE expects clean_temp to be "true" when
        misc_section["temp_dir"]["clean_temp"] = "true"
        misc_section["temp_dir"]["path"] = self._create_dee_file_path(temp_dir)

        return self._write_json(json_base)

    def ac4_json(
        self,
        payload: Ac4Payload,
        bitrate: int,
        fps: DeeFPS,
        delay: DeeDelay | None,
        temp_dir: Path,
        atmos_enabled: bool,
    ) -> Path:
        """Set up AC4 encoding."""
        # init base
        json_base = deepcopy(ac4_base)

        #### input section ####
        if atmos_enabled:
            input_section = json_base["job_config"]["input"]["audio"]["atmos_mezz"]
            del json_base["job_config"]["input"]["audio"]["wav"]
        else:
            input_section = json_base["job_config"]["input"]["audio"]["wav"]
            del json_base["job_config"]["input"]["audio"]["atmos_mezz"]
        input_section["file_name"] = self._create_dee_file_path(self.input_file_path)
        input_section["timecode_frame_rate"] = fps.to_dee_cmd()

        #### filter section ####
        filter_section = json_base["job_config"]["filter"]["audio"]["encode_to_ims_ac4"]
        filter_section["timecode_frame_rate"] = fps.to_dee_cmd()
        if delay:
            filter_section[delay.MODE.value] = delay.DELAY
        loudness = filter_section["loudness"]["measure_only"]
        loudness["metering_mode"] = payload.metering_mode.to_dee_cmd()
        loudness["dialogue_intelligence"] = payload.dialogue_intelligence
        loudness["speech_threshold"] = payload.speech_threshold
        filter_section["data_rate"] = bitrate
        filter_section["ac4_frame_rate"] = "native"
        filter_section["ims_legacy_presentation"] = str(
            payload.ims_legacy_presentation
        ).lower()
        filter_section["iframe_interval"] = 0
        filter_section["encoding_profile"] = payload.encoding_profile.to_dee_cmd()
        drc = filter_section["drc"]
        drc["ddp_drc_profile"] = payload.ddp_drc.to_dee_cmd()
        drc["flat_panel_drc_profile"] = payload.flat_panel_drc.to_dee_cmd()
        drc["home_theatre_drc_profile"] = payload.home_theatre_drc.to_dee_cmd()
        drc["portable_hp_drc_profile"] = payload.portable_headphones_drc.to_dee_cmd()
        drc["portable_spkr_drc_profile"] = payload.portable_speakers_drc.to_dee_cmd()

        #### output section ####
        output_section = json_base["job_config"]["output"]
        output_section["ac4"]["file_name"] = self._create_dee_file_path(
            self.output_file_path
        )

        #### misc section ####
        misc_section = json_base["job_config"]["misc"]
        # string bool lowered (true/false) - DEE expects clean_temp to be "true" when
        misc_section["temp_dir"]["clean_temp"] = "true"
        misc_section["temp_dir"]["path"] = self._create_dee_file_path(temp_dir)

        return self._write_json(json_base)

    def _write_json(self, json_base: dict) -> Path:
        if not json_base:
            raise ValueError("Missing or invalid json base")
        file_out = (
            self.output_dir
            / f"{clean_string(self.output_file_path.stem)}.{self.codec_format}.json"
        )
        with open(file_out, "w") as json_file:
            json.dump(json_base, json_file, indent=2)
        return file_out

    @staticmethod
    def _create_dee_file_path(path: Path) -> str:
        """DEE expects file paths quoted."""
        return f'"{path}"' if isinstance(path, Path) else f'"{Path(path)}"'
