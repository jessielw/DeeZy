from copy import deepcopy
import json
from pathlib import Path

from deezy.audio_encoders.dee.json.dd_base import dd_base
from deezy.enums.dd import DolbyDigitalChannels
from deezy.enums.ddp import DolbyDigitalPlusChannels
from deezy.enums.shared import DeeDRC, DeeDelay, DeeFPS
from deezy.payloads.dd import DDPayload
from deezy.payloads.ddp import DDPPayload


class DeeJSONGenerator:
    """Handles the creation of JSON files for DEE encoding"""

    __slots__ = (
        "input_file_path",
        "output_file_path",
        "output_dir",
    )

    def __init__(
        self,
        input_file_path: Path,
        output_file_path: Path,
        output_dir: Path,
    ) -> None:
        """
        Args:
            input_file_path (Path): Input file path.
            output_file_path (Path): Output file path.
            output_dir (Path | str): File path only.
        """
        self.input_file_path = input_file_path
        self.output_file_path = output_file_path
        self.output_dir = output_dir

    def dd_json(
        self,
        payload: DDPayload | DDPPayload,
        bitrate: int,
        fps: DeeFPS,
        delay: DeeDelay | None,
        temp_dir: Path,
        ddp_mode: bool = False,
        ddp71_mode: bool = False,
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
        if not ddp_mode and not ddp71_mode:
            filter_section["encoder_mode"] = "dd"
        elif ddp_mode:
            filter_section["encoder_mode"] = "ddp"
        else:
            filter_section["encoder_mode"] = "ddp71"
        filter_section["downmix_config"] = payload.channels.to_dee_cmd()
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
        downmix["preferred_downmix_mode"] = payload.preferred_downmix_mode.to_dee_cmd()
        filter_section["custom_dialnorm"] = payload.custom_dialnorm

        #### output section ####
        output_section = json_base["job_config"]["output"]
        if not ddp_mode and not ddp71_mode:
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
        # string bool lowered (true/false)
        misc_section["temp_dir"]["clean_temp"] = str(not payload.keep_temp).lower()
        misc_section["temp_dir"]["path"] = self._create_dee_file_path(temp_dir)

        return self._write_json(json_base)

    def _write_json(self, json_base: dict) -> Path:
        if not json_base:
            raise ValueError("Missing or invalid json base")
        file_out = Path(self.output_dir / self.output_file_path.name).with_suffix(
            ".json"
        )
        with open(file_out, "w") as json_file:
            json.dump(json_base, json_file, indent=2)
        return file_out

    @staticmethod
    def _create_dee_file_path(path: Path) -> str:
        """DEE expects file paths double quoted and with backslashes."""
        str_path = str(path)
        # convert to windows style backslashes
        str_path = str_path.replace("/", "\\")
        return f'"{str_path}"'
