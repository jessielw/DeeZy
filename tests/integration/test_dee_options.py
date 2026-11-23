"""Which options the DEE 6.7 tools accept, and their defaults."""

import re

import pytest

from .harness import decode, impulse_wav, md5, mediainfo, noise_wav, staggered_wav

ENCODERS = [
    "dee_ddp_encoder",
    "dee_ddpjoc_encoder",
    "dee_dthd_encoder",
    "dee_ac4_encoder",
    "dee_ac4ajoc_encoder",
    "dee_ac4ims_encoder",
    "dee_aac_encoder",
]


@pytest.fixture(scope="module")
def wavs(work):
    return {
        2: noise_wav(work / "noise2.wav", 2, seconds=2.0),
        6: noise_wav(work / "noise6.wav", 6, seconds=2.0),
        8: noise_wav(work / "noise8.wav", 8, seconds=2.0),
    }


def ddp(tools, wav, out, *args, encoder="ddp", loudness="measure_only"):
    return tools.dee(
        "dee_ddp_encoder", "--input-format", "wav", "-i", wav, "-o", out,
        "-e", encoder, "--loudness-management", loudness, *args,
    )  # fmt: skip


# --- Help text -------------------------------------------------------------------


@pytest.mark.parametrize("tool", ENCODERS)
def test_start_default(tools, tool):
    found = re.search(r"--start arg \(=([^)]*)\)", tools.help(tool))
    assert found, "no --start option"
    assert found.group(1) == (
        "0" if tool == "dee_aac_encoder" else "first_frame_of_action"
    )


@pytest.mark.parametrize(
    ("tool", "has_temp_dir"),
    [
        ("dee_ddp_encoder", True),
        ("dee_dthd_encoder", True),
        ("dee_ac4_encoder", True),
        ("dee_aac_encoder", True),
        ("dee_ddpjoc_encoder", False),
        ("dee_ac4ajoc_encoder", False),
        ("dee_ac4ims_encoder", False),
        ("dee_measure_loudness", False),
    ],
)
def test_temp_dir_option(tools, tool, has_temp_dir):
    assert ("--temp-dir" in tools.help(tool)) is has_temp_dir


def test_ac4ajoc_has_no_input_format_and_needs_level_and_manifest(tools, work):
    assert "--input-format" not in tools.help("dee_ac4ajoc_encoder")
    fake = work / "missing.atmos"
    no_level = tools.dee(
        "dee_ac4ajoc_encoder", "-i", fake, "-o", work / "x.ac4",
        "--output-manifest", work / "x.json",
    )  # fmt: skip
    assert not no_level.ok and "level" in no_level.error()
    no_manifest = tools.dee(
        "dee_ac4ajoc_encoder", "-i", fake, "-o", work / "x.ac4", "--level", "3"
    )
    assert not no_manifest.ok and "output-manifest" in no_manifest.error()


@pytest.mark.parametrize(
    ("tool", "modes"),
    [
        ("dee_ddp_encoder", "measure_and_correct"),
        ("dee_ddpjoc_encoder", "measure_only"),
        ("dee_dthd_encoder", "measure_only"),
        ("dee_ac4_encoder", "measure_and_correct"),
        ("dee_ac4ajoc_encoder", "measure_only"),
        ("dee_ac4ims_encoder", "measure_only"),
        ("dee_aac_encoder", "measure_and_correct"),
    ],
)
def test_loudness_default(tools, tool, modes):
    found = re.search(r"--loudness-management arg \(=([^)]*)\)", tools.help(tool))
    assert found and found.group(1) == modes


# --- Loudness --------------------------------------------------------------------


def test_custom_dialnorm_key_is_dialnorm(tools, work, wavs):
    """Bug 1: 1.5.0 sends skip:custom_dialnorm=N."""
    out = work / "dialnorm.ec3"
    good = ddp(tools, wavs[2], out, loudness="skip:dialnorm=-27")
    assert good.ok, good.error()
    assert int(mediainfo(out)["dialnorm_average"]) == -27
    bad = ddp(
        tools, wavs[2], work / "dialnorm_bad.ec3", loudness="skip:custom_dialnorm=-27"
    )
    assert not bad.ok
    assert "Required option: 'dialnorm' not found" in bad.out


def test_aac_has_no_measure_only(tools, work, wavs):
    def aac(mode):
        return tools.dee(
            "dee_aac_encoder", "--input-format", "wav", "-i", wavs[2],
            "-o", work / "lm.aac", "--loudness-management", mode,
        )  # fmt: skip

    assert not aac("measure_only").ok
    assert aac("skip").ok
    assert aac("measure_and_correct").ok


