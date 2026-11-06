from pathlib import Path

import pytest

from deezy.audio_encoders.dee.backends import (
    DeeJobFiles,
    LegacyDeeBackend,
    SplitDeeBackend,
    get_dee_backend,
)
from deezy.audio_encoders.delay import get_dee_delay
from deezy.enums.ac4 import Ac4EncodingProfile
from deezy.enums.atmos import AtmosMode, WarpMode
from deezy.enums.codec_format import CodecFormat
from deezy.enums.dd import DolbyDigitalChannels
from deezy.enums.ddp import DolbyDigitalPlusChannels
from deezy.enums.shared import (
    DDEncodingMode,
    DeeDRC,
    DeeFPS,
    MeteringMode,
    StereoDownmix,
)
from deezy.exceptions import UnsupportedDeeFeatureError
from deezy.payloads.ac4 import Ac4Payload
from deezy.payloads.atmos import AtmosPayload
from deezy.payloads.dd import DDPayload
from deezy.payloads.ddp import DDPPayload
from deezy.utils.dependencies import get_executable_extension
from tests.test_dee_json_generator import make_core_fields, make_dolby_fields

EXE = get_executable_extension()


@pytest.fixture
def split_dir(tmp_path: Path) -> Path:
    folder = tmp_path / "dee"
    folder.mkdir()
    (folder / f"dee_ddp_encoder{EXE}").touch()
    return folder


@pytest.fixture
def files(tmp_path: Path) -> DeeJobFiles:
    return DeeJobFiles(
        input_file=tmp_path / "in.wav",
        output_file=tmp_path / "out.ec3",
        temp_dir=tmp_path,
        job_name="job",
        codec_format=CodecFormat.DDP,
    )


def make_dd_payload(tmp_path: Path, cls=DDPPayload, channels=None, **overrides):
    core = make_core_fields(tmp_path, keep_temp=False)
    fields = {**core, **make_dolby_fields(), **overrides}
    return cls(
        channels=channels
        or (
            DolbyDigitalChannels.SURROUND
            if cls is DDPayload
            else DolbyDigitalPlusChannels.SURROUND
        ),
        **fields,
    )


def make_atmos_payload(tmp_path: Path, **overrides) -> AtmosPayload:
    dolby = make_dolby_fields()
    keys = {
        "drc_line_mode",
        "drc_rf_mode",
        "custom_dialnorm",
        "loro_center_mix_level",
        "loro_surround_mix_level",
        "ltrt_center_mix_level",
        "ltrt_surround_mix_level",
        "preferred_downmix_mode",
    }
    return AtmosPayload(
        atmos_mode=AtmosMode.STREAMING,
        thd_warp_mode=WarpMode.NORMAL,
        bed_conform=False,
        **make_core_fields(tmp_path, keep_temp=False),
        **{k: v for k, v in dolby.items() if k in keys},
        **overrides,
    )


def make_ac4_payload(tmp_path: Path, **overrides) -> Ac4Payload:
    fields = {
        "thd_warp_mode": WarpMode.NORMAL,
        "bed_conform": False,
        "ims_legacy_presentation": False,
        "encoding_profile": Ac4EncodingProfile.IMS,
        "ddp_drc": DeeDRC.FILM_LIGHT,
        "flat_panel_drc": DeeDRC.FILM_LIGHT,
        "home_theatre_drc": DeeDRC.FILM_LIGHT,
        "portable_headphones_drc": DeeDRC.FILM_LIGHT,
        "portable_speakers_drc": DeeDRC.FILM_LIGHT,
        **overrides,
    }
    return Ac4Payload(**fields, **make_core_fields(tmp_path, keep_temp=False))


def option(cmd: list[str], flag: str) -> str:
    return cmd[cmd.index(flag) + 1]


def encoder_options(cmd: list[str]) -> dict[str, str]:
    value = option(cmd, "-e")
    # DD/DDP lead with the mode ('ddp:...'), the others are bare lists
    value = value.split(":", 1)[1] if value.split(":")[0] in ("dd", "ddp") else value
    return dict(pair.split("=", 1) for pair in value.split(":"))


class TestBackendSelection:
    def test_folder_is_split(self, split_dir):
        assert isinstance(get_dee_backend(split_dir), SplitDeeBackend)

    def test_file_is_legacy(self, tmp_path):
        dee = tmp_path / f"dee{EXE}"
        dee.touch()
        assert isinstance(get_dee_backend(dee), LegacyDeeBackend)

    def test_unresolved_path_is_legacy(self):
        # keeps the single-dee behaviour for a path that is only a name
        assert isinstance(get_dee_backend(Path("dee")), LegacyDeeBackend)


