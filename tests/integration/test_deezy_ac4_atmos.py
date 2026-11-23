"""
DeeZy's ac4-atmos with the real tools: AC-4 Atmos from a master or a stream.

AC-4 Atmos output is byte-deterministic, so DeeZy's encodes are compared by
hash with dee_ac4ajoc_encoder run by hand. There is no AC-4 decoder here, so
the encode's timing is read from the manifest DEE writes: its offset is the
2048 samples DeeZy compensates, and its duration shows the compensated --start
or --add-silence reached DEE.

The planner and runner run in-process with the shipped default config, so the
tests use DEEZY_DEE_LICENSE rather than wherever DeeZy would find a license.
"""

from collections.abc import Iterator
import json
from pathlib import Path

import pytest
import tomlkit

import deezy.cli as cli
from deezy.cli.payload_factory import PayloadBuilder
from deezy.cli.utils import apply_config_defaults_to_args, apply_default_bitrate
from deezy.config.defaults import CONF_DEFAULT
from deezy.config.manager import ConfigManager
from deezy.dee.spec import get_format
from deezy.pipeline import run
from deezy.pipeline.plan import PlanContext, plan_job
from deezy.track_info.mediainfo import MediainfoParser

from .harness import SR, damf_with_warp, md5, mediainfo, synthetic_damf, warp_mode

TOOL = "dee_ac4ajoc_encoder"
SECONDS = 2
# DeeZy's --start for no delay: the manifest's 2048 samples
START = "0.042667"


@pytest.fixture(scope="module")
def ajoc_tools(tools):
    if not tools.tool(TOOL).is_file():
        pytest.skip(f"DEEZY_DEE_DIR lacks {TOOL}")
    return tools


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
def master(work) -> Path:
    return synthetic_damf(work / "ac4_atmos_noise", seconds=SECONDS)


def encode(
    tools, work, parser, config, args, src: Path, steps=("DeeStep",)
) -> tuple[Path, dict]:
    """DeeZy's encode, and the manifest entry DEE wrote for it."""
    tag = f"{src.parent.name}_" + (
        "_".join(args).replace("-", "").replace("=", "") or "default"
    )
    out = work / "ac4_atmos_out" / f"{tag}.ac4"
    ns = parser.parse_args(
        ["--no-progress-bars", "encode", "ac4-atmos", *args, "--overwrite"]
        + ["--keep-temp", "--output", str(out), str(src)]
    )
    apply_default_bitrate(ns, config)
    apply_config_defaults_to_args(ns, config)
    truehdd = Path(tools.truehdd) if tools.truehdd else None
    payload = PayloadBuilder.build_ac4_atmos_payload(
        ns, src, Path(tools.ffmpeg), truehdd, tools.dee_dir
    )
    namer = MediainfoParser(src, payload.track_index)
    temp = run.temp_dir_path(src, work / "ac4_atmos_temp", track_label=tag)
    ctx = PlanContext(namer=namer, temp_dir=temp, license=tools.license, config=config)
    plan = plan_job(payload, namer.get_audio_track_info(), ctx)
    assert tuple(type(step).__name__ for step in plan.steps) == steps
    run.init_phase_limits(max_parallel=1)
    result = run.run_plan(plan, payload)
    (manifest,) = temp.glob("*.manifest.json")
    (entry,) = json.loads(manifest.read_text())["output_files"]
    return result, entry


def direct(tools, work, src: Path, name: str, *args: str) -> Path:
    """dee_ac4ajoc_encoder run by hand, at DeeZy's default rate and --start."""
    out_dir = work / "ac4_atmos_direct" / name
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "o.ac4"
    result = tools.dee(
        TOOL, "--level", "3", "-i", src, "-o", out,
        "--output-manifest", out_dir / "o.json",
        "--start", START, "--data-rate", "448", *args,
    )  # fmt: skip
    assert result.ok, result.error()
    return out


def test_a_master_encodes_as_dee_does_at_the_defaults(
    ajoc_tools, work, parser, config, master
):
    """DeeZy's DRC, loudness and timecode arguments change no byte."""
    out, entry = encode(ajoc_tools, work, parser, config, [], master)
    assert md5(out) == md5(direct(ajoc_tools, work, master, "defaults"))
    assert "AC-4" in str(mediainfo(out).get("format"))
    assert -entry["offset"] == get_format("ac4-atmos").delay_samples


DEVICES = (
    "--flat-panel-drc",
    "--home-theatre-drc",
    "--portable-headphones-drc",
    "--portable-speakers-drc",
)


@pytest.mark.parametrize("drc", ["music_light", "none"])
def test_drc_reaches_every_device(ajoc_tools, work, parser, config, master, drc):
    """Every device set alike gives DEE's general drc_profile."""
    args = [arg for device in DEVICES for arg in (device, drc)]
    out, _ = encode(ajoc_tools, work, parser, config, args, master)
    by_hand = direct(ajoc_tools, work, master, f"drc_{drc}", "-e", f"drc_profile={drc}")
    assert md5(out) == md5(by_hand)


def test_one_device_drc_changes_the_stream(ajoc_tools, work, parser, config, master):
    out, _ = encode(
        ajoc_tools, work, parser, config, ["--home-theatre-drc", "none"], master
    )
    assert md5(out) != md5(direct(ajoc_tools, work, master, "defaults"))


@pytest.mark.parametrize(
    ("args", "samples"),
    [([], 0), (["--delay=-20ms"], -960), (["--delay=100ms"], 4800)],
    ids=["no_delay", "delay_neg", "delay_pos"],
)
def test_the_manifest_holds_the_compensated_timing(
    ajoc_tools, work, parser, config, master, args, samples
):
    """
    The stream starts 2048 samples early (the offset), so DeeZy trims them, and
    the delay moves the start on from there.
    """
    _, entry = encode(ajoc_tools, work, parser, config, args, master)
    offset = get_format("ac4-atmos").delay_samples
    assert entry["offset"] == -offset
    assert entry["duration"] == SECONDS * SR - offset + samples


@pytest.mark.parametrize("rate", [256, 768])
def test_the_rate_reaches_dee(ajoc_tools, work, parser, config, master, rate):
    out, entry = encode(
        ajoc_tools, work, parser, config, ["--bitrate", str(rate)], master
    )
    nominal = rate * 1000 / 8 * entry["duration"] / SR
    # the preroll and postroll frames add a little
    assert 1.0 < out.stat().st_size / nominal < 1.15


def test_the_atmos_sample_goes_through_truehdd(
    ajoc_tools, work, parser, config, thd, damf
):
    """
    truehdd's warp mode reaches the encode: the stream through DeeZy encodes as
    its DAMF with that warp mode does by hand. Each encode of the sample takes
    about a minute.
    """
    if warp_mode(damf) is not None:
        pytest.skip(
            "the sample carries a warp mode, so truehdd ignores --thd-warp-mode"
        )
    args = ["--thd-warp-mode", "normal"]
    out, _ = encode(
        ajoc_tools, work, parser, config, args, thd, steps=("TruehddStep", "DeeStep")
    )
    by_hand = direct(ajoc_tools, work, damf_with_warp(damf, "normal"), "sample")
    assert md5(out) == md5(by_hand)
