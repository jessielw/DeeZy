"""The format table in deezy.dee.spec, and the fixture it is built from."""

import pytest

from deezy.dee import spec

# DeeZy's default rates, which 2.0 keeps instead of Dolby's lower automatic ones
DEFAULTS = {
    ("dd", "dd", "1.0"): 192,
    ("dd", "dd", "2.0"): 224,
    ("dd", "dd", "5.1"): 448,
    ("ddp", "ddp", "1.0"): 64,
    ("ddp", "ddp", "2.0"): 128,
    ("ddp", "ddp", "5.1"): 192,
    ("ddp", "ddp", "7.1"): 384,
    ("ddp-bluray", "bluray", "7.1"): 1280,
    ("ddp-bluray", "bluray_secondary", "2.0"): 192,
    ("ddp-bluray", "bluray_secondary", "5.1"): 192,
    ("ddp-atmos", "streaming", "atmos"): 448,
    ("ddp-atmos", "bluray", "atmos"): 1280,
    ("ac4-ims", "ims", "2.0"): 256,
}


def all_layouts():
    for fmt in spec.formats().values():
        for mode_name, mode in fmt.modes.items():
            for layout_name, layout in mode.layouts.items():
                yield (fmt.name, mode_name, layout_name), layout


def test_fixture_is_packaged():
    assert spec.fixture()["dee_version"].startswith("6.7.")


def test_every_layout_has_a_default():
    assert {key for key, _ in all_layouts()} == set(DEFAULTS)


@pytest.mark.parametrize(("key", "default"), DEFAULTS.items(), ids=str)
def test_default_rates_are_deezys(key, default):
    name, mode, layout = key
    rates = spec.get_format(name).rates(layout, mode=mode)
    assert rates.default == default
    assert default in rates.choices


def test_probed_rates_come_from_the_fixture():
    probed = spec.fixture()["rates"]["dee_ddp_encoder"]["dd"]["5.1"]
    rates = spec.get_format("dd").rates("5.1")
    assert rates.choices == tuple(probed["rates"])
    assert rates.dee_auto == probed["auto"]


def test_only_shim_layouts_need_the_shim():
    needs = {key for key, layout in all_layouts() if layout.needs_shim}
    assert needs == {("ddp", "ddp", "7.1"), ("ddp-atmos", "bluray", "atmos")}


def test_mode_defaults_to_the_first():
    fmt = spec.get_format("ddp-atmos")
    assert fmt.mode() is fmt.mode("streaming")
    assert fmt.mode("streaming").dee_mode == "ddpjoc"


def test_unknown_names_say_what_is_missing():
    with pytest.raises(KeyError, match="no DEE format"):
        spec.get_format("mp3")
    with pytest.raises(KeyError, match="no 7.1 layout"):
        spec.get_format("dd").rates("7.1")
    with pytest.raises(KeyError, match="no mode"):
        spec.get_format("dd").rates("5.1", mode="bluray")


@pytest.mark.parametrize(
    ("tool", "temp_dir", "single_pass"),
    [
        ("dee_ddp_encoder", True, True),
        ("dee_ddpjoc_encoder", False, True),
        ("dee_dthd_encoder", True, True),
        ("dee_ac4_encoder", True, False),
        ("dee_ac4ims_encoder", False, False),
        ("dee_ac4ajoc_encoder", False, False),
        ("dee_aac_encoder", True, True),
    ],
)
def test_tool_flags(tool, temp_dir, single_pass):
    found = spec.tool(tool)
    assert found.has_temp_dir is temp_dir
    assert found.single_pass is single_pass


def test_loudness_modes_drop_the_probe_value():
    assert spec.tool("dee_ddp_encoder").loudness_modes == {
        "skip:dialnorm",
        "measure_only",
        "measure_and_correct",
    }
    assert spec.tool("dee_aac_encoder").loudness_modes == {
        "skip",
        "measure_and_correct",
    }


def test_extensions():
    assert spec.get_format("dd").extension == ".ac3"
    assert spec.get_format("ddp").extensions == (".ec3", ".eac3")
    assert spec.get_format("ac4-ims").extension == ".ac4"
