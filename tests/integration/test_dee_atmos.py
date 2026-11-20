"""Atmos encodes from a DAMF master that truehdd decodes from a TrueHD Atmos sample."""

import pytest

from .harness import (
    damf_with_warp,
    decode,
    make_damf,
    md5,
    mediainfo,
    truehd_content,
    warp_mode,
    xcorr,
)

SHORT = ("--duration", "5")


def joc(tools, src, out, mode, *args):
    return tools.dee(
        "dee_ddpjoc_encoder", "--input-format", "atmos_mezz", "-i", src, "-o", out,
        "-e", mode, *args,
    )  # fmt: skip


def joc_shim(tools, src, out, layout, *args):
    return tools.run_shim(
        "ddpjoc_encoder",
        ["--layout", layout],
        ["--input-format", "atmos_mezz", "-i", src, "-o", out, *args],
    )


# --- Layout and rates --------------------------------------------------------------


def test_streaming_joc(tools, work, damf):
    out = work / "joc51.ec3"
    result = joc(tools, damf, out, "ddpjoc", *SHORT)
    assert result.ok, result.error()
    info = mediainfo(out)
    assert info["channel_layout"] == "L R C LFE Ls Rs"
    assert "JOC" in info["format_additionalfeatures"]
    assert int(info["bit_rate"]) == 448000


def test_native_bluray_backbone_is_5_1_2(tools, work, damf):
    """Bug 3: -e bluray codes front heights, not back surrounds."""
    out = work / "jocbr_native.eb3"
    result = joc(tools, damf, out, "bluray", *SHORT)
    assert result.ok, result.error()
    info = mediainfo(out)
    assert info["channel_layout"] == "L R C LFE Ls Rs Tfl Tfr"
    assert info["format"] == "AC-3"  # AC-3 core plus a JOC dependent substream
    assert "JOC" in info["format_additionalfeatures"]
    assert int(info["bit_rate"]) == 1152000


def test_shim_7_1_backbone(shim, work, damf):
    out = work / "jocbr_shim.eb3"
    result = joc_shim(shim, damf, out, "7.1", *SHORT)
    assert result.ok, result.error()
    info = mediainfo(out)
    assert info["channel_layout"] == "L R C LFE Ls Rs Lb Rb"
    assert info["format"] == "AC-3"
    assert "JOC" in info["format_additionalfeatures"]
    assert int(info["complexity_index"]) == 16


JOC_RATES = [
    *[("ddpjoc", r, True) for r in (384, 448, 576, 640, 768, 1024)],
    ("ddpjoc", 512, False),
    *[("bluray", r, True) for r in (1152, 1280, 1408, 1512, 1536, 1664)],
    ("bluray", 1024, False),
    ("bluray", 2048, False),
]


@pytest.mark.parametrize(("mode", "rate", "ok"), JOC_RATES)
def test_joc_rates(tools, work, damf, mode, rate, ok):
    out = work / f"jocrate_{mode}_{rate}.ec3"
    result = joc(tools, damf, out, mode, "--data-rate", str(rate), "--duration", "1")
    assert result.ok is ok, result.error()


AJOC_RATES = [
    *[(3, r, True) for r in (256, 320, 448, 768)],
    (3, 128, False),
    (3, 1500, False),
    *[(4, r, True) for r in (128, 256, 448, 768, 1500)],
    (4, 320, False),
]


@pytest.mark.parametrize(("level", "rate", "ok"), AJOC_RATES)
def test_ac4_atmos_rates(tools, work, damf, level, rate, ok):
    out = work / f"ajoc_{level}_{rate}.ac4"
    result = tools.dee(
        "dee_ac4ajoc_encoder", "-i", damf, "-o", out, "--level", str(level),
        "--output-manifest", out.with_suffix(".json"), "--data-rate", str(rate),
        "--duration", "1",
    )  # fmt: skip
    assert result.ok is ok, result.error()


def test_joc_drc_none(tools, work, damf):
    result = joc(
        tools, damf, work / "joc_drc.ec3", "ddpjoc:drc_profile=none", "--duration", "1"
    )
    assert result.ok, result.error()


