"""
DeeZy's aac format with the real tools: the encode lands on the source's
first sample at every profile, rate band and input layout, a piped encode
matches the temp-WAV encode, and a loudness target corrects the audio.

HE-AAC and HE-AACv2 from a source DEE downmixes (5.1, 7.1) can differ, piped
against the temp WAV, in the last ~100 ms, and only at some --start values
(seen at 4312 samples, not at 0, 32, 960 or 24000). Both are deterministic,
an impulse lands on the same sample at the same level, and both score the same
against an AAC-LC reference in the body and in the tail, so those encodes are
checked for timing and level, not bytes.

The planner and runner run in-process with the shipped default config, so the
tests use DEEZY_DEE_LICENSE rather than wherever DeeZy would find a license.
"""

from collections.abc import Iterator
import math
from pathlib import Path
import re
import subprocess
import sys

import pytest
import tomlkit

import deezy.cli as cli
from deezy.cli.payload_factory import PayloadBuilder
from deezy.cli.utils import apply_config_defaults_to_args, apply_default_bitrate
from deezy.config.defaults import CONF_DEFAULT
from deezy.config.manager import ConfigManager
from deezy.pipeline import run
from deezy.pipeline.encode import pipe_name
from deezy.pipeline.plan import PipeStep, PlanContext, plan_job
from deezy.track_info.mediainfo import MediainfoParser

from .harness import SR, decode, impulse_wav, md5, noise_wav

# the impulse, one second in
AT = SR


@pytest.fixture(scope="module")
def parser():
    main = cli.create_main_parser()
    sub = main.add_subparsers(dest="sub_command")
    groups = cli.create_common_argument_groups()
    cli.create_encode_parsers(sub, groups)
    return main


@pytest.fixture
def config() -> Iterator[ConfigManager]:
    ConfigManager.reset_instance()
    manager = ConfigManager()
    manager.config = tomlkit.parse(CONF_DEFAULT).unwrap()
    yield manager
    ConfigManager.reset_instance()


def encode(tools, work, parser, config, args, src: Path, pipe="never") -> Path:
    tag = "_".join(args).replace("-", "").replace("=", "") or "default"
    out = work / "aac_out" / f"{src.stem}_{tag}_{pipe}.aac"
    ns = parser.parse_args(
        ["--no-progress-bars", "encode", "aac", *args, "--pipe", pipe]
        + ["--overwrite", "--output", str(out), str(src)]
    )
    apply_default_bitrate(ns, config)
    apply_config_defaults_to_args(ns, config)
    payload = PayloadBuilder.build_aac_payload(
        ns, src, Path(tools.ffmpeg), None, tools.dee_dir
    )
    namer = MediainfoParser(src, payload.track_index)
    temp = run.temp_dir_path(src, out.parent / "temp", track_label=out.stem)
    ctx = PlanContext(
        namer=namer,
        temp_dir=temp,
        license=tools.license,
        config=config,
        pipe_name=pipe_name(temp),
    )
    plan = plan_job(payload, namer.get_audio_track_info(), ctx)
    piped = any(isinstance(step, PipeStep) for step in plan.steps)
    assert piped is (pipe == "always")
    run.init_phase_limits(max_parallel=1)
    return run.run_plan(plan, payload)


def impulse(work: Path, channels: int, rate: int = SR) -> Path:
    """An impulse in the first channel only, so a downmix keeps it in L."""
    path = work / f"aac_impulse_{channels}ch_{rate}.wav"
    if path.exists():
        return path
    return impulse_wav(path, channels, at=rate, which=[0], seconds=3.0, rate=rate)


def noise(work: Path, channels: int) -> Path:
    path = work / f"aac_noise_{channels}ch.wav"
    return path if path.exists() else noise_wav(path, channels, seconds=3.0)


# (id, arguments after 'encode aac', source channels, delay in samples)
ALIGNED = [
    ("lc_192_2ch", [], 2, 0),
    ("lc_192_1ch", [], 1, 0),
    ("lc_192_51", [], 6, 0),
    ("lc_192_71", [], 8, 0),
    ("lc_192_3ch", [], 3, 0),
    ("lc_64", ["--bitrate", "64"], 2, 0),
    ("lc_80", ["--bitrate", "80"], 2, 0),
    ("he_64", ["--aac-profile", "heaac"], 2, 0),
    ("he_100_51", ["--aac-profile", "heaac", "--bitrate", "100"], 6, 0),
    ("hev2_56", ["--aac-profile", "heaacv2"], 2, 0),
    ("lc_delay_pos", ["--delay=100ms"], 2, 4800),
    ("lc_delay_neg_51", ["--delay=-100ms"], 6, -4800),
]


