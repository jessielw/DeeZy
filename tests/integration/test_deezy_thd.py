"""
DeeZy's channel-based thd format with the real tools.

TrueHD is lossless at 48 kHz, so a decoded encode must equal its source sample
for sample, channel for channel, which also proves the delay (none) and the
7.1 channel order. Layouts TrueHD lacks are padded with silent channels and
must keep every source channel bit-exact. At 96 kHz DEE's apodizing filter
changes the audio, so those encodes are checked for timing only.

The planner and runner run in-process with the shipped default config, so the
tests use DEEZY_DEE_LICENSE rather than wherever DeeZy would find a license.
"""

from collections.abc import Iterator
from pathlib import Path
import re
import subprocess

import pytest
import tomlkit

import deezy.cli as cli
from deezy.cli.payload_factory import PayloadBuilder
from deezy.cli.utils import apply_config_defaults_to_args, apply_default_bitrate
from deezy.config.defaults import CONF_DEFAULT
from deezy.config.manager import ConfigManager
from deezy.pipeline import run
from deezy.pipeline.plan import PlanContext, plan_job
from deezy.track_info.mediainfo import MediainfoParser

from .harness import SR, decode, impulse_wav, mediainfo, noise_wav

# the impulse, one second in
AT = SR


@pytest.fixture(scope="module")
def thd_tools(tools):
    if not tools.tool("dee_dthd_encoder").is_file():
        pytest.skip("DEEZY_DEE_DIR lacks dee_dthd_encoder")
    return tools


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


def encode(tools, work, parser, config, args, src: Path) -> Path:
    tag = "_".join(args).replace("-", "").replace("=", "") or "default"
    out = work / "thd_out" / f"{src.stem}_{tag}.thd"
    ns = parser.parse_args(
        ["--no-progress-bars", "encode", "thd", *args]
        + ["--overwrite", "--output", str(out), str(src)]
    )
    apply_default_bitrate(ns, config)
    apply_config_defaults_to_args(ns, config)
    payload = PayloadBuilder.build_thd_payload(
        ns, src, Path(tools.ffmpeg), None, tools.dee_dir
    )
    namer = MediainfoParser(src, payload.track_index)
    temp = run.temp_dir_path(src, out.parent / "temp", track_label=out.stem)
    ctx = PlanContext(namer=namer, temp_dir=temp, license=tools.license, config=config)
    plan = plan_job(payload, namer.get_audio_track_info(), ctx)
    run.init_phase_limits(max_parallel=1)
    return run.run_plan(plan, payload)


def noise(work: Path, channels: int) -> Path:
    """White noise, a different sequence in every channel."""
    path = work / f"thd_noise_{channels}ch.wav"
    return path if path.exists() else noise_wav(path, channels, seconds=3.0)


def layout_noise(tools, work: Path, layout: str, count: int) -> Path:
    """White noise in ``layout``, a different seed in every channel."""
    name = re.sub(r"[^0-9a-z]", "", layout)
    path = work / f"thd_{name}.wav"
    if not path.exists():
        inputs = []
        for i in range(count):
            inputs += ["-f", "lavfi", "-i", f"anoisesrc=d=2:c=white:a=0.2:seed={i + 7}"]
        joined = "".join(f"[{i}:a]" for i in range(count))
        subprocess.run(  # noqa: S603
            [tools.ffmpeg, "-v", "error", "-y", *inputs, "-filter_complex"]
            + [f"{joined}join=inputs={count}:channel_layout={layout}[o]", "-map"]
            + ["[o]", "-ar", str(SR), "-c:a", "pcm_s24le", str(path)],
            check=True,
        )
    return path


def impulse(work: Path, channels: int, rate: int = SR) -> Path:
    path = work / f"thd_impulse_{channels}ch_{rate}.wav"
    if path.exists():
        return path
    return impulse_wav(path, channels, at=rate, which=[0], seconds=3.0, rate=rate)


@pytest.mark.parametrize("channels", [2, 6, 8])
def test_truehd_decodes_to_its_source_exactly(
    thd_tools, work, parser, config, channels
):
    src = noise(work, channels)
    out = decode(thd_tools, encode(thd_tools, work, parser, config, [], src))
    ref = decode(thd_tools, src)
    assert out.channels == channels
    assert out.frames == ref.frames
    for c in range(channels):
        assert out.channel(c) == ref.channel(c), f"channel {c}"


