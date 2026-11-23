"""
DeeZy's thd-atmos with the real tools: TrueHD Atmos from a master or a stream.

A short synthetic master encodes to the same TrueHD Atmos bytes every run, so
its encodes are compared by hash with DEE run directly. Longer masters and the
sample are not byte-deterministic, so their tests check the decoded audio and
what truehdd reports. An impulse master shows the encode lands on the master's
own sample.

The planner and runner run in-process with the shipped default config, so the
tests use DEEZY_DEE_LICENSE rather than wherever DeeZy would find a license.
"""

from collections.abc import Iterator
from pathlib import Path
import re

import pytest
import tomlkit

import deezy.cli as cli
from deezy.cli.payload_factory import PayloadBuilder
from deezy.cli.utils import apply_config_defaults_to_args
from deezy.config.defaults import CONF_DEFAULT
from deezy.config.manager import ConfigManager
from deezy.pipeline import run
from deezy.pipeline.plan import PlanContext, plan_job
from deezy.track_info.mediainfo import MediainfoParser

from .harness import (
    SR,
    decode,
    make_damf,
    md5,
    run as run_cmd,
    synthetic_damf,
    warp_mode,
)

# the impulse, one second in
AT = SR
PRESENTATIONS = ("atmos", "8ch", "6ch", "2ch")


@pytest.fixture(scope="module")
def truehdd(tools) -> str:
    if not tools.truehdd:
        pytest.skip("set DEEZY_TRUEHDD to decode TrueHD Atmos")
    return tools.truehdd


@pytest.fixture(scope="module")
def parser():
    main = cli.create_main_parser()
    sub = main.add_subparsers(dest="sub_command")
    cli.create_encode_parsers(sub, cli.create_common_argument_groups())
    return main


@pytest.fixture
def config() -> Iterator[ConfigManager]:
    ConfigManager.reset_instance()
    manager = ConfigManager()
    manager.config = tomlkit.parse(CONF_DEFAULT).unwrap()
    yield manager
    ConfigManager.reset_instance()


@pytest.fixture(scope="module")
def noise_master(work) -> Path:
    # 2 s: a 3 s master already encodes to different bytes from run to run
    return synthetic_damf(work / "thd_atmos_noise", seconds=2.0)


@pytest.fixture(scope="module")
def impulse_master(work) -> Path:
    return synthetic_damf(work / "thd_atmos_impulse", seconds=3.0, impulse_at=AT)


def encode(tools, work, parser, config, args, src: Path, steps=("DeeStep",)) -> Path:
    tag = f"{src.parent.name}_" + ("_".join(args).replace("-", "") or "default")
    out = work / "thd_atmos_out" / f"{tag}.thd"
    ns = parser.parse_args(
        ["--no-progress-bars", "encode", "thd-atmos", *args, "--overwrite"]
        + ["--output", str(out), str(src)]
    )
    apply_config_defaults_to_args(ns, config)
    truehdd = Path(tools.truehdd) if tools.truehdd else None
    payload = PayloadBuilder.build_thd_atmos_payload(
        ns, src, Path(tools.ffmpeg), truehdd, tools.dee_dir
    )
    namer = MediainfoParser(src, payload.track_index)
    temp = run.temp_dir_path(src, work / "thd_atmos_temp", track_label=tag)
    ctx = PlanContext(namer=namer, temp_dir=temp, license=tools.license, config=config)
    plan = plan_job(payload, namer.get_audio_track_info(), ctx)
    assert tuple(type(step).__name__ for step in plan.steps) == steps
    run.init_phase_limits(max_parallel=1)
    return run.run_plan(plan, payload)


def direct(tools, work, src: Path, name: str, *presentations: str) -> Path:
    """dee_dthd_encoder run by hand: the master into the first presentation."""
    out_dir = work / "thd_atmos_direct" / name
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "o.thd"
    first, *rest = presentations
    args = ["--presentation", first, "--input-format", "atmos_mezz", "-i", src]
    for presentation in rest:
        args += ["--presentation", presentation]
    result = tools.dee(
        "dee_dthd_encoder", *args, "--start", "0", "-o", out, "--temp-dir", out_dir
    )
    assert result.ok, result.error()
    return out


