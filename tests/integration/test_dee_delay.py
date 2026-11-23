"""Encoder delays of the DEE 6.7 tools, measured with a decoded impulse.

The impulse sits at frame 48000 of a 3 s WAV in every channel. The delay is where
the decoded peak of channel 0 lands, minus 48000.
"""

import re

import pytest

from .harness import SR, codec_delay, decode, impulse_wav

AT = SR
DOWNMIX = 32  # extra samples when DEE itself changes the channel count
EXT = {"dd": "ac3", "ddp": "ec3", "bluray": "eb3", "bluray_secondary": "ec3"}


@pytest.fixture(scope="module")
def imp(work):
    cache = {}

    def get(channels: int):
        if channels not in cache:
            cache[channels] = impulse_wav(work / f"imp{channels}.wav", channels)
        return cache[channels]

    return get


def safe(label: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", label)


def ddp_delay(tools, work, imp, mode, channels, layout=None, eopts="", extra=()):
    name = f"delay_{mode}_{channels}_{layout}_{eopts}_{'_'.join(extra)}.{EXT[mode]}"
    out = work / safe(name)
    args = ["--input-format", "wav", "-i", imp(channels), "-o", out]
    args += ["-e", mode + eopts, "--loudness-management", "measure_only", *extra]
    if layout:
        args += ["-c", layout]
    result = tools.dee("dee_ddp_encoder", *args)
    assert result.ok, result.error()
    pcm = decode(tools, out)
    return pcm.peak(0)[0] - AT, pcm.channels


@pytest.mark.parametrize(
    ("mode", "channels", "out_channels"),
    [
        ("dd", 1, 1),
        ("dd", 2, 2),
        ("dd", 6, 6),
        ("ddp", 1, 1),
        ("ddp", 2, 2),
        ("ddp", 6, 6),
        ("bluray", 8, 8),
        ("bluray_secondary", 2, 2),
        ("bluray_secondary", 6, 6),
    ],
)
def test_ddp_same_layout_is_256(tools, work, imp, mode, channels, out_channels):
    delay, got_channels = ddp_delay(tools, work, imp, mode, channels)
    assert got_channels == out_channels
    assert delay == 256


@pytest.mark.parametrize(
    ("mode", "channels", "layout", "out_channels"),
    [
        ("dd", 8, None, 6),  # -e dd and -e ddp take 7.1 and code 5.1
        ("ddp", 8, None, 6),
        ("dd", 6, "stereo", 2),
        ("ddp", 6, "stereo", 2),
        ("ddp", 8, "stereo", 2),
        ("dd", 6, "mono", 1),
        ("ddp", 6, "mono", 1),
        ("ddp", 2, "mono", 1),
    ],
)
def test_ddp_downmix_in_dee_adds_32(
    tools, work, imp, mode, channels, layout, out_channels
):
    delay, got_channels = ddp_delay(tools, work, imp, mode, channels, layout)
    assert got_channels == out_channels
    # DDP mono peaks one sample late; the filters smear the impulse.
    assert abs(delay - (256 + DOWNMIX)) <= 1


@pytest.mark.parametrize(
    "eopts",
    [
        ":surround_90deg_phase_shift=0",
        ":surround_3dB_attenuation=1",
        ":preferred_downmix_mode=ltrt",
        ":loro_cmix=0",
    ],
)
def test_downmix_delay_ignores_downmix_options(tools, work, imp, eopts):
    delay, _ = ddp_delay(tools, work, imp, "ddp", 6, "stereo", eopts)
    assert delay == 256 + DOWNMIX


@pytest.mark.parametrize(
    "mode", ["skip:dialnorm=-31", "measure_only", "measure_and_correct"]
)
def test_loudness_mode_does_not_change_delay(tools, work, imp, mode):
    out = work / safe(f"lm_{mode}.ec3")
    result = tools.dee(
        "dee_ddp_encoder", "--input-format", "wav", "-i", imp(2), "-o", out,
        "-e", "ddp", "--loudness-management", mode,
    )  # fmt: skip
    assert result.ok, result.error()
    assert decode(tools, out).peak(0)[0] - AT == 256


@pytest.mark.parametrize(
    ("layout", "args", "expected"),
    [
        (None, ("--start", "0.005333"), 0),  # 256 samples
        (None, ("--add-silence", "0.094667:0"), 4800),  # +100 ms
        (None, ("--start", "0.105333"), -4800),  # -100 ms
        ("stereo", ("--start", "0.006"), 0),  # 288 samples
    ],
)
def test_start_and_add_silence_are_sample_exact(
    tools, work, imp, layout, args, expected
):
    channels = 6 if layout else 2
    delay, _ = ddp_delay(tools, work, imp, "ddp", channels, layout, extra=args)
    assert delay == expected


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        # 1743.98 and 1744.03 samples: --add-silence drops the part sample
        (("--start", "0", "--add-silence", "0.036333:0"), 256 + 1743),
        (("--start", "0", "--add-silence", "0.036334:0"), 256 + 1744),
        # 0.48 and 0.53 samples: --start rounds to the nearest
        (("--start", "0.000010"), 256),
        (("--start", "0.000011"), 256 - 1),
    ],
)
def test_add_silence_truncates_and_start_rounds(tools, work, imp, args, expected):
    delay, _ = ddp_delay(tools, work, imp, "ddp", 2, extra=args)
    assert delay == expected