def test_mono_is_copied_into_both_channels(thd_tools, work, parser, config):
    src = noise(work, 1)
    out = decode(thd_tools, encode(thd_tools, work, parser, config, [], src))
    ref = decode(thd_tools, src).channel(0)
    assert out.channels == 2
    assert out.channel(0) == ref
    assert out.channel(1) == ref


# (layout, its channel count, the 5.1 slot each source channel lands in)
PADDED = [
    ("3.0", 3, [0, 1, 2]),
    ("2.1", 3, [0, 1, 3]),
    ("quad", 4, [0, 1, 4, 5]),
    ("5.0(side)", 5, [0, 1, 2, 4, 5]),
]


@pytest.mark.parametrize(
    ("layout", "count", "slots"), PADDED, ids=[p[0] for p in PADDED]
)
def test_a_padded_layout_keeps_every_channel_exact(
    thd_tools, work, parser, config, layout, count, slots
):
    src = layout_noise(thd_tools, work, layout, count)
    out = decode(thd_tools, encode(thd_tools, work, parser, config, [], src))
    ref = decode(thd_tools, src)
    assert out.channels == 6
    for c, slot in enumerate(slots):
        assert out.channel(slot) == ref.channel(c), f"{layout} channel {c}"
    for slot in set(range(6)) - set(slots):
        assert not any(out.channel(slot)), f"slot {slot} is not silent"


def test_61_is_padded_to_71_with_its_sides_kept(thd_tools, work, parser, config):
    src = layout_noise(thd_tools, work, "6.1", 7)
    out = decode(thd_tools, encode(thd_tools, work, parser, config, [], src))
    ref = decode(thd_tools, src)
    assert out.channels == 8
    # FL FR FC LFE stay; FFmpeg's 6.1 has its sides last, as its 7.1 does
    for c, slot in [(0, 0), (1, 1), (2, 2), (3, 3), (5, 6), (6, 7)]:
        assert out.channel(slot) == ref.channel(c), f"channel {c}"


# (id, arguments after 'encode thd', source channels, rate, delay in samples)
ALIGNED = [
    ("delay_pos", ["--delay=100ms"], 6, SR, 4800),
    ("delay_neg_71", ["--delay=-20ms"], 8, SR, -960),
    ("downmix_51_from_71", ["--channels", "6"], 8, SR, 0),
    ("downmix_20_from_51", ["--channels", "2"], 6, SR, 0),
    ("resampled_441", [], 2, 44100, 0),
    ("drc_dialnorm", ["--drc", "speech", "--custom-dialnorm", "-27"], 6, SR, 0),
]


@pytest.mark.parametrize(
    ("args", "channels", "rate", "delay"),
    [pytest.param(a, c, r, d, id=i) for i, a, c, r, d in ALIGNED],
)
def test_truehd_lands_on_the_source_sample(
    thd_tools, work, parser, config, args, channels, rate, delay
):
    src = impulse(work, channels, rate)
    out = decode(thd_tools, encode(thd_tools, work, parser, config, args, src))
    frame, level = out.peak(0)
    assert level > 0.05
    # a resampled impulse may peak a sample early
    assert -1 <= frame - (AT + delay) <= 0


@pytest.mark.parametrize("channels", [2, 8])
def test_96k_stays_96k_and_on_time(thd_tools, work, parser, config, channels):
    src = impulse(work, channels, 96000)
    out_path = encode(thd_tools, work, parser, config, [], src)
    assert int(mediainfo(out_path)["sampling_rate"]) == 96000
    frame, _level = decode(thd_tools, out_path).peak(0)
    # DEE's apodizing filter moves the peak by a sample at 96 kHz
    assert abs(frame - 96000) <= 1


def test_the_atmos_sample_encodes_as_71(thd_tools, work, parser, config):
    if not thd_tools.atmos_sample:
        pytest.skip("needs DEEZY_ATMOS_SAMPLE")
    out = encode(thd_tools, work, parser, config, [], thd_tools.atmos_sample)
    track = mediainfo(out)
    assert int(track["channel_s"]) == 8


@pytest.mark.parametrize("channels", [2, 6, 8])
def test_surround_attenuation(thd_tools, work, parser, config, channels):
    src = noise(work, channels)
    output = encode(thd_tools, work, parser, config, ["--surround-3db"], src)
    pcm = decode(thd_tools, output)
    ref = decode(thd_tools, src)
    for channel in range(channels):
        if channel < 4:
            assert pcm.channel(channel) == ref.channel(channel)
        else:
            assert pcm.peak(channel)[1] / ref.peak(channel)[1] == pytest.approx(
                10 ** (-3 / 20), abs=0.002
            )