def test_joc_from_a_master_cannot_correct_loudness(tools, work, damf):
    """The -31..-8 target range in --help applies only to 5.1.4 channel-based input."""
    result = joc(
        tools, damf, work / "joc_correct.ec3", "ddpjoc", "--duration", "1",
        "--loudness-management", "measure_and_correct:loudness_target=-24",
    )  # fmt: skip
    assert not result.ok
    assert "supported only for 5.1.4 channel-based immersive input" in result.out


def test_joc_is_deterministic(tools, work, damf):
    first, second = work / "jocdet1.ec3", work / "jocdet2.ec3"
    assert joc(tools, damf, first, "ddpjoc", *SHORT).ok
    assert joc(tools, damf, second, "ddpjoc", *SHORT).ok
    assert md5(first) == md5(second)


# --- Delay -----------------------------------------------------------------------

DELAY_SECONDS = ("--duration", "12")


@pytest.fixture(scope="module")
def truehd_ref(tools, work, thd):
    return decode(tools, thd, work / "ref_truehd.wav")


def assert_lag(tools, ref, out, expected):
    lag, corr = xcorr(ref, 0, decode(tools, out), 0)
    assert corr > 0.9, f"weak correlation {corr:.3f}"
    assert lag == expected


@pytest.mark.parametrize(("mode", "suffix"), [("ddpjoc", ".ec3"), ("bluray", ".eb3")])
def test_joc_delay_is_256(tools, work, damf, truehd_ref, mode, suffix):
    out = work / f"jocdelay_{mode}{suffix}"
    result = joc(tools, damf, out, mode, *DELAY_SECONDS)
    assert result.ok, result.error()
    assert_lag(tools, truehd_ref, out, 256)


def test_shim_joc_delay_is_256(shim, work, damf, truehd_ref):
    out = work / "jocdelay_shim71.eb3"
    result = joc_shim(shim, damf, out, "7.1", *DELAY_SECONDS)
    assert result.ok, result.error()
    assert_lag(shim, truehd_ref, out, 256)


@pytest.mark.parametrize(("mode", "suffix"), [("ddp", ".ec3"), ("dd", ".ac3")])
def test_render_of_master_delay_is_256(tools, work, damf, truehd_ref, mode, suffix):
    out = work / f"renderdelay_{mode}{suffix}"
    result = tools.dee(
        "dee_ddp_encoder", "--input-format", "atmos_mezz", "-i", damf, "-o", out,
        "-e", mode, "--loudness-management", "measure_only", *DELAY_SECONDS,
    )  # fmt: skip
    assert result.ok, result.error()
    assert_lag(tools, truehd_ref, out, 256)


def test_truehd_atmos_delay_is_0(tools, work, damf, truehd_ref):
    out = work / "thdatmos_delay.thd"
    result = tools.dee(
        "dee_dthd_encoder", "--presentation", "atmos:number_of_elements=16:legacy_authoring=0",
        "--input-format", "atmos_mezz", "-i", damf, "-o", out, "--temp-dir", work,
        *DELAY_SECONDS,
    )  # fmt: skip
    assert result.ok, result.error()
    assert_lag(tools, truehd_ref, out, 0)


# --- truehdd -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("flag", "written"),
    [
        ("normal", "normal"),
        ("warping", "warping"),
        ("prologiciix", "ProLogicIIx"),
        ("loro", "LoRo"),
    ],
)
def test_truehdd_writes_dee_warp_names(tools, work, thd, damf, flag, written):
    if warp_mode(damf) is not None:
        pytest.skip("the sample carries a warp mode, so truehdd ignores --warp-mode")
    out = make_damf(tools, thd, work / f"damf_warp_{flag}", "--warp-mode", flag)
    assert warp_mode(out) == written


@pytest.mark.parametrize("name", ["prologiciix", "loro"])
def test_dee_rejects_lowercase_warp_names(tools, work, damf, name):
    result = joc(
        tools,
        damf_with_warp(damf, name),
        work / "warp_bad.ec3",
        "ddpjoc",
        "--duration",
        "1",
    )
    assert not result.ok
    assert "ATMOS_STORAGE_RES_FORMAT_INVALID" in result.out


def test_bed_conform_does_not_change_joc(tools, work, thd, damf):
    conformed = make_damf(tools, thd, work / "damf_conform", "--bed-conform")
    plain, bed = work / "conform_plain.ec3", work / "conform_bed.ec3"
    assert joc(tools, damf, plain, "ddpjoc", *SHORT).ok
    assert joc(tools, conformed, bed, "ddpjoc", *SHORT).ok
    assert md5(plain) == md5(bed)


