"""
deezy measure with the real tools.

DEE's integrated loudness is checked against FFmpeg's EBU R128 meter on the
source itself, so a layout DeeZy pads to 5.1 must measure as the source does.
A piped measurement must match the temp-WAV one, and a saved manifest must be
DEE's, naming the source.

The planner and runner run in-process with the shipped default config, so the
tests use DEEZY_DEE_LICENSE rather than wherever DeeZy would find a license.
"""

from collections.abc import Iterator
import json
from pathlib import Path
import re
import subprocess
import sys

import pytest
import tomlkit

import deezy.cli as cli
from deezy.cli.payload_factory import PayloadBuilder
from deezy.cli.utils import apply_config_defaults_to_args
from deezy.config.defaults import CONF_DEFAULT
from deezy.config.manager import ConfigManager
from deezy.exceptions import UnsupportedDeeFeatureError
from deezy.pipeline import run
from deezy.pipeline.encode import pipe_name
from deezy.pipeline.plan import PipeStep, PlanContext, plan_measure
from deezy.track_info.mediainfo import MediainfoParser

from .harness import noise_wav

# DEE's meter and FFmpeg's agree to the printed decimal on these sources
TOLERANCE = 0.3


@pytest.fixture(scope="module")
def measure_tools(tools):
    if not tools.tool("dee_measure_loudness").is_file():
        pytest.skip("DEEZY_DEE_DIR lacks dee_measure_loudness")
    return tools


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


def measure(tools, work, parser, config, args, src: Path, pipe="never") -> dict:
    tag = "_".join(args).replace("-", "") or "default"
    ns = parser.parse_args(
        ["--no-progress-bars", "measure", *args, "--pipe", pipe, "--overwrite"]
        + [str(src)]
    )
    apply_config_defaults_to_args(ns, config)
    truehdd = Path(tools.truehdd) if tools.truehdd else None
    payload = PayloadBuilder.build_measure_payload(
        ns, src, Path(tools.ffmpeg), truehdd, tools.dee_dir
    )
    namer = MediainfoParser(src, payload.track_index)
    temp = run.temp_dir_path(src, work / "measure_temp", track_label=f"{tag}{pipe}")
    ctx = PlanContext(
        namer=namer,
        temp_dir=temp,
        license=tools.license,
        config=config,
        pipe_name=pipe_name(temp),
    )
    plan = plan_measure(payload, namer.get_audio_track_info(), ctx)
    piped = any(isinstance(step, PipeStep) for step in plan.steps)
    assert piped is (pipe == "always")
    run.init_phase_limits(max_parallel=1)
    return run.run_measure(plan, payload)


def results(manifest: dict) -> dict:
    (track,) = manifest["loudness_manifest"]["tracks"]
    return track.get("channel_based_loudness") or track["atmos_loudness"]


def only(manifest: dict) -> dict:
    (found,) = results(manifest).values()
    return found