class TestLegacyBackend:
    def test_runs_the_json_job_it_wrote(self, tmp_path, files):
        backend = LegacyDeeBackend(Path("dee"))
        cmd = backend.dd_command(
            make_dd_payload(tmp_path),
            files,
            downmix_mode_off=False,
            bitrate=640,
            fps=DeeFPS.FPS_24,
            delay=None,
            dd_mode=DDEncodingMode.DDP,
        )

        assert cmd[0] == "dee"
        assert "--verbose" in cmd
        json_path = Path(option(cmd, "-j"))
        assert json_path.is_file()
        assert json_path.name == f"job.{CodecFormat.DDP}.json"


class TestSplitDD:
    def build(self, tmp_path, split_dir, files, payload=None, **kwargs):
        options = {
            "downmix_mode_off": False,
            "bitrate": 640,
            "fps": DeeFPS.FPS_24,
            "delay": None,
            "dd_mode": DDEncodingMode.DDP,
            **kwargs,
        }
        return SplitDeeBackend(split_dir).dd_command(
            payload or make_dd_payload(tmp_path), files, **options
        )

    def test_ddp_command(self, tmp_path, split_dir, files):
        cmd = self.build(tmp_path, split_dir, files)

        assert cmd[0] == str(split_dir / f"dee_ddp_encoder{EXE}")
        assert option(cmd, "--input-format") == "wav"
        assert option(cmd, "-i") == str(files.input_file)
        assert option(cmd, "-o") == str(files.output_file)
        assert option(cmd, "--temp-dir") == str(files.temp_dir)
        assert option(cmd, "--data-rate") == "640"
        assert option(cmd, "--timecode-frame-rate") == "24"
        assert option(cmd, "-c") == "5.1"
        assert option(cmd, "--progress") == "1"
        assert option(cmd, "--overwrite") == "1"
        assert option(cmd, "-e").startswith("ddp:")
        assert encoder_options(cmd) == {
            "drc_profile_line": "film_light",
            "drc_profile_rf": "film_light",
            "lfe_filter": "1",
            "surround_90deg_phase_shift": "1",
            "surround_3dB_attenuation": "1",
            "preferred_downmix_mode": "not_indicated",
            "loro_cmix": "-3",
            "loro_smix": "-3",
            "ltrt_cmix": "-3",
            "ltrt_smix": "-3",
        }

    def test_dd_uses_dd_encoder_mode(self, tmp_path, split_dir, files):
        cmd = self.build(
            tmp_path,
            split_dir,
            files,
            payload=make_dd_payload(tmp_path, cls=DDPayload),
            dd_mode=DDEncodingMode.DD,
        )
        assert option(cmd, "-e").startswith("dd:")

    def test_downmix_off_means_auto_layout_and_no_indicated_mode(
        self, tmp_path, split_dir, files
    ):
        payload = make_dd_payload(tmp_path, preferred_downmix_mode=StereoDownmix.LTRT)
        cmd = self.build(
            tmp_path, split_dir, files, payload=payload, downmix_mode_off=True
        )
        assert option(cmd, "-c") == "auto"
        assert encoder_options(cmd)["preferred_downmix_mode"] == "not_indicated"

    def test_auto_channels_use_auto_layout(self, tmp_path, split_dir, files):
        payload = make_dd_payload(tmp_path, channels=DolbyDigitalPlusChannels.AUTO)
        cmd = self.build(tmp_path, split_dir, files, payload=payload)
        assert option(cmd, "-c") == "auto"

    def test_metering_defaults_to_measure_only(self, tmp_path, split_dir, files):
        cmd = self.build(tmp_path, split_dir, files)
        assert option(cmd, "--loudness-management") == (
            "measure_only:preset=manual:dialogue_intelligence=1:speech_threshold=15"
        )

    @pytest.mark.parametrize("mode", [DDEncodingMode.BLURAY, DDEncodingMode.DDP71])
    def test_7_1_is_refused(self, tmp_path, split_dir, files, mode):
        """The tool has no 7.1 layout and would silently return 5.1."""
        with pytest.raises(UnsupportedDeeFeatureError, match="7.1"):
            self.build(tmp_path, split_dir, files, dd_mode=mode)

    def test_custom_dialnorm_is_refused(self, tmp_path, split_dir, files):
        payload = make_dd_payload(tmp_path, custom_dialnorm=-27)
        with pytest.raises(UnsupportedDeeFeatureError, match="custom-dialnorm"):
            self.build(tmp_path, split_dir, files, payload=payload)

    def test_zero_custom_dialnorm_is_off(self, tmp_path, split_dir, files):
        payload = make_dd_payload(tmp_path, custom_dialnorm="0")
        self.build(tmp_path, split_dir, files, payload=payload)


