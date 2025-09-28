import json
from pathlib import Path

from deezy.audio_encoders.dee.json.dee_json_generator import DeeJSONGenerator
from deezy.enums.ac4 import Ac4EncodingProfile
from deezy.enums.atmos import AtmosMode, WarpMode
from deezy.enums.codec_format import CodecFormat
from deezy.enums.dd import DolbyDigitalChannels
from deezy.enums.shared import (
    DDEncodingMode,
    DeeDRC,
    DeeFPS,
    MeteringMode,
    StereoDownmix,
)
from deezy.payloads.ac4 import Ac4Payload
from deezy.payloads.atmos import AtmosPayload
from deezy.payloads.dd import DDPayload
from deezy.track_info.track_index import TrackIndex


def make_core_fields(tmp_path: Path, keep_temp: bool) -> dict:
    # fields common to all Core/Loudness payloads
    return {
        "no_progress_bars": True,
        "ffmpeg_path": Path("/usr/bin/ffmpeg"),
        "truehdd_path": None,
        "dee_path": Path("/usr/bin/dee"),
        "file_input": tmp_path / "in.wav",
        "track_index": TrackIndex.audio(0),
        "bitrate": 640,
        "temp_dir": None,
        "delay": None,
        "keep_temp": keep_temp,
        "reuse_temp_files": False,
        "file_output": None,
        "batch_output_dir": None,
        "worker_id": None,
        "overwrite": True,
        # template fields
        "output_template": "",
        "output_preview": False,
        # Loudness fields
        "metering_mode": MeteringMode.MODE_1770_3,
        "dialogue_intelligence": True,
        "speech_threshold": 15,
    }


def make_dolby_fields() -> dict:
    # additional fields required by Dolby-based payloads (DD/DDP)
    return {
        "drc_line_mode": DeeDRC.FILM_LIGHT,
        "drc_rf_mode": DeeDRC.FILM_LIGHT,
        "custom_dialnorm": "0",
        # StereoMix fields
        "stereo_mix": StereoDownmix.NOT_INDICATED,
        "lfe_lowpass_filter": True,
        "surround_90_degree_phase_shift": True,
        "surround_3db_attenuation": True,
        "loro_center_mix_level": "-3",
        "loro_surround_mix_level": "-3",
        "ltrt_center_mix_level": "-3",
        "ltrt_surround_mix_level": "-3",
        "preferred_downmix_mode": StereoDownmix.NOT_INDICATED,
        "upmix_50_to_51": False,
    }


def test_dd_json_creates_file_and_clean_temp_reflects_payload(tmp_path: Path):
    core = make_core_fields(tmp_path, keep_temp=False)
    # ensure input exists
    (tmp_path / "in.wav").write_text("x")

    dolby = make_dolby_fields()
    payload = DDPayload(channels=DolbyDigitalChannels.SURROUND, **core, **dolby)

    output = Path("out.ec3")
    generator = DeeJSONGenerator(
        input_file_path=payload.file_input,
        output_file_path=output,
        output_dir=tmp_path,
        codec_format=CodecFormat.DDP,
    )

    json_path = generator.dd_json(
        payload,
        downmix_mode_off=False,
        bitrate=640,
        fps=DeeFPS.FPS_24,
        delay=None,
        temp_dir=tmp_path,
        dd_mode=DDEncodingMode.DDP,
    )

    assert json_path.exists()
    data = json.loads(json_path.read_text())
    assert data["job_config"]["misc"]["temp_dir"]["clean_temp"] == "true"
    # filename should include codec format
    assert json_path.name.endswith(f".{CodecFormat.DDP}.json")


def test_ac4_and_atmos_clean_temp_and_filename(tmp_path: Path):
    core = make_core_fields(tmp_path, keep_temp=True)
    (tmp_path / "in.wav").write_text("x")

    # AC4 payload doesn't accept the Dolby-only fields returned by make_dolby_fields()
    ac4_payload = Ac4Payload(
        thd_warp_mode=WarpMode.NORMAL,
        bed_conform=False,
        ims_legacy_presentation=False,
        encoding_profile=Ac4EncodingProfile.IMS,
        ddp_drc=DeeDRC.FILM_LIGHT,
        flat_panel_drc=DeeDRC.FILM_LIGHT,
        home_theatre_drc=DeeDRC.FILM_LIGHT,
        portable_headphones_drc=DeeDRC.FILM_LIGHT,
        portable_speakers_drc=DeeDRC.FILM_LIGHT,
        **core,
    )

    output_ac4 = Path("out.ac4")
    generator_ac4 = DeeJSONGenerator(
        input_file_path=ac4_payload.file_input,
        output_file_path=output_ac4,
        output_dir=tmp_path,
        codec_format=CodecFormat.AC4,
    )

    json_path_ac4 = generator_ac4.ac4_json(
        ac4_payload,
        bitrate=320,
        fps=DeeFPS.FPS_24,
        delay=None,
        temp_dir=tmp_path,
        atmos_enabled=True,
    )
    assert json_path_ac4.exists()
    data_ac4 = json.loads(json_path_ac4.read_text())
    # DEE job JSON now instructs DEE to clean temp files by default
    assert data_ac4["job_config"]["misc"]["temp_dir"]["clean_temp"] == "true"
    assert json_path_ac4.name.endswith(f".{CodecFormat.AC4}.json")

    # atmos
    dolby = make_dolby_fields()
    # AtmosPayload doesn't accept stereo_mix/lfe/etc. Filter to downmix/drc fields only
    allowed_atmos_keys = {
        "drc_line_mode",
        "drc_rf_mode",
        "custom_dialnorm",
        "loro_center_mix_level",
        "loro_surround_mix_level",
        "ltrt_center_mix_level",
        "ltrt_surround_mix_level",
        "preferred_downmix_mode",
    }
    atmos_fields = {k: v for k, v in dolby.items() if k in allowed_atmos_keys}

    atmos_payload = AtmosPayload(
        atmos_mode=AtmosMode.STREAMING,
        thd_warp_mode=WarpMode.NORMAL,
        bed_conform=False,
        **core,
        **atmos_fields,
    )
    generator_atm = DeeJSONGenerator(
        input_file_path=atmos_payload.file_input,
        output_file_path=Path("out.ec3"),
        output_dir=tmp_path,
        codec_format=CodecFormat.ATMOS,
    )
    json_path_atm = generator_atm.atmos_json(
        atmos_payload,
        bitrate=320,
        fps=DeeFPS.FPS_24,
        delay=None,
        temp_dir=tmp_path,
        atmos_mode=AtmosMode.STREAMING,
    )
    assert json_path_atm.exists()
    data_atm = json.loads(json_path_atm.read_text())
    # DEE job JSON now instructs DEE to clean temp files by default
    assert data_atm["job_config"]["misc"]["temp_dir"]["clean_temp"] == "true"
    assert json_path_atm.name.endswith(f".{CodecFormat.ATMOS}.json")
