from dataclasses import replace
from pathlib import Path

import pytest

from deezy.dee.commands import (
    DeeFiles,
    DeeTools,
    ac4ims_command,
    check_atmos_options,
    ddp_command,
    ddpjoc_command,
)
from deezy.dee.shim import DeeShim
from deezy.dee.spec import get_format
from deezy.dee.tools import get_executable_extension
from deezy.delay import Delay, compensation
from deezy.enums.ac4 import Ac4EncodingProfile
from deezy.enums.atmos import AtmosMode, WarpMode
from deezy.enums.dd import DolbyDigitalChannels
from deezy.enums.ddp import DolbyDigitalPlusChannels
from deezy.enums.shared import (
    DDEncodingMode,
    DeeDRC,
    DeeFPS,
    LoudnessPreset,
    MeteringMode,
    StereoDownmix,
)
from deezy.exceptions import UnsupportedDeeFeatureError
from deezy.payloads.ac4 import Ac4Payload
from deezy.payloads.atmos import AtmosPayload
from deezy.payloads.dd import DDPayload
from deezy.payloads.ddp import DDPPayload
from deezy.pipeline.plan import ddp_auto_layouts, ddp_channel_resolver
from tests.utils.payload_helpers import make_core_fields, make_dolby_fields

EXE = get_executable_extension()


@pytest.fixture
def split_dir(tmp_path: Path) -> Path:
    folder = tmp_path / "dee"
    folder.mkdir()
    (folder / f"dee_ddp_encoder{EXE}").touch()
    return folder