class TestSplitDelay:
    def build(self, tmp_path, split_dir, files, delay):
        return SplitDeeBackend(split_dir).dd_command(
            make_dd_payload(tmp_path),
            files,
            downmix_mode_off=False,
            bitrate=640,
            fps=DeeFPS.FPS_24,
            delay=delay,
            dd_mode=DDEncodingMode.DDP,
        )

    def test_default_compensation_trims_the_start(self, tmp_path, split_dir, files):
        cmd = self.build(tmp_path, split_dir, files, get_dee_delay("0ms"))
        assert option(cmd, "--start") == "0.005333"
        assert "--add-silence" not in cmd

    def test_positive_delay_prepends_silence(self, tmp_path, split_dir, files):
        cmd = self.build(tmp_path, split_dir, files, get_dee_delay("100ms"))
        assert option(cmd, "--add-silence") == "0.094667:0"
        assert "--start" not in cmd

    def test_no_delay_adds_nothing(self, tmp_path, split_dir, files):
        cmd = self.build(tmp_path, split_dir, files, None)
        assert "--start" not in cmd
        assert "--add-silence" not in cmd

    @pytest.mark.parametrize("delay", ["-2s", "-10ms", "0ms", "250ms", "3s"])
    def test_seconds_match_the_millisecond_input(self, delay):
        dee_delay = get_dee_delay(delay)
        expected = abs(_ms(delay) - 16 / 3) / 1000
        assert dee_delay.to_seconds() == pytest.approx(expected, abs=1e-6)


def _ms(delay: str) -> float:
    value = float(delay.rstrip("ms"))
    return value if delay.endswith("ms") else value * 1000


class TestSplitAtmos:
    def test_command(self, tmp_path, split_dir, files):
        cmd = SplitDeeBackend(split_dir).atmos_command(
            make_atmos_payload(tmp_path),
            files,
            bitrate=448,
            fps=DeeFPS.FPS_24,
            delay=None,
            atmos_mode=AtmosMode.STREAMING,
        )

        assert cmd[0] == str(split_dir / f"dee_ddpjoc_encoder{EXE}")
        assert option(cmd, "--input-format") == "atmos_mezz"
        assert option(cmd, "--data-rate") == "448"
        # this encoder has no --temp-dir option and refuses to start with one
        assert "--temp-dir" not in cmd
        assert encoder_options(cmd)["drc_profile_line"] == "film_light"
        assert encoder_options(cmd)["preferred_downmix_mode"] == "not_indicated"

    def test_bluray_is_refused(self, tmp_path, split_dir, files):
        with pytest.raises(UnsupportedDeeFeatureError):
            SplitDeeBackend(split_dir).atmos_command(
                make_atmos_payload(tmp_path),
                files,
                bitrate=1280,
                fps=DeeFPS.FPS_24,
                delay=None,
                atmos_mode=AtmosMode.BLURAY,
            )


class TestSplitAC4:
    def build(self, tmp_path, split_dir, files, atmos=True, **payload):
        return SplitDeeBackend(split_dir).ac4_command(
            make_ac4_payload(tmp_path, **payload),
            files,
            bitrate=256,
            fps=DeeFPS.FPS_24,
            delay=None,
            atmos_enabled=atmos,
        )

    def test_atmos_input(self, tmp_path, split_dir, files):
        cmd = self.build(tmp_path, split_dir, files)

        assert cmd[0] == str(split_dir / f"dee_ac4ims_encoder{EXE}")
        assert option(cmd, "--input-format") == "atmos_mezz"
        assert option(cmd, "--data-rate") == "256"
        assert "--temp-dir" not in cmd
        assert set(encoder_options(cmd)) == {
            "drc_profile_ddp",
            "drc_profile_flat_panel",
            "drc_profile_home_theatre",
            "drc_profile_portable_hp",
            "drc_profile_portable_spkr",
        }

    def test_channel_based_input_is_wav(self, tmp_path, split_dir, files):
        cmd = self.build(tmp_path, split_dir, files, atmos=False)
        assert option(cmd, "--input-format") == "wav"

    def test_none_drc_is_passed_through(self, tmp_path, split_dir, files):
        cmd = self.build(tmp_path, split_dir, files, ddp_drc=DeeDRC.NONE)
        assert encoder_options(cmd)["drc_profile_ddp"] == "none"

    def test_legacy_presentation_is_ignored(self, tmp_path, split_dir, files):
        cmd = self.build(tmp_path, split_dir, files, ims_legacy_presentation=True)
        assert cmd == self.build(tmp_path, split_dir, files)

    def test_music_profile_is_refused(self, tmp_path, split_dir, files):
        with pytest.raises(UnsupportedDeeFeatureError):
            self.build(
                tmp_path,
                split_dir,
                files,
                encoding_profile=Ac4EncodingProfile.IMS_MUSIC,
            )


def test_non_1770_4_metering_is_measured_as_1770_4(tmp_path, split_dir, files):
    """The split encoders only measure 1770-4, so the request is overridden."""
    payload = make_dd_payload(tmp_path, metering_mode=MeteringMode.MODE_1770_1)
    cmd = SplitDeeBackend(split_dir).dd_command(
        payload,
        files,
        downmix_mode_off=False,
        bitrate=640,
        fps=DeeFPS.FPS_24,
        delay=None,
        dd_mode=DDEncodingMode.DDP,
    )
    assert option(cmd, "--loudness-management").startswith("measure_only:")
