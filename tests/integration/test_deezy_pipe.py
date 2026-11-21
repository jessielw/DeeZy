"""
DeeZy's --pipe with the real tools: a piped encode must match the temp-WAV
encode, and a pipe job must fail, without hanging, when either side does.

Most encodes match byte for byte. Two match in timing and level only, so an
impulse checks them: resampling, where the pipe carries FFmpeg's result at 24
bits and the WAV at 32, and a positive delay while measuring loudness, where
DEE encodes the stream differently from the file (seen on noise; both
deterministic, aligned alike, and equal in SNR against the source).

The planner and runner run in-process with the shipped default config, so the
tests use DEEZY_DEE_LICENSE rather than wherever DeeZy would find a license.
"""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
import math
import os
from pathlib import Path
import sys
import time

import pytest
import tomlkit

from deezy.audio_processors.pipe import process_pipe_job
import deezy.cli as cli
from deezy.cli.payload_factory import PayloadBuilder
from deezy.cli.utils import apply_config_defaults_to_args, apply_default_bitrate
from deezy.config.defaults import CONF_DEFAULT
from deezy.config.manager import ConfigManager
from deezy.exceptions import PipeError
from deezy.pipeline import run
from deezy.pipeline.encode import pipe_name
from deezy.pipeline.plan import PipeStep, PlanContext, plan_job
from deezy.pipeline.transport import NamedPipe
from deezy.track_info.mediainfo import MediainfoParser

from .harness import decode, impulse_wav, md5, noise_wav, xcorr

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="DeeZy pipes into DEE only on Windows"
)

BUILDERS = {
    "dd": PayloadBuilder.build_dd_payload,
    "ddp": PayloadBuilder.build_ddp_payload,
    "ddp-bluray": PayloadBuilder.build_ddp_payload,
}

# (id, arguments after 'encode', source channels): byte-identical
CASES = [
    ("dd_51", ["dd"], 6),
    ("dd_stereo_from_51", ["dd", "--channels", "2"], 6),
    ("dd_dpl2", ["dd", "--channels", "2", "--stereo-down-mix", "dpl2"], 6),
    ("dd_upmix_50", ["dd", "--channels", "6", "--upmix-50-to-51"], 5),
    ("ddp_mono_from_stereo", ["ddp", "--channels", "1"], 2),
    ("ddp_auto_71", ["ddp"], 8),
    ("ddp_auto_3ch", ["ddp"], 3),
    ("ddp_bluray_71", ["ddp-bluray"], 8),
    ("ddp_secondary_51", ["ddp", "--bluray-secondary"], 6),
    ("ddp_dialnorm", ["ddp", "--custom-dialnorm", "-27"], 6),
    ("ddp_delay_dialnorm", ["ddp", "--delay=100ms", "--custom-dialnorm", "-27"], 6),
    ("ddp_delay_negative", ["ddp", "--delay=-100ms"], 6),
]

# (id, arguments after 'encode', source channels, source rate): same timing
ALIGNED_CASES = [
    ("ddp_delay", ["ddp", "--delay=100ms"], 6, 48000),
    ("ddp_441", ["ddp"], 6, 44100),
    ("dd_441_stereo", ["dd", "--channels", "2"], 6, 44100),
]


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


def noise_source(work: Path, channels: int) -> Path:
    path = work / f"pipe_noise_{channels}ch.wav"
    return path if path.exists() else noise_wav(path, channels, seconds=3.0)


def impulse_source(work: Path, channels: int, rate: int) -> Path:
    """One impulse in every channel, one second in."""
    path = work / f"pipe_impulse_{channels}ch_{rate}.wav"
    if path.exists():
        return path
    return impulse_wav(path, channels, at=rate, seconds=3.0, rate=rate)


