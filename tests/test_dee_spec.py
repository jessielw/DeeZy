"""The format table in deezy.dee.spec, and the fixture it is built from."""

import pytest

from deezy.dee import spec
from deezy.pipeline.plan import secondary_bitrate

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
    ("ddp-atmos", "standard", "atmos"): 1152,
    ("ac4-ims", "ims", "2.0"): 256,
    # DeeZy's AC-4 defaults sit above Dolby's 64 and 128
    ("ac4", "ac4", "2.0"): 96,
    ("ac4", "ac4", "5.1"): 192,
    # a step above Dolby's 320 at level 3
    ("ac4-atmos", "level3", "atmos"): 448,
    # DeeZy raises only AAC-LC above Dolby's 64 kbps
    ("aac", "aaclc", "2.0"): 192,
    ("aac", "heaac", "2.0"): 64,
    ("aac", "heaacv2", "2.0"): 56,
}


def all_layouts():
    """Every layout with a data rate (a lossless format has none)."""
    for fmt in spec.formats().values():
        for mode_name, mode in fmt.modes.items():
            for layout_name, layout in mode.layouts.items():
                if layout.rates is not None:
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
    assert needs == {
        ("ddp", "ddp", "7.1"),
        ("ddp-atmos", "bluray", "atmos"),
        ("ddp-atmos", "standard", "atmos"),
    }


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
    assert spec.get_format("aac").extension == ".aac"
    assert spec.get_format("ac4").extension == ".ac4"
    assert spec.get_format("ac4-atmos").extensions == (".ac4",)


def test_truehd_is_lossless_and_starts_on_time():
    fmt = spec.get_format("thd")
    assert set(fmt.mode().layouts) == {"2.0", "5.1", "7.1"}
    with pytest.raises(ValueError, match="lossless"):
        fmt.rates("5.1")
    assert fmt.extensions == (".thd", ".mlp")
    assert (fmt.delay_samples, fmt.channel_change_samples) == (0, 0)
    assert fmt.tool.name == "dee_dthd_encoder"


@pytest.mark.parametrize("name", ["ac4", "ac4-atmos"])
def test_ac4_takes_the_manifest_offset_as_its_delay(name):
    fmt = spec.get_format(name)
    assert fmt.delay_samples == 2048
    assert fmt.channel_change_samples == 0


@pytest.mark.parametrize(
    ("mode", "low", "high", "auto"),
    [("aaclc", 56, 576, 64), ("heaac", 16, 143, 64), ("heaacv2", 14, 63, 56)],
)
def test_aac_takes_every_whole_rate_in_its_range(mode, low, high, auto):
    rates = spec.get_format("aac").rates("2.0", mode=mode)
    assert rates.choices == tuple(range(low, high + 1))
    assert rates.dee_auto == auto


@pytest.mark.parametrize(
    ("mode", "rate", "samples"),
    [
        ("aaclc", 56, 1710),
        ("aaclc", 71, 1710),
        ("aaclc", 72, 1702),
        ("aaclc", 87, 1702),
        ("aaclc", 88, 1600),
        ("aaclc", 576, 1600),
        ("heaac", 16, 4480),
        ("heaac", 64, 4280),
        ("heaac", 76, 4347),
        ("heaacv2", 14, 7172),
        ("heaacv2", 63, 7172),
    ],
)
def test_aac_delay_follows_the_rate(mode, rate, samples):
    assert spec.get_format("aac").mode(mode).delay_at(rate) == samples


def test_aac_delay_bands_cover_every_rate():
    fmt = spec.get_format("aac")
    for name, mode in fmt.modes.items():
        for rate in mode.layouts["2.0"].rates.choices:
            assert mode.delay_at(rate) is not None, (name, rate)
    with pytest.raises(ValueError, match="no aaclc delay"):
        fmt.mode("aaclc").delay_at(600)


def test_fixed_delay_formats_have_no_bands():
    assert spec.get_format("ddp").mode().delay_at(448) is None


@pytest.mark.parametrize(
    ("layout", "requested", "rate"),
    [
        ("2.0", None, 192),
        ("5.1", None, 192),
        ("2.0", 96, 96),
        ("2.0", 128, 128),
        ("2.0", 100, 128),
        ("5.1", 128, 160),
        ("5.1", 200, 224),
        ("5.1", 320, 256),
    ],
)
def test_bluray_secondary_takes_dee_rates(layout, requested, rate):
    assert secondary_bitrate(requested, layout) == rate