@pytest.mark.parametrize(
    ("target", "ok"), [(-31, True), (-8, True), (-32, False), (-7, False)]
)
def test_ddp_loudness_target_range(tools, work, wavs, target, ok):
    mode = f"measure_and_correct:loudness_target={target}"
    assert ddp(tools, wavs[2], work / "target.ec3", loudness=mode).ok is ok


@pytest.mark.parametrize(
    ("target", "ok"), [(-31, True), (-10, True), (-32, False), (-9, False)]
)
def test_ac4_loudness_target_range(tools, work, wavs, target, ok):
    result = tools.dee(
        "dee_ac4_encoder", "--input-format", "wav", "-i", wavs[2], "-o", work / "t.ac4",
        "--output-manifest", work / "t.json",
        "--loudness-management", f"measure_and_correct:loudness_target={target}",
    )  # fmt: skip
    assert result.ok is ok


# --- DRC -------------------------------------------------------------------------


def test_drc_none(tools, work, wavs):
    """Bug 7: DD, DDP and IMS take none; the AC-4 channel encoder does not."""
    for encoder, ext in (("dd", "ac3"), ("ddp", "ec3")):
        out = work / f"drc_{encoder}.{ext}"
        result = ddp(tools, wavs[6], out, encoder=f"{encoder}:drc_profile=none")
        assert result.ok, result.error()
    ims = tools.dee(
        "dee_ac4ims_encoder", "--input-format", "wav", "-i", wavs[6],
        "-o", work / "drc_ims.ac4", "-e", "mode=general:drc_profile=none",
    )  # fmt: skip
    assert ims.ok, ims.error()
    ac4 = tools.dee(
        "dee_ac4_encoder", "--input-format", "wav", "-i", wavs[6], "-o", work / "drc.ac4",
        "--output-manifest", work / "drc.json", "-e", "drc_profile=none",
        "--loudness-management", "measure_only",
    )  # fmt: skip
    assert not ac4.ok


# --- AC-4 IMS --------------------------------------------------------------------


def ims(tools, wav, out, *args):
    return tools.dee(
        "dee_ac4ims_encoder", "--input-format", "wav", "-i", wav, "-o", out, *args
    )


def test_ims_takes_mode_not_profile(tools, work, wavs):
    """Bug 2: 1.5.0 sends -e profile=..."""
    assert ims(tools, wavs[6], work / "ims.ac4", "-e", "mode=general").ok
    bad = ims(tools, wavs[6], work / "ims_bad.ac4", "-e", "profile=ims")
    assert not bad.ok
    assert 'Invalid options: "profile"' in bad.out


def test_ims_music_mode_needs_music_light_and_no_di(tools, work, wavs):
    out = work / "music.ac4"
    no_di = ("--loudness-management", "measure_only:dialogue_intelligence=0")
    assert not ims(tools, wavs[6], out, "-e", "mode=music", *no_di).ok
    light = "mode=music:drc_profile=music_light"
    di_on = ims(tools, wavs[6], out, "-e", light)
    assert not di_on.ok
    assert "Dialogue intelligence must be disabled" in di_on.out
    good = ims(tools, wavs[6], out, "-e", light, *no_di)
    assert good.ok, good.error()


@pytest.mark.parametrize(
    ("rate", "ok"),
    [
        (64, True),
        (96, True),
        (128, True),
        (144, True),
        (256, True),
        (320, True),
        (192, False),
        (448, False),
    ],
)
def test_ims_rates(tools, work, wavs, rate, ok):
    assert ims(tools, wavs[6], work / "rate.ac4", "--data-rate", str(rate)).ok is ok


def test_ims_rejects_forward_slash_paths(tools, work, wavs):
    if "\\" not in str(wavs[6]):
        pytest.skip("only Windows paths have backslashes")
    native = ims(tools, wavs[6], work / "slash.ac4")
    assert native.ok, native.error()
    slashed = ims(
        tools,
        str(wavs[6]).replace("\\", "/"),
        str(work / "slash2.ac4").replace("\\", "/"),
    )
    assert not slashed.ok


# --- AAC -------------------------------------------------------------------------


def test_heaacv2_rate_limit(tools, work, wavs):
    def run_rate(rate):
        return tools.dee(
            "dee_aac_encoder", "--input-format", "wav", "-i", wavs[2], "-o", work / "v2.aac",
            "-e", "heaacv2", "--data-rate", str(rate), "--loudness-management", "skip",
        )  # fmt: skip

    assert run_rate(63).ok
    assert not run_rate(64).ok


# --- Measurement -----------------------------------------------------------------