def r128(tools, path: Path) -> float:
    """FFmpeg's EBU R128 integrated loudness of the file."""
    result = subprocess.run(  # noqa: S603
        [tools.ffmpeg, "-hide_banner", "-nostats", "-i", str(path)]
        + ["-af", "ebur128", "-f", "null", "-"],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(re.findall(r"I:\s+(-?\d+(?:\.\d+)?) LUFS", result.stderr)[-1])


def noise(work: Path, channels: int) -> Path:
    path = work / f"measure_noise_{channels}ch.wav"
    return path if path.exists() else noise_wav(path, channels, seconds=3.0)


# each layout's channels, every one carrying the same pink noise
LAYOUTS = {
    "3.0": "FL FR FC",
    "2.1": "FL FR LFE",
    "quad": "FL FR BL BR",
    "5.0(side)": "FL FR FC SL SR",
    "4.1": "FL FR FC LFE BC",
}


def layout_wav(tools, work: Path, layout: str, rate: int = 48000) -> Path:
    """Pink noise in ``layout``, with the WAV channel mask set to it."""
    name = re.sub(r"[^0-9a-z]", "", layout)
    path = work / f"measure_{name}_{rate}.wav"
    if not path.exists():
        pan = "|".join(f"{channel}=c0" for channel in LAYOUTS[layout].split())
        subprocess.run(  # noqa: S603
            [tools.ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i"]
            + ["anoisesrc=d=3:c=pink:a=0.2:seed=1", "-af"]
            + [f"aformat=channel_layouts=mono,pan={layout}|{pan}", "-ar", str(rate)]
            + ["-c:a", "pcm_s24le", str(path)],
            check=True,
        )
    return path


@pytest.mark.parametrize("channels", [1, 2, 6])
def test_dee_measures_what_r128_does(measure_tools, work, parser, config, channels):
    src = noise(work, channels)
    found = only(measure(measure_tools, work, parser, config, [], src))
    assert abs(found["integrated_loudness"] - r128(measure_tools, src)) < TOLERANCE


@pytest.mark.parametrize("layout", list(LAYOUTS))
def test_a_layout_padded_to_51_measures_as_the_source(
    measure_tools, work, parser, config, layout
):
    src = layout_wav(measure_tools, work, layout)
    measured = measure(measure_tools, work, parser, config, [], src)
    assert list(results(measured)) == ["multichannel_5_1"]
    found = only(measured)["integrated_loudness"]
    assert abs(found - r128(measure_tools, src)) < TOLERANCE


def test_a_441_source_is_resampled_first(measure_tools, work, parser, config):
    src = layout_wav(measure_tools, work, "5.0(side)", rate=44100)
    found = only(measure(measure_tools, work, parser, config, [], src))
    assert abs(found["integrated_loudness"] - r128(measure_tools, src)) < TOLERANCE


def test_71_is_refused(measure_tools, work, parser, config):
    with pytest.raises(UnsupportedDeeFeatureError, match="not 8 channels"):
        measure(measure_tools, work, parser, config, [], noise(work, 8))


def test_a_regulation_preset_leaves_speech_unmeasured(
    measure_tools, work, parser, config
):
    src = noise(work, 2)
    found = only(
        measure(
            measure_tools, work, parser, config, ["--loudness-preset", "ebu_r128"], src
        )
    )
    assert found["integrated_speech_percentage"] == -1.0
    assert found["integrated_loudness_gating"] == "level"


def test_output_dir_saves_dee_manifest_under_the_input_name(
    measure_tools, work, parser, config
):
    src = noise(work, 6)
    out_dir = work / "measure_saved"
    got = measure(
        measure_tools, work, parser, config, ["--output-dir", str(out_dir)], src
    )
    saved = json.loads((out_dir / f"{src.stem}.loudness.json").read_text())
    assert saved == got
    assert saved["loudness_manifest"]["tracks"][0]["id"] == str(src)


@pytest.mark.skipif(sys.platform != "win32", reason="DeeZy pipes only on Windows")
@pytest.mark.parametrize("channels", [1, 2, 6])
def test_a_piped_measurement_matches_the_wav_one(
    measure_tools, work, parser, config, channels
):
    src = noise(work, channels)
    wav = measure(measure_tools, work, parser, config, [], src, pipe="never")
    piped = measure(measure_tools, work, parser, config, [], src, pipe="always")
    assert results(piped) == results(wav)


@pytest.mark.skipif(sys.platform != "win32", reason="DeeZy pipes only on Windows")
def test_a_piped_resampled_padded_measurement_matches_the_wav_one(
    measure_tools, work, parser, config
):
    src = layout_wav(measure_tools, work, "5.0(side)", rate=44100)
    wav = only(measure(measure_tools, work, parser, config, [], src, pipe="never"))
    piped = only(measure(measure_tools, work, parser, config, [], src, pipe="always"))
    # the resampled pipe carries s24 and the WAV s32, so they differ in the last
    # bits (seen: 0.00002 LU)
    for key in ("integrated_loudness", "integrated_loudness_range"):
        assert abs(piped[key] - wav[key]) < 0.01, key
    for key in ("true_peaks", "sample_peaks"):
        assert all(abs(a - b) < 0.01 for a, b in zip(piped[key], wav[key], strict=True))


def test_the_atmos_sample_measures_both_renders(measure_tools, work, parser, config):
    if not measure_tools.atmos_sample or not measure_tools.truehdd:
        pytest.skip("needs DEEZY_ATMOS_SAMPLE and truehdd")
    measured = results(
        measure(measure_tools, work, parser, config, [], measure_tools.atmos_sample)
    )
    assert sorted(measured) == ["binaural", "multichannel"]
    for render in measured.values():
        # the sample has dialogue, so DEE gates on speech
        assert render["integrated_loudness_gating"] == "speech"
        assert abs(render["integrated_loudness"] - -20.1) < 0.1
        assert 40 < render["integrated_speech_percentage"] < 55