def plan_for(tools, parser, config, args, src: Path, out: Path, mode: str):
    ns = parser.parse_args(
        ["--no-progress-bars", "encode", *args, "--pipe", mode, "--overwrite"]
        + ["--output", str(out), str(src)]
    )
    apply_default_bitrate(ns, config)
    apply_config_defaults_to_args(ns, config)
    payload = BUILDERS[ns.format_command](
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
    return plan_job(payload, namer.get_audio_track_info(), ctx), payload


def encode(tools, parser, config, args, src, out, mode) -> Path:
    plan, payload = plan_for(tools, parser, config, args, src, out, mode)
    piped = any(isinstance(step, PipeStep) for step in plan.steps)
    assert piped is (mode == "always")
    return run.run_plan(plan, payload)


def both_ways(tools, work, parser, config, args, src: Path) -> dict[str, Path]:
    """The encode of ``src`` through the temp WAV and through the pipe."""
    run.init_phase_limits(max_parallel=1)
    tag = "_".join(args).replace("-", "").replace("=", "") + "_" + src.stem
    suffix = ".ac3" if args[0] == "dd" else ".ec3"
    return {
        mode: encode(
            tools,
            parser,
            config,
            args,
            src,
            work / "pipe_out" / f"{tag}_{mode}{suffix}",
            mode,
        )
        for mode in ("never", "always")
    }


@pytest.mark.parametrize(
    ("args", "channels"), [pytest.param(a, c, id=i) for i, a, c in CASES]
)
def test_piped_encode_matches_the_wav_encode(
    tools, work, parser, config, args, channels
):
    outs = both_ways(tools, work, parser, config, args, noise_source(work, channels))
    assert md5(outs["always"]) == md5(outs["never"])


@pytest.mark.parametrize(
    ("args", "channels", "rate"),
    [pytest.param(a, c, r, id=i) for i, a, c, r in ALIGNED_CASES],
)
def test_piped_encode_lines_up_with_the_wav_encode(
    tools, work, parser, config, args, channels, rate
):
    src = impulse_source(work, channels, rate)
    outs = both_ways(tools, work, parser, config, args, src)
    wav, piped = decode(tools, outs["never"]), decode(tools, outs["always"])
    assert piped.frames == wav.frames
    # the LFE's low-pass smears the impulse too much to time it
    lfe = 3 if wav.channels >= 6 else None
    for c in range(wav.channels):
        if c == lfe:
            continue
        lag, _ = xcorr(wav, c, piped, c, max_lag=64, window=2048)
        assert lag == 0, f"channel {c}"
        # lossy coding of a transient varies, so compare its energy, not its peak
        at = wav.peak(c)[0]
        energy = [
            sum(v * v for v in pcm.floats(c, at - 1024, at + 1024))
            for pcm in (wav, piped)
        ]
        assert abs(10 * math.log10(energy[1] / energy[0])) < 1.0, f"channel {c}"


def test_parallel_pipes_match_the_wav_encodes(tools, work, parser, config):
    sources = [noise_source(work, 6), noise_source(work, 2)]
    run.init_phase_limits(max_parallel=2)

    def both(mode: str) -> list[str]:
        def one(src: Path) -> str:
            out = work / "pipe_par" / f"{src.stem}_{mode}.ec3"
            return md5(encode(tools, parser, config, ["ddp"], src, out, mode))

        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(one, sources))

    assert both("always") == both("never")


# --- failures, with the real DEE on the other end of the pipe


def dee_cmd(tools, work: Path, name: str, data_rate: str = "448") -> list[str]:
    named = NamedPipe(name, 6)
    return [
        str(tools.tool("dee_ddp_encoder")), "--loglevel", "info", "--progress", "1",
        *map(str, tools.license_args()), "--overwrite", "1", "--temp-dir", str(work),
        "--input-format", named.dee_input_format, "-i", named.dee_input,
        "-o", str(work / f"{name}.ec3"), "--data-rate", data_rate,
        "--loudness-management", "skip:dialnorm=-27", "-c", "5.1", "-e", "ddp",
    ]  # fmt: skip


def unique(tag: str) -> str:
    return f"deezy-test-{os.getpid()}-{tag}"


def test_dee_refusing_its_options_reports_dee(tools, work):
    name = unique("badrate")
    ffmpeg = [tools.ffmpeg, "-v", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=5.1"]
    ffmpeg += ["-t", "2", "-c", "pcm_s24le", "-f", "s24le", NamedPipe(name, 6).path]
    start = time.monotonic()
    with pytest.raises(ValueError, match="DEE"):
        process_pipe_job(dee_cmd(tools, work, name, data_rate="7"), ffmpeg, name)
    assert time.monotonic() - start < 60


def test_ffmpeg_failing_to_start_ends_dee(tools, work):
    name = unique("noinput")
    ffmpeg = [tools.ffmpeg, "-v", "-i", str(work / "missing.wav")]
    ffmpeg += ["-c", "pcm_s24le", "-f", "s24le", NamedPipe(name, 6).path]
    start = time.monotonic()
    with pytest.raises(PipeError, match="FFMPEG error"):
        process_pipe_job(dee_cmd(tools, work, name), ffmpeg, name)
    assert time.monotonic() - start < 60


def test_writer_dying_partway_fails_the_job(tools, work):
    # DEE finishes a short stream cleanly and exits 0; the job must still fail
    name = unique("short")
    writer = (
        "import sys; f = open(sys.argv[1], 'wb'); "
        "f.write(bytes(48000 * 6 * 3)); f.close(); sys.exit(1)"
    )
    with pytest.raises(PipeError, match="exit code 1"):
        process_pipe_job(
            dee_cmd(tools, work, name),
            [sys.executable, "-c", writer, NamedPipe(name, 6).path, "-v"],
            name,
        )
