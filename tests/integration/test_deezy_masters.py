"""
DeeZy's Atmos formats from a DAMF master, with the real tools.

DEE reads the master as it is. A synthetic master (an impulse in every
element) shows that DDP Atmos, and DD and DD+ rendered from a master, land on
the master's own sample, delay or not. The sample's DAMF must give the same
bytes as the TrueHD Atmos stream it was decoded from, since DeeZy decodes that
stream to the same DAMF.

The planner and runner run in-process with the shipped default config, so the
tests use DEEZY_DEE_LICENSE rather than wherever DeeZy would find a license.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
import tomlkit

import deezy.cli as cli
from deezy.cli.payload_factory import PayloadBuilder
from deezy.cli.utils import apply_config_defaults_to_args, apply_default_bitrate
from deezy.config.defaults import CONF_DEFAULT
from deezy.config.manager import ConfigManager
from deezy.exceptions import InvalidAtmosInputError
from deezy.pipeline import run
from deezy.pipeline.plan import PlanContext, plan_job, plan_measure
from deezy.track_info.mediainfo import MediainfoParser

from .harness import SR, decode, md5, mediainfo, synthetic_damf

# the impulse, one second in
AT = SR

BUILDERS = {
    "ddp-atmos": PayloadBuilder.build_atmos_payload,
    "ac4-ims": PayloadBuilder.build_ac4_payload,
    "ddp": PayloadBuilder.build_ddp_payload,
    "dd": PayloadBuilder.build_dd_payload,
    "aac": PayloadBuilder.build_aac_payload,
    "measure": PayloadBuilder.build_measure_payload,
}
SUFFIX = {
    "ddp-atmos": ".ec3",
    "ac4-ims": ".ac4",
    "ddp": ".ec3",
    "dd": ".ac3",
    "aac": ".aac",
}


@pytest.fixture(scope="module")
def parser():
    main = cli.create_main_parser()
    sub = main.add_subparsers(dest="sub_command")
    groups = cli.create_common_argument_groups()
    cli.create_encode_parsers(sub, groups)
    cli.create_other_parsers(sub, groups)
    return main


@pytest.fixture
def config() -> Iterator[ConfigManager]:
    ConfigManager.reset_instance()
    manager = ConfigManager()
    manager.config = tomlkit.parse(CONF_DEFAULT).unwrap()
    yield manager
    ConfigManager.reset_instance()


@pytest.fixture(scope="module")
def impulse_master(work) -> Path:
    return synthetic_damf(work / "impulse_master", seconds=3.0, impulse_at=AT)


@pytest.fixture(scope="module")
def noise_master(work) -> Path:
    return synthetic_damf(work / "noise_master", seconds=2.0)


def job(tools, work, parser, config, fmt, args, src: Path):
    """The plan and payload for ``fmt``, written under the work folder."""
    measuring = fmt == "measure"
    tag = f"{src.parent.name}_{fmt}_" + ("_".join(args).replace("-", "") or "default")
    out = work / "masters_out" / f"{tag}{SUFFIX.get(fmt, '.json')}"
    head = [fmt] if measuring else ["encode", fmt]
    ns = parser.parse_args(
        ["--no-progress-bars", *head, *args, "--overwrite"]
        + ([] if measuring else ["--output", str(out)])
        + [str(src)]
    )
    if not measuring:
        apply_default_bitrate(ns, config)
    apply_config_defaults_to_args(ns, config)
    truehdd = Path(tools.truehdd) if tools.truehdd else None
    payload = BUILDERS[fmt](ns, src, Path(tools.ffmpeg), truehdd, tools.dee_dir)
    namer = MediainfoParser(src, payload.track_index)
    temp = run.temp_dir_path(src, work / "masters_temp", track_label=tag)
    ctx = PlanContext(namer=namer, temp_dir=temp, license=tools.license, config=config)
    info = namer.get_audio_track_info()
    plan = (plan_measure if measuring else plan_job)(payload, info, ctx)
    run.init_phase_limits(max_parallel=1)
    return plan, payload


def encode(tools, work, parser, config, fmt, args, src: Path) -> Path:
    plan, payload = job(tools, work, parser, config, fmt, args, src)
    assert [type(step).__name__ for step in plan.steps] == ["DeeStep"]
    return run.run_plan(plan, payload)


@pytest.mark.parametrize(
    ("args", "delay"),
    [([], 0), (["--delay=-20ms"], -960), (["--delay=100ms"], 4800)],
    ids=["no_delay", "delay_neg", "delay_pos"],
)
def test_ddp_atmos_from_a_master_lands_on_its_sample(
    tools, work, parser, config, impulse_master, args, delay
):
    out_path = encode(tools, work, parser, config, "ddp-atmos", args, impulse_master)
    assert "Atmos" in mediainfo(out_path)["commercial_name"]
    out = decode(tools, out_path)
    frames = [out.peak(c)[0] for c in range(out.channels) if out.peak(c)[1] > 0.02]
    assert frames, "the impulse is missing from every channel"
    # lossy coding may move a transient's peak by a sample
    for frame in frames:
        assert abs(frame - (AT + delay)) <= 1


def test_ac4_ims_encodes_a_master(tools, work, parser, config, noise_master):
    out = encode(tools, work, parser, config, "ac4-ims", [], noise_master)
    track = mediainfo(out)
    assert track["format"] == "AC-4"
    assert int(track["channel_s"]) == 2


def test_a_master_is_measured_as_atmos(tools, work, parser, config, noise_master):
    plan, payload = job(tools, work, parser, config, "measure", [], noise_master)
    (track,) = run.run_measure(plan, payload)["loudness_manifest"]["tracks"]
    assert set(track["atmos_loudness"]) == {"binaural", "multichannel"}


def test_a_channel_based_format_refuses_a_master(
    tools, work, parser, config, noise_master
):
    with pytest.raises(InvalidAtmosInputError, match="aac can't encode an Atmos"):
        job(tools, work, parser, config, "aac", [], noise_master)


# (id, format, arguments, channels out, delay in samples)
RENDERS = [
    ("ddp_51", "ddp", [], 6, 0),
    ("ddp_51_delay_neg", "ddp", ["--delay=-20ms"], 6, -960),
    ("ddp_51_delay_pos", "ddp", ["--delay=100ms"], 6, 4800),
    ("ddp_20", "ddp", ["--channels", "2"], 2, 0),
    ("ddp_20_delay_neg", "ddp", ["--channels", "2", "--delay=-20ms"], 2, -960),
    ("ddp_10", "ddp", ["--channels", "1"], 1, 0),
    ("dd_51", "dd", [], 6, 0),
    ("dd_20_delay_pos", "dd", ["--channels", "2", "--delay=100ms"], 2, 4800),
    ("dd_10", "dd", ["--channels", "1"], 1, 0),
    ("secondary_20", "ddp", ["--bluray-secondary", "--channels", "2"], 2, 0),
]


@pytest.mark.parametrize(
    ("fmt", "args", "channels", "delay"),
    [pytest.param(f, a, c, d, id=i) for i, f, a, c, d in RENDERS],
)
def test_dd_and_ddp_render_a_master_on_its_sample(
    tools, work, parser, config, impulse_master, fmt, args, channels, delay
):
    """DEE adds 256 samples to a 5.1 render and 288 to a 2.0 or 1.0 one."""
    out_path = encode(tools, work, parser, config, fmt, args, impulse_master)
    assert int(mediainfo(out_path)["channel_s"]) == channels
    out = decode(tools, out_path)
    frames = [out.peak(c)[0] for c in range(out.channels) if out.peak(c)[1] > 0.02]
    assert frames, "the impulse is missing from every channel"
    # lossy coding may move a transient's peak by a sample (DD+ mono peaks
    # one late, as it does from PCM)
    for frame in frames:
        assert abs(frame - (AT + delay)) <= 1


@pytest.mark.parametrize("fmt", ["dd", "ddp"])
def test_a_render_encodes_as_dee_does_by_hand(
    tools, work, parser, config, noise_master, fmt
):
    """
    DeeZy's DRC, downmix, phase-shift and 3 dB options at their defaults change
    no byte of a render (DEE ignores the last two for a master).
    """
    out = encode(tools, work, parser, config, fmt, [], noise_master)
    by_hand = work / "masters_out" / f"by_hand{SUFFIX[fmt]}"
    rate = "448" if fmt == "dd" else "192"
    result = tools.dee(
        "dee_ddp_encoder", "--input-format", "atmos_mezz", "-i", noise_master,
        "-o", by_hand, "--temp-dir", by_hand.parent, "--start", "0.005333",
        "--data-rate", rate, "--loudness-management", "measure_only",
        "-c", "5.1", "-e", fmt,
    )  # fmt: skip
    assert result.ok, result.error()
    assert md5(out) == md5(by_hand)


def test_the_samples_damf_encodes_as_its_truehd_stream_does(
    tools, work, parser, config, damf
):
    """ac4-ims, because it is fast: both paths give DEE the same master."""
    from_damf = encode(tools, work, parser, config, "ac4-ims", [], damf)
    plan, payload = job(tools, work, parser, config, "ac4-ims", [], tools.atmos_sample)
    assert [type(step).__name__ for step in plan.steps] == ["TruehddStep", "DeeStep"]
    from_truehd = run.run_plan(plan, payload)
    assert md5(from_damf) == md5(from_truehd)
