"""
DeeZy finding and running the real dee_shim, and reading its failures.

With no options of its own the shim encodes what DEE does, byte for byte, so
DeeZy runs every DD+ Atmos and TrueHD encode through it when it has it.

The planner and runner run in-process with the shipped default config, so the
tests use DEEZY_DEE_LICENSE rather than wherever DeeZy would find a license.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
import tomlkit

from deezy.audio_processors.dee import process_dee_job
import deezy.cli as cli
from deezy.cli.payload_factory import PayloadBuilder
from deezy.cli.utils import apply_config_defaults_to_args, apply_default_bitrate
from deezy.config.defaults import CONF_DEFAULT
from deezy.config.manager import ConfigManager
from deezy.dee.shim import DeeShim, is_shim_command, resolve_shim
from deezy.pipeline import run
from deezy.pipeline.plan import DeeStep, PlanContext, plan_job
from deezy.track_info.mediainfo import MediainfoParser

from .harness import md5, noise_wav, synthetic_damf


@pytest.fixture(scope="module")
def dee_shim(shim) -> DeeShim:
    found = resolve_shim(Path(), None, shim.shim)
    assert found is not None
    return found


@pytest.fixture(scope="module")
def wav(work) -> Path:
    return noise_wav(work / "shim_noise71.wav", 8, seconds=1.0)


def ddp_argv(shim, work, wav, out: str) -> list[str]:
    return [
        str(shim.tool("dee_ddp_encoder")), *map(str, shim.license_args()),
        "--overwrite", "1", "--loglevel", "info", "--progress", "1",
        "--input-format", "wav", "-i", str(wav), "-o", str(work / out),
        "--temp-dir", str(work), "--loudness-management", "measure_only",
    ]  # fmt: skip


def shim_run(argv, *shim_args, shim: DeeShim):
    return process_dee_job(list(shim.argv(argv, *shim_args)), no_progress_bars=True)


def test_deezy_reads_the_shims_version(dee_shim):
    assert dee_shim.version.startswith("0.2.1")


def test_a_run_through_the_shim(shim, work, wav, dee_shim):
    argv = ddp_argv(shim, work, wav, "shim_ok.ec3")
    assert shim_run(argv, "--layout", "7.1/eac3", shim=dee_shim)
    assert (work / "shim_ok.ec3").stat().st_size > 0


def test_a_refused_job_says_why(shim, work, wav, dee_shim):
    argv = ddp_argv(shim, work, wav, "shim_rate.ec3")
    with pytest.raises(ValueError, match="dee_shim refused the job: --bitrate 123"):
        shim_run(argv, "--layout", "7.1/eac3", "--bitrate", "123", shim=dee_shim)


def test_a_dee_build_without_a_profile(shim, work, wav, dee_shim):
    argv = ddp_argv(shim, work, wav, "shim_build.ec3")
    argv[0] = str(shim.ffmpeg)
    with pytest.raises(ValueError, match="doesn't support this DEE build"):
        process_dee_job(
            [str(dee_shim.path), "ddp_encoder", "--layout", "7.1/eac3", "--binary",
             str(shim.ffmpeg), "--", *argv[1:]],
            no_progress_bars=True,
        )  # fmt: skip


def test_deees_own_failure_passes_through(shim, work, dee_shim):
    argv = ddp_argv(shim, work, work / "missing.wav", "shim_missing.ec3")
    with pytest.raises(ValueError, match="DEE execution failed:"):
        shim_run(argv, "--layout", "7.1/eac3", shim=dee_shim)


def test_the_shims_environment_is_kept_out(shim, work, wav, dee_shim, monkeypatch):
    """RUST_LOG=debug would put dee_shim's debug lines into DEE's output."""
    import deezy.audio_processors.dee as runner

    monkeypatch.setenv("RUST_LOG", "debug")
    lines: list[str] = []
    monkeypatch.setattr(runner.logger, "debug", lambda line, *_: lines.append(line))
    argv = ddp_argv(shim, work, wav, "shim_env.ec3")
    assert shim_run(argv, "--layout", "7.1/eac3", shim=dee_shim)
    assert lines, "DEE's output was not logged"
    assert not any("dee_shim DEBUG" in line for line in lines)


# --- DeeZy's encodes through dee_shim: the same bytes as plain DEE

BUILDERS = {
    "ddp-atmos": PayloadBuilder.build_atmos_payload,
    "thd": PayloadBuilder.build_thd_payload,
    "thd-atmos": PayloadBuilder.build_thd_atmos_payload,
}
SUFFIX = {"ddp-atmos": ".ec3", "thd": ".thd", "thd-atmos": ".thd"}


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


def encode(tools, work, parser, config, fmt, args, src: Path, shim: DeeShim | None):
    """DeeZy's plan for ``fmt``, run with or without dee_shim."""
    tag = f"{src.stem}_{fmt}_{'shim' if shim else 'plain'}_" + "_".join(args)
    out = work / "shim_out" / f"{tag.replace('-', '')}{SUFFIX[fmt]}"
    ns = parser.parse_args(
        ["--no-progress-bars", "encode", fmt, *args, "--overwrite", "--output", str(out), str(src)]
    )  # fmt: skip
    apply_default_bitrate(ns, config)
    apply_config_defaults_to_args(ns, config)
    truehdd = Path(tools.truehdd) if tools.truehdd else None
    payload = BUILDERS[fmt](ns, src, Path(tools.ffmpeg), truehdd, tools.dee_dir)
    payload.dee_shim = shim
    namer = MediainfoParser(src, payload.track_index)
    temp = run.temp_dir_path(src, work / "shim_temp", track_label=tag)
    ctx = PlanContext(namer=namer, temp_dir=temp, license=tools.license, config=config)
    plan = plan_job(payload, namer.get_audio_track_info(), ctx)
    dee_steps = [step for step in plan.steps if isinstance(step, DeeStep)]
    assert len(dee_steps) == 1
    assert is_shim_command(dee_steps[0].argv) == (shim is not None)
    run.init_phase_limits(max_parallel=1)
    return run.run_plan(plan, payload)


@pytest.fixture(scope="module")
def master(work) -> Path:
    # TrueHD Atmos from a 2 s synthetic master is byte-deterministic
    return synthetic_damf(work / "shim_master", seconds=2.0)


@pytest.mark.parametrize(
    ("fmt", "args"),
    [
        ("ddp-atmos", []),
        ("ddp-atmos", ["--delay=-20ms"]),
        ("thd-atmos", []),
        ("thd-atmos", ["--legacy-authoring"]),
    ],
    ids=["ddp_atmos", "ddp_atmos_delay", "thd_atmos", "thd_atmos_legacy"],
)
def test_a_master_through_the_shim_is_byte_identical(
    shim, work, parser, config, dee_shim, master, fmt, args
):
    plain = encode(shim, work, parser, config, fmt, args, master, None)
    shimmed = encode(shim, work, parser, config, fmt, args, master, dee_shim)
    assert md5(shimmed) == md5(plain)


@pytest.mark.parametrize(
    ("channels", "args"),
    [(8, []), (6, ["--delay=100ms"]), (2, ["--drc", "speech"])],
    ids=["thd_71", "thd_51_delay", "thd_20_drc"],
)
def test_thd_through_the_shim_is_byte_identical(
    shim, work, parser, config, dee_shim, channels, args
):
    src = noise_wav(work / f"shim_thd_in{channels}.wav", channels, seconds=2.0)
    plain = encode(shim, work, parser, config, "thd", args, src, None)
    shimmed = encode(shim, work, parser, config, "thd", args, src, dee_shim)
    assert md5(shimmed) == md5(plain)