@pytest.mark.parametrize(("channels", "ok"), [(2, True), (6, True), (8, False)])
def test_measure_loudness_layouts(tools, work, wavs, channels, ok):
    result = tools.dee(
        "dee_measure_loudness", "--input-format", "wav", "-i", wavs[channels],
        "--output-manifest", work / f"measure{channels}.json",
    )  # fmt: skip
    assert result.ok is ok


# --- Output ----------------------------------------------------------------------


CHANNEL_ENCODES = {
    "ddp": (
        "dee_ddp_encoder",
        ".ec3",
        ["-e", "ddp", "--loudness-management", "measure_only"],
    ),
    "thd": (
        "dee_dthd_encoder",
        ".thd",
        ["--presentation", "6ch", "--loudness-management", "measure_only"],
    ),
    "ac4": ("dee_ac4_encoder", ".ac4", ["--loudness-management", "measure_only"]),
    "aac": ("dee_aac_encoder", ".aac", ["--loudness-management", "skip"]),
}


@pytest.mark.parametrize("name", list(CHANNEL_ENCODES))
def test_channel_based_output_is_deterministic(tools, work, wavs, name):
    """TrueHD Atmos is the exception; see test_dee_atmos."""
    tool, ext, args = CHANNEL_ENCODES[name]
    outs = []
    for run_no in (1, 2):
        out = work / f"det_{name}_{run_no}{ext}"
        extra = ["--output-manifest", out.with_suffix(".json")] if name == "ac4" else []
        result = tools.dee(
            tool, *args, "--input-format", "wav", "-i", wavs[6], "-o", out, *extra,
            "--temp-dir", work,
        )  # fmt: skip
        assert result.ok, result.error()
        outs.append(out)
    assert md5(outs[0]) == md5(outs[1])


def test_ddp_mode_downmixes_7_1_but_bluray_keeps_it(tools, work, wavs):
    out = work / "ddp71.ec3"
    assert ddp(tools, wavs[8], out).ok
    assert int(mediainfo(out)["channel_s"]) == 6
    out = work / "bluray71.eb3"
    result = ddp(tools, wavs[8], out, encoder="bluray")
    assert result.ok, result.error()
    info = mediainfo(out)
    assert int(info["channel_s"]) == 8
    assert int(info["bit_rate"]) == 768000  # Dolby's automatic rate


def test_surround_3db_attenuation_lowers_the_surrounds(tools, work):
    wav = impulse_wav(work / "att6.wav", 6)
    peaks = {}
    for flag in (0, 1):
        out = work / f"att{flag}.ec3"
        result = ddp(tools, wav, out, encoder=f"ddp:surround_3dB_attenuation={flag}")
        assert result.ok, result.error()
        pcm = decode(tools, out)
        peaks[flag] = [pcm.peak(c)[1] for c in (4, 5)]
    for off, on in zip(peaks[0], peaks[1], strict=True):
        assert on < off * 0.75  # at least 2.5 dB lower


# --- Channel order -----------------------------------------------------------------


def arrival_order(pcm, start, step, delay):
    """For each decoded channel, which input channel's impulse it carries."""
    order = []
    for c in range(pcm.channels):
        frame, amp = pcm.peak(c)
        order.append(round((frame - delay - start) / step) if amp > 1e-4 else None)
    return order


def test_ddp_5_1_channel_order(tools, work):
    wav = staggered_wav(work / "stag6.wav", 6)
    out = work / "stag6.ec3"
    assert ddp(tools, wav, out).ok
    assert arrival_order(decode(tools, out), 48000, 2400, 256) == [0, 1, 2, 3, 4, 5]


def test_bluray_7_1_channel_order(tools, work):
    """DEE's WAV slots 5-6 are the side surrounds; ffmpeg's 7.1 puts the backs there."""
    wav = staggered_wav(work / "stag8.wav", 8)
    out = work / "stag8.eb3"
    result = ddp(tools, wav, out, encoder="bluray")
    assert result.ok, result.error()
    # ffmpeg order is FL FR FC LFE BL BR SL SR.
    assert arrival_order(decode(tools, out), 48000, 2400, 256) == [
        0,
        1,
        2,
        3,
        6,
        7,
        4,
        5,
    ]


def test_truehd_7_1_channel_order(tools, work):
    wav = staggered_wav(work / "stag8.wav", 8)
    out = work / "stag8.thd"
    result = tools.dee(
        "dee_dthd_encoder", "--presentation", "8ch", "--input-format", "wav",
        "-i", wav, "-o", out, "--loudness-management", "measure_only",
    )  # fmt: skip
    assert result.ok, result.error()
    assert arrival_order(decode(tools, out), 48000, 2400, 0) == [0, 1, 2, 3, 6, 7, 4, 5]
