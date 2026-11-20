"""Channel-based encodes through dee_shim."""

import pytest

from .harness import decode, impulse_wav, mediainfo, noise_wav


@pytest.mark.parametrize(
    ("layout", "fmt"),
    [("7.1/eac3", "E-AC-3"), ("7.1", "AC-3")],
)
def test_ddp_7_1_layouts(shim, work, layout, fmt):
    wav = impulse_wav(work / "shim_imp8.wav", 8)
    out = work / f"shim_ddp_{layout.replace('/', '_')}.ec3"
    result = shim.run_shim(
        "ddp_encoder",
        ["--layout", layout],
        [
            "--input-format",
            "wav",
            "-i",
            wav,
            "-o",
            out,
            "--loudness-management",
            "measure_only",
        ],
    )
    assert result.ok, result.error()
    info = mediainfo(out)
    assert info["format"] == fmt
    assert info["channel_layout"] == "L R C LFE Ls Rs Lb Rb"
    pcm = decode(shim, out)
    assert pcm.channels == 8
    assert pcm.peak(0)[0] - 48000 == 256


def test_truehd_drc_none_needs_the_shim(shim, work):
    wav = noise_wav(work / "shim_noise8.wav", 8, seconds=2.0)
    args = ["--input-format", "wav", "-i", wav, "--loudness-management", "measure_only"]
    args += ["--temp-dir", work]
    native = shim.dee(
        "dee_dthd_encoder", "--presentation", "8ch:drc_profile=none", *args,
        "-o", work / "thd_none_native.thd",
    )  # fmt: skip
    assert not native.ok
    assert "Invalid 'drc_profile' option value: 'none'" in native.out
    shimmed = shim.run_shim(
        "dthd_encoder", ["--drc", "none"],
        ["--presentation", "8ch", *args, "-o", work / "thd_none_shim.thd"],
    )  # fmt: skip
    assert shimmed.ok, shimmed.error()