@pytest.mark.parametrize(
    ("args", "channels", "delay"),
    [pytest.param(a, c, d, id=i) for i, a, c, d in ALIGNED],
)
def test_aac_lands_on_the_source_sample(
    tools, work, parser, config, args, channels, delay
):
    out = encode(tools, work, parser, config, args, impulse(work, channels))
    pcm = decode(tools, out)
    assert pcm.channels == 2  # AAC output is always 2.0
    frame, level = pcm.peak(0)
    assert level > 0.05
    # the decoded impulse peaks up to 3 samples early at low rates
    assert -3 <= frame - (AT + delay) <= 1


def test_a_441_source_lands_on_its_sample(tools, work, parser, config):
    out = encode(tools, work, parser, config, [], impulse(work, 2, rate=44100))
    assert -3 <= decode(tools, out).peak(0)[0] - AT <= 1


@pytest.mark.skipif(sys.platform != "win32", reason="DeeZy pipes only on Windows")
@pytest.mark.parametrize(
    ("args", "channels"),
    [
        pytest.param([], 2, id="lc_2ch"),
        pytest.param([], 6, id="lc_51"),
        pytest.param([], 8, id="lc_71"),
        pytest.param(["--aac-profile", "heaac"], 2, id="he_2ch"),
        pytest.param(["--aac-profile", "heaacv2"], 2, id="hev2_2ch"),
        pytest.param(["--delay=-20ms"], 6, id="delay_neg"),
        pytest.param(["--loudness-target", "-20"], 2, id="target"),
    ],
)
def test_piped_aac_matches_the_wav_encode(tools, work, parser, config, args, channels):
    src = noise(work, channels)
    wav = encode(tools, work, parser, config, args, src, pipe="never")
    piped = encode(tools, work, parser, config, args, src, pipe="always")
    assert md5(piped) == md5(wav)


@pytest.mark.skipif(sys.platform != "win32", reason="DeeZy pipes only on Windows")
@pytest.mark.parametrize(
    ("args", "channels"),
    [
        pytest.param(["--aac-profile", "heaac"], 6, id="he_51"),
        pytest.param(["--aac-profile", "heaacv2"], 6, id="hev2_51"),
        pytest.param(["--aac-profile", "heaac"], 8, id="he_71"),
    ],
)
def test_piped_he_aac_from_a_downmix_lines_up_with_the_wav_encode(
    tools, work, parser, config, args, channels
):
    src = impulse(work, channels)
    wav = decode(tools, encode(tools, work, parser, config, args, src, "never"))
    piped = decode(tools, encode(tools, work, parser, config, args, src, "always"))
    assert piped.frames == wav.frames
    assert piped.peak(0) == wav.peak(0)
    # on dense audio the two may differ near the end; their level doesn't
    src = noise(work, channels)
    wav = decode(tools, encode(tools, work, parser, config, args, src, "never"))
    piped = decode(tools, encode(tools, work, parser, config, args, src, "always"))
    tail = slice(wav.frames - SR // 4, wav.frames)
    for c in range(2):
        energy = [sum(v * v for v in pcm.floats(c)[tail]) for pcm in (wav, piped)]
        assert abs(10 * math.log10(energy[1] / energy[0])) < 0.5, f"channel {c}"


def integrated_loudness(tools, path: Path) -> float:
    """FFmpeg's EBU R128 integrated loudness of the decoded file."""
    result = subprocess.run(  # noqa: S603
        [tools.ffmpeg, "-hide_banner", "-nostats", "-i", str(path)]
        + ["-af", "ebur128", "-f", "null", "-"],
        capture_output=True,
        text=True,
        check=True,
    )
    found = re.findall(r"I:\s+(-?\d+(?:\.\d+)?) LUFS", result.stderr)
    return float(found[-1])


def test_skip_leaves_the_loudness_and_a_target_corrects_it(tools, work, parser, config):
    src = noise(work, 2)
    source = integrated_loudness(tools, src)
    kept = encode(tools, work, parser, config, [], src)
    corrected = encode(tools, work, parser, config, ["--loudness-target", "-30"], src)
    assert abs(integrated_loudness(tools, kept) - source) < 0.5
    # white noise has no speech, so DEE gates on level, as R128 does
    assert abs(integrated_loudness(tools, corrected) - -30) < 1.0