@pytest.mark.parametrize(
    ("presentation", "channels"), [("2ch", 2), ("6ch", 6), ("8ch", 8)]
)
def test_truehd_has_no_delay(tools, work, imp, presentation, channels):
    out = work / f"delay_thd_{presentation}.thd"
    result = tools.dee(
        "dee_dthd_encoder", "--presentation", presentation, "--input-format", "wav",
        "-i", imp(channels), "-o", out, "--loudness-management", "measure_only",
    )  # fmt: skip
    assert result.ok, result.error()
    pcm = decode(tools, out)
    assert pcm.channels == channels
    assert pcm.peak(0)[0] - AT == 0


# (encoder, kbps): the delay DEE logs as "Codec delay:". It changes with the rate.
AAC_DELAYS = {
    ("aaclc", 56): 1710,
    ("aaclc", 64): 1710,
    ("aaclc", 71): 1710,
    ("aaclc", 72): 1702,
    ("aaclc", 87): 1702,
    ("aaclc", 88): 1600,
    ("aaclc", 128): 1600,
    ("aaclc", 256): 1600,
    ("aaclc", 576): 1600,
    ("heaac", 16): 4480,
    ("heaac", 24): 4407,
    ("heaac", 32): 4374,
    ("heaac", 48): 4307,
    ("heaac", 56): 4294,
    ("heaac", 64): 4280,
    ("heaac", 72): 4280,
    ("heaac", 80): 4347,
    ("heaac", 143): 4347,
    ("heaacv2", 14): 7172,
    ("heaacv2", 32): 7172,
    ("heaacv2", 63): 7172,
}


def aac(tools, work, imp, encoder, rate, channels=2, extra=()):
    out = work / safe(f"delay_aac_{encoder}_{rate}_{channels}_{'_'.join(extra)}.aac")
    result = tools.dee(
        "dee_aac_encoder", "--loglevel", "debug", "--input-format", "wav",
        "-i", imp(channels), "-o", out, "-e", encoder, "--data-rate", str(rate),
        "--loudness-management", "skip", *extra,
    )  # fmt: skip
    return result, out


@pytest.mark.parametrize(("encoder", "rate"), list(AAC_DELAYS))
def test_aac_delay_depends_on_rate(tools, work, imp, encoder, rate):
    result, out = aac(tools, work, imp, encoder, rate)
    assert result.ok, result.error()
    expected = AAC_DELAYS[(encoder, rate)]
    assert codec_delay(result.out) == expected
    # The decoded impulse peaks up to 3 samples early at low rates.
    assert -3 <= decode(tools, out).peak(0)[0] - AT - expected <= 0


@pytest.mark.parametrize(("channels", "rate"), [(1, 64), (6, 64), (8, 64), (6, 256)])
def test_aac_downmix_and_upmix_add_32_unlogged(tools, work, imp, channels, rate):
    result, out = aac(tools, work, imp, "aaclc", rate, channels)
    assert result.ok, result.error()
    logged = codec_delay(result.out)
    assert logged == AAC_DELAYS[("aaclc", rate)]  # the log leaves the 32 out
    pcm = decode(tools, out)
    assert pcm.channels == 2  # AAC output is always 2.0
    assert abs(pcm.peak(0)[0] - AT - (logged + DOWNMIX)) <= 1


def test_aac_start_compensation(tools, work, imp):
    # --start defaults to 0 for AAC. 1710 samples is 0.035625 s.
    result, out = aac(tools, work, imp, "aaclc", 64, extra=("--start", "0.035625"))
    assert result.ok, result.error()
    assert -1 <= decode(tools, out).peak(0)[0] - AT <= 0