# --- Warp mode -----------------------------------------------------------------------

WARPS = [None, "normal", "warping", "ProLogicIIx", "LoRo"]


def render(tools, name, src, out_dir):
    """Encode `src` with one of the encoders that render the master."""
    if name in ("ddpjoc", "bluray"):
        out = out_dir / f"{name}.ec3"
        return joc(tools, src, out, name, *SHORT), out
    if name == "ac4ajoc":
        out = out_dir / "ajoc.ac4"
        args = ["--level", "3", "--output-manifest", out.with_suffix(".json")]
        return tools.dee(
            "dee_ac4ajoc_encoder", "-i", src, "-o", out, *args, *SHORT
        ), out
    if name == "ac4ims":
        out = out_dir / "ims.ac4"
        args = ["--input-format", "atmos_mezz", "-i", src, "-o", out, *SHORT]
        return tools.dee("dee_ac4ims_encoder", *args), out
    out = out_dir / f"render.{'ac3' if name == 'dd' else 'ec3'}"
    args = ["--input-format", "atmos_mezz", "-i", src, "-o", out, "-e", name]
    args += ["--loudness-management", "measure_only", *SHORT]
    return tools.dee("dee_ddp_encoder", *args), out


@pytest.mark.parametrize("name", ["ddpjoc", "bluray", "ac4ajoc", "ac4ims", "ddp", "dd"])
def test_warp_mode_changes_rendered_output(tools, work, damf, name):
    """A master with no warp mode encodes as warping; each other value differs."""
    hashes = {}
    for warp in WARPS:
        out_dir = work / f"warp_{name}_{warp or 'none'}_{len(warp or '')}"
        out_dir.mkdir(exist_ok=True)
        result, out = render(tools, name, damf_with_warp(damf, warp), out_dir)
        assert result.ok, result.error()
        hashes[warp] = md5(out)
    assert hashes[None] == hashes["warping"]
    assert len({hashes[w] for w in WARPS[1:]}) == 4


def thd_atmos(tools, src, out_dir, legacy):
    out = out_dir / "o.thd"
    pres = f"atmos:number_of_elements=16:legacy_authoring={legacy}"
    result = tools.dee(
        "dee_dthd_encoder", "--presentation", pres, "--input-format", "atmos_mezz",
        "-i", src, "-o", out, "--temp-dir", out_dir, *SHORT,
    )  # fmt: skip
    assert result.ok, result.error()
    return out


@pytest.mark.parametrize("legacy", [0, 1])
def test_warp_mode_is_only_a_flag_in_truehd(tools, work, damf, legacy):
    """TrueHD codes the objects, so warp mode changes no decoded content.

    legacy_authoring=0 keeps the flag (none becomes warping); 1 drops it.
    """
    content, flags = set(), {}
    for warp in (None, "normal", "ProLogicIIx"):
        out_dir = work / f"thdwarp_{legacy}_{warp or 'none'}"
        out_dir.mkdir(exist_ok=True)
        out = thd_atmos(tools, damf_with_warp(damf, warp), out_dir, legacy)
        decoded = out_dir / "dec"
        content.add(truehd_content(tools, out, decoded))
        flags[warp] = warp_mode(decoded / "m.atmos")
    assert len(content) == 1
    if legacy:
        assert set(flags.values()) == {None}
    else:
        assert flags == {
            None: "warping",
            "normal": "normal",
            "ProLogicIIx": "ProLogicIIx",
        }


@pytest.mark.parametrize("legacy", [0, 1])
def test_truehd_atmos_bytes_change_between_runs(tools, work, damf, legacy):
    """TrueHD golden tests must compare decoded content, never file hashes."""
    outs, content = [], set()
    for run_no in (1, 2):
        out_dir = work / f"thddet_{legacy}_{run_no}"
        out_dir.mkdir(exist_ok=True)
        out = thd_atmos(tools, damf, out_dir, legacy)
        outs.append(md5(out))
        content.add(truehd_content(tools, out, out_dir / "dec"))
    assert outs[0] != outs[1]
    assert len(content) == 1
