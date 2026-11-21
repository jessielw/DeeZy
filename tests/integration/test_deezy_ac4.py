"""
DeeZy's channel-based ac4 format with the real tools.

There is no AC-4 decoder here, so the encode's timing can't be measured. DeeZy
compensates the offset dee_ac4_encoder writes into its manifest, which these
tests pin for every layout DeeZy hands it. The rest checks that every source
layout encodes to the layout asked for, and that a piped encode matches the
temp-WAV encode byte for byte.

The planner and runner run in-process with the shipped default config, so the
tests use DEEZY_DEE_LICENSE rather than wherever DeeZy would find a license.
"""

from collections.abc import Iterator
import json
from pathlib import Path
import sys

import pytest
import tomlkit

import deezy.cli as cli
from deezy.cli.payload_factory import PayloadBuilder
from deezy.cli.utils import apply_config_defaults_to_args, apply_default_bitrate
from deezy.config.defaults import CONF_DEFAULT
from deezy.config.manager import ConfigManager
from deezy.dee.spec import get_format
from deezy.pipeline import run
from deezy.pipeline.encode import pipe_name
from deezy.pipeline.plan import PipeStep, PlanContext, plan_job
from deezy.track_info.mediainfo import MediainfoParser

from .harness import md5, mediainfo, noise_wav


@pytest.fixture(scope="module")
def ac4_tools(tools):
    if not tools.tool("dee_ac4_encoder").is_file():
        pytest.skip("DEEZY_DEE_DIR lacks dee_ac4_encoder")
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


def noise(work: Path, channels: int) -> Path:
    path = work / f"ac4_noise_{channels}ch.wav"
    return path if path.exists() else noise_wav(path, channels, seconds=3.0)


def encode(tools, work, parser, config, args, src: Path, pipe="never") -> Path:
    tag = "_".join(args).replace("-", "").replace("=", "") or "default"
    out = work / "ac4_out" / f"{src.stem}_{tag}_{pipe}.ac4"
    ns = parser.parse_args(
        ["--no-progress-bars", "encode", "ac4", *args, "--pipe", pipe]
        + ["--overwrite", "--output", str(out), str(src)]
    )
    apply_default_bitrate(ns, config)
    apply_config_defaults_to_args(ns, config)
    payload = PayloadBuilder.build_ac4_channel_payload(
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


# (id, arguments after 'encode ac4', source channels, output channels)
LAYOUTS = [
    ("auto_2", [], 2, 2),
    ("auto_51", [], 6, 6),
    ("auto_71", [], 8, 6),
    ("auto_mono", [], 1, 2),
    ("auto_3ch", [], 3, 2),
    ("auto_7ch", [], 7, 6),
    ("stereo_from_51", ["--channels", "2"], 6, 2),
    ("stereo_from_71", ["--channels", "2"], 8, 2),
    ("target", ["--loudness-target", "-20"], 6, 6),
    ("dpl2_flag", ["--stereo-down-mix", "dpl2"], 6, 6),
    ("delay", ["--delay=-20ms"], 2, 2),
]


@pytest.mark.parametrize(
    ("args", "channels", "out_channels"),
    [pytest.param(a, c, o, id=i) for i, a, c, o in LAYOUTS],
)
def test_ac4_encodes_the_layout_asked_for(
    ac4_tools, work, parser, config, args, channels, out_channels
):
    out = encode(ac4_tools, work, parser, config, args, noise(work, channels))
    track = mediainfo(out)
    assert "AC-4" in str(track.get("format"))
    assert int(track["channel_s"]) == out_channels


@pytest.mark.parametrize(
    ("channels", "layout"),
    [(2, "stereo"), (6, "5.1"), (8, "5.1"), (6, "stereo"), (8, "stereo")],
)
def test_the_manifest_offset_is_the_compensated_delay(
    ac4_tools, work, channels, layout
):
    out = work / f"ac4_manifest_{channels}_{layout}.ac4"
    manifest = out.with_suffix(".json")
    result = ac4_tools.dee(
        "dee_ac4_encoder", "--input-format", "wav", "-i", noise(work, channels),
        "-o", out, "--output-manifest", manifest, "--temp-dir", work,
        "--start", "0", "--loudness-management", "measure_only", "-c", layout,
    )  # fmt: skip
    assert result.ok, result.error()
    (entry,) = json.loads(manifest.read_text())["output_files"]
    assert -entry["offset"] == get_format("ac4").delay_samples


@pytest.mark.skipif(sys.platform != "win32", reason="DeeZy pipes only on Windows")
@pytest.mark.parametrize(
    ("args", "channels"),
    [
        pytest.param([], 2, id="stereo"),
        pytest.param([], 6, id="51"),
        pytest.param([], 8, id="71"),
        pytest.param([], 1, id="mono"),
        pytest.param(["--channels", "2"], 6, id="stereo_from_51"),
        pytest.param(["--delay=-20ms"], 6, id="delay_neg"),
    ],
)
def test_piped_ac4_matches_the_wav_encode(
    ac4_tools, work, parser, config, args, channels
):
    src = noise(work, channels)
    wav = encode(ac4_tools, work, parser, config, args, src, pipe="never")
    piped = encode(ac4_tools, work, parser, config, args, src, pipe="always")
    assert md5(piped) == md5(wav)