def info(truehdd: str, thd: Path) -> str:
    result = run_cmd([truehdd, "--loglevel", "warn", "info", thd])
    assert result.ok, result.out
    return result.out


def numbers(label: str, text: str) -> list[int]:
    return [int(n) for n in re.findall(rf"{label}\s+(-?\d+)", text)]


def test_a_master_encodes_as_dee_does_with_the_d7_settings(
    tools, work, parser, config, noise_master, truehdd
):
    """DeeZy's DRC, timecode and --start arguments change no byte at defaults."""
    out = encode(tools, work, parser, config, [], noise_master)
    plain = direct(
        tools,
        work,
        noise_master,
        "d7",
        "atmos:number_of_elements=16:legacy_authoring=0",
    )
    assert md5(out) == md5(plain)
    text = info(truehdd, out)
    assert numbers("Number of elements", text) == [16]
    # the 2.0, 5.1 and 7.1 presentations DEE renders from the master
    assert numbers("Number of channels", text) == [2, 6, 8]


def test_the_stream_keeps_its_warp_mode_unless_authored_for_legacy_tools(
    tools, work, parser, config, noise_master, truehdd
):
    flags = {}
    for args in ([], ["--legacy-authoring"]):
        out = encode(tools, work, parser, config, args, noise_master)
        decoded = make_damf(tools, out, out.parent / f"{out.stem}_dec")
        flags[bool(args)] = warp_mode(decoded)
    # D6: the master has none, which DEE writes as warping
    assert flags == {False: "warping", True: None}
    legacy = direct(tools, work, noise_master, "legacy", "atmos:number_of_elements=16")
    assert md5(out) == md5(legacy)


def test_drc_reaches_every_presentation(tools, work, parser, config, noise_master):
    """DEE sets each presentation's DRC on its own; DeeZy sets all four."""
    out = encode(tools, work, parser, config, ["--drc", "music_light"], noise_master)
    top = "atmos:drc_profile=music_light:number_of_elements=16:legacy_authoring=0"
    every = [top] + [f"{p}:drc_profile=music_light" for p in PRESENTATIONS[1:]]
    assert md5(out) == md5(direct(tools, work, noise_master, "drc_all", *every))
    assert md5(out) != md5(direct(tools, work, noise_master, "drc_top", top))


def test_a_custom_dialnorm_is_written(
    tools, work, parser, config, noise_master, truehdd
):
    args = ["--custom-dialnorm", "-27"]
    out = encode(tools, work, parser, config, args, noise_master)
    levels = numbers("Dialogue Level", info(truehdd, out))
    # 2.0, 5.1, 7.1, Atmos; DEE writes the 2.0 downmix 6 dB lower, as it does
    # for a measured dialnorm
    assert levels[1:] == [-27, -27, -27]


@pytest.mark.parametrize(
    ("args", "delay"),
    [([], 0), (["--delay=-20ms"], -960), (["--delay=100ms"], 4800)],
    ids=["no_delay", "delay_neg", "delay_pos"],
)
def test_truehd_atmos_lands_on_the_masters_sample(
    tools, work, parser, config, impulse_master, args, delay
):
    out = decode(tools, encode(tools, work, parser, config, args, impulse_master))
    frames = {out.peak(c)[0] for c in range(out.channels) if out.peak(c)[1] > 0.02}
    # lossless: every channel of the 7.1 presentation peaks on the same sample
    assert frames == {AT + delay}


def test_the_atmos_sample_goes_through_truehdd(
    tools, work, parser, config, thd, damf, truehdd
):
    """
    The stream's warp mode reaches the TrueHD Atmos output. One encode of the
    sample takes over a minute, and test_deezy_masters shows the stream and its
    DAMF give DEE the same master, so the DAMF isn't also encoded by hand.
    """
    if warp_mode(damf) is not None:
        pytest.skip(
            "the sample carries a warp mode, so truehdd ignores --thd-warp-mode"
        )
    args = ["--thd-warp-mode", "normal"]
    out = encode(
        tools, work, parser, config, args, thd, steps=("TruehddStep", "DeeStep")
    )
    assert numbers("Number of elements", info(truehdd, out)) == [16]
    decoded = make_damf(tools, out, out.parent / f"{out.stem}_dec")
    assert warp_mode(decoded) == "normal"