@pytest.fixture
def files(tmp_path: Path) -> DeeFiles:
    return DeeFiles(
        input=tmp_path / "in.wav", output=tmp_path / "out.ec3", temp_dir=tmp_path
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
    fields = {
        "atmos_mode": AtmosMode.STREAMING,
        "thd_warp_mode": WarpMode.NORMAL,
        **make_core_fields(tmp_path, keep_temp=False),
        **{k: v for k, v in dolby.items() if k in keys},
    }
    return AtmosPayload(**{**fields, **overrides})


def make_ac4_payload(tmp_path: Path, **overrides) -> Ac4Payload:
    fields = {
        "thd_warp_mode": WarpMode.NORMAL,
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
    value = (
        value.split(":", 1)[1]
        if value.split(":")[0] in ("dd", "ddp", "bluray", "bluray_secondary")
        else value
    )
    return dict(pair.split("=", 1) for pair in value.split(":"))


class TestSplitDD:
    def build(self, tmp_path, split_dir, files, payload=None, shim=None, **kwargs):
        options = {
            "downmix_mode_off": False,
            "bitrate": 640,
            "fps": DeeFPS.FPS_24,
            "delay": Delay(),
            "dd_mode": DDEncodingMode.DDP,
            **kwargs,
        }
        return ddp_command(
            DeeTools(split_dir, shim=shim),
            payload or make_dd_payload(tmp_path),
            files,
            **options,
        )

    def test_ddp_command(self, tmp_path, split_dir, files):
        cmd = self.build(tmp_path, split_dir, files)

        assert cmd[0] == str(split_dir / f"dee_ddp_encoder{EXE}")
        assert option(cmd, "--input-format") == "wav"
        assert option(cmd, "-i") == str(files.input)
        assert option(cmd, "-o") == str(files.output)
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

    def test_online_7_1_is_refused_without_the_shim(self, tmp_path, split_dir, files):
        """The plain DD+ mode has no 7.1 layout and would silently return 5.1."""
        with pytest.raises(UnsupportedDeeFeatureError, match="7.1 .*needs dee_shim"):
            self.build(tmp_path, split_dir, files, dd_mode=DDEncodingMode.DDP71)

    def test_online_7_1_runs_through_the_shim(self, tmp_path, split_dir, files):
        shim = DeeShim(Path("dee_shim"), "0.2.1")
        cmd = self.build(
            tmp_path, split_dir, files, shim=shim, dd_mode=DDEncodingMode.DDP71
        )
        tool = str(split_dir / f"dee_ddp_encoder{EXE}")
        assert cmd[:6] == [
            "dee_shim", "ddp_encoder", "--layout", "7.1/eac3", "--binary", tool,
        ]  # fmt: skip
        native = cmd[cmd.index("--") + 1 :]
        # the layout keeps DEE's own -e ddp options and --data-rate
        assert option(native, "-e").startswith("ddp:drc_profile_line=")
        assert option(native, "--data-rate") == "640"

    @pytest.mark.parametrize(
        "dd_mode",
        [
            DDEncodingMode.DD,
            DDEncodingMode.DDP,
            DDEncodingMode.BLURAY,
            DDEncodingMode.BLURAY_SECONDARY,
        ],
    )
    def test_other_modes_run_dee_alone_with_the_shim(
        self, tmp_path, split_dir, files, dd_mode
    ):
        shim = DeeShim(Path("dee_shim"), "0.2.1")
        cmd = self.build(tmp_path, split_dir, files, shim=shim, dd_mode=dd_mode)
        assert cmd[0] == str(split_dir / f"dee_ddp_encoder{EXE}")
        assert "--" not in cmd

    def test_bluray_uses_bluray_mode_without_output_layout(
        self, tmp_path, split_dir, files
    ):
        cmd = self.build(tmp_path, split_dir, files, dd_mode=DDEncodingMode.BLURAY)
        assert "-c" not in cmd
        assert option(cmd, "-e").startswith("bluray:")

    def test_custom_dialnorm_skips_measurement(self, tmp_path, split_dir, files):
        payload = make_dd_payload(tmp_path, custom_dialnorm=-27)
        cmd = self.build(tmp_path, split_dir, files, payload=payload)
        assert cmd[cmd.index("--loudness-management") + 1] == "skip:dialnorm=-27"

    def test_zero_custom_dialnorm_is_off(self, tmp_path, split_dir, files):
        payload = make_dd_payload(tmp_path, custom_dialnorm="0")
        self.build(tmp_path, split_dir, files, payload=payload)


class TestSplitDDExtras:
    """Options that only the split encoders offer."""

    def build(self, tmp_path, split_dir, files, dd_mode=DDEncodingMode.DDP, **fields):
        payload = replace(make_dd_payload(tmp_path), **fields)
        return ddp_command(
            DeeTools(split_dir),
            payload,
            files,
            downmix_mode_off=False,
            bitrate=192,
            fps=DeeFPS.FPS_24,
            delay=Delay(),
            dd_mode=dd_mode,
        )

    def test_loudness_target_measures_and_corrects(self, tmp_path, split_dir, files):
        cmd = self.build(tmp_path, split_dir, files, loudness_target=-24)
        assert option(cmd, "--loudness-management") == (
            "measure_and_correct:preset=manual:dialogue_intelligence=1:"
            "speech_threshold=15:loudness_target=-24"
        )

    def test_peak_limit(self, tmp_path, split_dir, files):
        cmd = self.build(
            tmp_path, split_dir, files, loudness_target=-27, peak_limit=-3.5
        )
        assert option(cmd, "--loudness-management").endswith(
            "loudness_target=-27:peak_limit_db=-3.5"
        )

    def test_peak_limit_needs_a_target(self, tmp_path, split_dir, files):
        with pytest.raises(UnsupportedDeeFeatureError, match="--loudness-target"):
            self.build(tmp_path, split_dir, files, peak_limit=-3)

    def test_target_and_custom_dialnorm_conflict(self, tmp_path, split_dir, files):
        with pytest.raises(UnsupportedDeeFeatureError, match="custom-dialnorm"):
            self.build(
                tmp_path, split_dir, files, loudness_target=-24, custom_dialnorm=-27
            )

    def test_loudness_target_is_refused_for_bluray(self, tmp_path, split_dir, files):
        with pytest.raises(UnsupportedDeeFeatureError, match="Blu-ray"):
            self.build(
                tmp_path,
                split_dir,
                files,
                dd_mode=DDEncodingMode.BLURAY,
                loudness_target=-24,
            )

    def test_user_data(self, tmp_path, split_dir, files):
        cmd = self.build(tmp_path, split_dir, files, user_data=100)
        assert encoder_options(cmd)["user_data"] == "100"

    def test_no_user_data_by_default(self, tmp_path, split_dir, files):
        assert "user_data" not in encoder_options(
            self.build(tmp_path, split_dir, files)
        )

    def test_user_data_is_refused_outside_plain_ddp(self, tmp_path, split_dir, files):
        with pytest.raises(UnsupportedDeeFeatureError, match="user-data"):
            self.build(
                tmp_path,
                split_dir,
                files,
                dd_mode=DDEncodingMode.BLURAY_SECONDARY,
                user_data=5,
            )

    def test_bluray_secondary_mode(self, tmp_path, split_dir, files):
        cmd = self.build(
            tmp_path, split_dir, files, dd_mode=DDEncodingMode.BLURAY_SECONDARY
        )
        assert option(cmd, "-e").startswith("bluray_secondary:")
        assert option(cmd, "-c") == "5.1"


class TestLoudnessPreset:
    def dd(self, tmp_path, split_dir, files, dd_mode=DDEncodingMode.DDP, **fields):
        return ddp_command(
            DeeTools(split_dir),
            replace(make_dd_payload(tmp_path), **fields),
            files,
            downmix_mode_off=False,
            bitrate=640,
            fps=DeeFPS.FPS_24,
            delay=Delay(),
            dd_mode=dd_mode,
        )

    @pytest.mark.parametrize(
        "preset", [p for p in LoudnessPreset if p.value != "manual"]
    )
    def test_preset_replaces_manual_options(self, tmp_path, split_dir, files, preset):
        cmd = self.dd(tmp_path, split_dir, files, loudness_preset=preset)
        assert option(cmd, "--loudness-management") == (
            f"measure_only:preset={preset.value}"
        )

    def test_preset_with_correction(self, tmp_path, split_dir, files):
        cmd = self.dd(
            tmp_path, split_dir, files, loudness_preset=LoudnessPreset.EBU_R128
        )
        assert "dialogue_intelligence" not in option(cmd, "--loudness-management")

    def test_preset_cannot_use_a_target(self, tmp_path, split_dir, files):
        with pytest.raises(UnsupportedDeeFeatureError, match="loudness-preset"):
            self.dd(
                tmp_path,
                split_dir,
                files,
                loudness_preset=LoudnessPreset.EBU_R128,
                loudness_target=-24,
            )

    def test_custom_dialnorm_wins_over_a_preset(self, tmp_path, split_dir, files):
        cmd = self.dd(
            tmp_path,
            split_dir,
            files,
            loudness_preset=LoudnessPreset.EBU_R128,
            custom_dialnorm=-27,
        )
        assert option(cmd, "--loudness-management") == "skip:dialnorm=-27"

    def test_atmos_and_ac4(self, tmp_path, split_dir, files):
        atmos = ddpjoc_command(
            DeeTools(split_dir),
            replace(
                make_atmos_payload(tmp_path), loudness_preset=LoudnessPreset.ATSC_A85
            ),
            files,
            bitrate=448,
            fps=DeeFPS.FPS_24,
            delay=Delay(),
        )
        ac4 = ac4ims_command(
            DeeTools(split_dir),
            make_ac4_payload(tmp_path, loudness_preset=LoudnessPreset.ATSC_A85),
            files,
            bitrate=256,
            fps=DeeFPS.FPS_24,
            delay=Delay(),
            atmos_input=True,
        )
        for cmd in (atmos, ac4):
            assert (
                option(cmd, "--loudness-management") == "measure_only:preset=atsc_a85"
            )


class TestSplitDelay:
    def build(self, tmp_path, split_dir, files, delay):
        return ddp_command(
            DeeTools(split_dir),
            make_dd_payload(tmp_path),
            files,
            downmix_mode_off=False,
            bitrate=640,
            fps=DeeFPS.FPS_24,
            delay=delay,
            dd_mode=DDEncodingMode.DDP,
        )

    def test_default_compensation_trims_the_start(self, tmp_path, split_dir, files):
        cmd = self.build(
            tmp_path, split_dir, files, Delay.parse("0ms").compensated(256)
        )
        assert option(cmd, "--start") == "0.005333"
        assert "--add-silence" not in cmd

    def test_positive_delay_prepends_silence(self, tmp_path, split_dir, files):
        cmd = self.build(
            tmp_path, split_dir, files, Delay.parse("100ms").compensated(256)
        )
        assert option(cmd, "--add-silence") == "0.094667:0"
        # left out, DEE would start at the first frame of action
        assert option(cmd, "--start") == "0"

    def test_negative_delay_trims_the_start(self, tmp_path, split_dir, files):
        cmd = self.build(
            tmp_path, split_dir, files, Delay.parse("-100ms").compensated(256)
        )
        assert option(cmd, "--start") == "0.105333"
        assert "--add-silence" not in cmd

    def test_a_delay_equal_to_the_compensation_is_no_shift(
        self, tmp_path, split_dir, files
    ):
        cmd = self.build(
            tmp_path, split_dir, files, Delay.parse("6ms").compensated(288)
        )
        assert option(cmd, "--start") == "0"
        assert "--add-silence" not in cmd

    def test_no_delay_starts_at_the_first_sample(self, tmp_path, split_dir, files):
        cmd = self.build(tmp_path, split_dir, files, Delay())
        assert option(cmd, "--start") == "0"
        assert "--add-silence" not in cmd

    def test_a_channel_change_adds_32_samples(self, tmp_path, split_dir, files):
        delay = Delay().compensated(
            compensation(get_format("ddp"), channel_change=True)
        )
        assert delay.compensation == 288
        cmd = self.build(tmp_path, split_dir, files, delay)
        assert option(cmd, "--start") == "0.006000"

    @pytest.mark.parametrize(
        ("delay", "offset"),
        [("-2s", -96256), ("-10ms", -736), ("0ms", -256), ("250ms", 11744)],
    )
    def test_offsets_are_whole_samples(self, delay, offset):
        assert Delay.parse(delay).compensated(256).offset == offset


class TestSplitAtmos:
    def test_command(self, tmp_path, split_dir, files):
        cmd = ddpjoc_command(
            DeeTools(split_dir),
            make_atmos_payload(tmp_path),
            files,
            bitrate=448,
            fps=DeeFPS.FPS_24,
            delay=Delay(),
        )

        assert cmd[0] == str(split_dir / f"dee_ddpjoc_encoder{EXE}")
        assert option(cmd, "--input-format") == "atmos_mezz"
        assert option(cmd, "--data-rate") == "448"
        # this encoder has no --temp-dir option and refuses to start with one
        assert "--temp-dir" not in cmd
        assert encoder_options(cmd)["drc_profile_line"] == "film_light"
        assert encoder_options(cmd)["preferred_downmix_mode"] == "not_indicated"

    def build(self, tmp_path, split_dir, files, shim=None, bitrate=448, **payload):
        return ddpjoc_command(
            DeeTools(split_dir, shim=shim),
            make_atmos_payload(tmp_path, **payload),
            files,
            bitrate=bitrate,
            fps=DeeFPS.FPS_24,
            delay=Delay(),
        )

    @pytest.mark.parametrize("mode", [AtmosMode.BLURAY, AtmosMode.STANDARD])
    def test_7_1_backbones_need_dee_shim(self, tmp_path, split_dir, files, mode):
        # DEE's own Blu-ray mode gives a 5.1.2 backbone, not 7.1
        with pytest.raises(UnsupportedDeeFeatureError, match="7.1 backbone.*dee_shim"):
            self.build(tmp_path, split_dir, files, atmos_mode=mode)

    def test_phase_shift_off_needs_dee_shim(self, tmp_path, split_dir, files):
        with pytest.raises(UnsupportedDeeFeatureError, match="phase-shift.*dee_shim"):
            self.build(tmp_path, split_dir, files, surround_90_degree_phase_shift=False)

    def test_oamd_as_is_off_is_fine_without_the_shim(self, tmp_path, split_dir, files):
        # DEE alone always smooths, so there is nothing to turn off
        cmd = self.build(tmp_path, split_dir, files, oamd_as_is=False)
        assert cmd[0] == str(split_dir / f"dee_ddpjoc_encoder{EXE}")
        assert "--" not in cmd

    def test_refusals_pass_with_the_shim(self, tmp_path):
        payload = make_atmos_payload(
            tmp_path,
            atmos_mode=AtmosMode.STANDARD,
            surround_90_degree_phase_shift=False,
        )
        check_atmos_options(payload, shim=True)

    @pytest.mark.parametrize(
        ("mode", "layout"),
        [
            (AtmosMode.STREAMING, []),
            (AtmosMode.BLURAY, ["--layout", "7.1"]),
            (AtmosMode.STANDARD, ["--layout", "7.1/eac3"]),
        ],
    )
    def test_shim_options_by_mode(self, tmp_path, split_dir, files, mode, layout):
        shim = DeeShim(Path("dee_shim"), "0.2.1")
        cmd = self.build(tmp_path, split_dir, files, shim=shim, atmos_mode=mode)
        tool = str(split_dir / f"dee_ddpjoc_encoder{EXE}")
        # the object metadata is coded as the master has it by default
        assert cmd[: cmd.index("--")] == [
            "dee_shim", "ddpjoc_encoder", *layout, "--oamd-as-is", "on",
            "--binary", tool,
        ]  # fmt: skip
        native = cmd[cmd.index("--") + 1 :]
        # DeeZy's -e names no mode; the shim adds the one its layout runs
        assert option(native, "-e").startswith("preferred_downmix_mode=")
        assert option(native, "--data-rate") == "448"

    def test_shim_phase_shift_off_and_oamd_smoothed(self, tmp_path, split_dir, files):
        shim = DeeShim(Path("dee_shim"), "0.2.1")
        cmd = self.build(
            tmp_path,
            split_dir,
            files,
            shim=shim,
            surround_90_degree_phase_shift=False,
            oamd_as_is=False,
        )
        assert cmd[: cmd.index("--binary")] == [
            "dee_shim", "ddpjoc_encoder", "--phase90", "off",
        ]  # fmt: skip

    def test_custom_dialnorm(self, tmp_path, split_dir, files):
        cmd = ddpjoc_command(
            DeeTools(split_dir),
            replace(make_atmos_payload(tmp_path), custom_dialnorm=-27),
            files,
            bitrate=448,
            fps=DeeFPS.FPS_24,
            delay=Delay(),
        )
        assert option(cmd, "--loudness-management") == "skip:dialnorm=-27"


class TestSplitAC4:
    def build(self, tmp_path, split_dir, files, atmos=True, **payload):
        return ac4ims_command(
            DeeTools(split_dir),
            make_ac4_payload(tmp_path, **payload),
            files,
            bitrate=256,
            fps=DeeFPS.FPS_24,
            delay=Delay(),
            atmos_input=atmos,
        )

    def test_atmos_input(self, tmp_path, split_dir, files):
        cmd = self.build(tmp_path, split_dir, files)

        assert cmd[0] == str(split_dir / f"dee_ac4ims_encoder{EXE}")
        assert option(cmd, "--input-format") == "atmos_mezz"
        assert option(cmd, "--data-rate") == "256"
        assert "--temp-dir" not in cmd
        assert set(encoder_options(cmd)) == {
            "mode",
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

    def test_general_mode_by_default(self, tmp_path, split_dir, files):
        options = encoder_options(self.build(tmp_path, split_dir, files))
        assert options["mode"] == "general"

    def test_music_mode_sets_what_dee_requires(self, tmp_path, split_dir, files):
        cmd = self.build(
            tmp_path,
            split_dir,
            files,
            encoding_profile=Ac4EncodingProfile.IMS_MUSIC,
            ddp_drc=DeeDRC.SPEECH,
            flat_panel_drc=DeeDRC.FILM_STANDARD,
        )
        options = encoder_options(cmd)
        assert options.pop("mode") == "music"
        # the DD+ transcode profile is not checked by DEE, so it is kept
        assert options.pop("drc_profile_ddp") == "speech"
        assert set(options.values()) == {"music_light"}
        assert "dialogue_intelligence=0" in option(cmd, "--loudness-management")


def test_non_1770_4_metering_is_measured_as_1770_4(tmp_path, split_dir, files):
    """The split encoders only measure 1770-4, so the request is overridden."""
    payload = make_dd_payload(tmp_path, metering_mode=MeteringMode.MODE_1770_1)
    cmd = ddp_command(
        DeeTools(split_dir),
        payload,
        files,
        downmix_mode_off=False,
        bitrate=640,
        fps=DeeFPS.FPS_24,
        delay=Delay(),
        dd_mode=DDEncodingMode.DDP,
    )
    assert option(cmd, "--loudness-management").startswith("measure_only:")


@pytest.mark.parametrize(("shim", "has_71"), [(False, False), (True, True)])
def test_ddp_auto_picks_7_1_only_with_the_shim(shim, has_71):
    assert ddp_auto_layouts(shim) == ([1, 2, 6, 8] if has_71 else [1, 2, 6])
    expected = (
        DolbyDigitalPlusChannels.SURROUNDEX
        if has_71
        else DolbyDigitalPlusChannels.SURROUND
    )
    assert ddp_channel_resolver(8, shim) is expected


@pytest.mark.parametrize("shim", [False, True])
def test_ddp_auto_keeps_a_6_1_source_at_5_1(shim):
    assert ddp_channel_resolver(7, shim) is DolbyDigitalPlusChannels.SURROUND
