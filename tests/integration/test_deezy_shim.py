"""
DeeZy finding and running the real dee_shim, and reading its failures.

With no options of its own the shim encodes what DEE does, byte for byte, so
DeeZy runs every DD+ Atmos and TrueHD encode through it when it has it. DD+
Atmos also gets `--oamd-as-is on` (the object metadata coded as the master has
it), so it matches plain DEE only with `--no-oamd-as-is`. The shim also gives
what DEE alone can't encode: DD+ 7.1 as E-AC-3, and DD+ Atmos on a 7.1
backbone.

The planner and runner run in-process with the shipped default config, so the
tests use DEEZY_DEE_LICENSE rather than wherever DeeZy would find a license.
"""

from collections.abc import Iterator
from pathlib import Path
import sys

import pytest
import tomlkit

from deezy.audio_processors.dee import process_dee_job
import deezy.cli as cli
from deezy.cli.payload_factory import PayloadBuilder
from deezy.cli.utils import apply_config_defaults_to_args, apply_default_bitrate
from deezy.config.defaults import CONF_DEFAULT
from deezy.config.manager import ConfigManager
from deezy.dee.shim import DeeShim, is_shim_command, resolve_shim
from deezy.exceptions import UnsupportedDeeFeatureError
from deezy.pipeline import run
from deezy.pipeline.encode import pipe_name
from deezy.pipeline.plan import DeeStep, PipeStep, PlanContext, plan_job
from deezy.track_info.mediainfo import MediainfoParser

from .harness import SR, decode, impulse_wav, md5, mediainfo, noise_wav, synthetic_damf


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


# --- DeeZy's encodes through dee_shim: the same bytes as plain DEE (DD+ Atmos
# with the object metadata smoothed as DEE does)

BUILDERS = {
    "ddp": PayloadBuilder.build_ddp_payload,
    "ddp-atmos": PayloadBuilder.build_atmos_payload,
    "thd": PayloadBuilder.build_thd_payload,
    "thd-atmos": PayloadBuilder.build_thd_atmos_payload,
}
SUFFIX = {"ddp": ".ec3", "ddp-atmos": ".ec3", "thd": ".thd", "thd-atmos": ".thd"}


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


def encode(
    tools, work, parser, config, fmt, args, src: Path, shim: DeeShim | None, pipe=False
):
    """DeeZy's plan for ``fmt``, run with or without dee_shim."""
    tag = f"{src.parent.name}_{src.stem}_{fmt}_{'shim' if shim else 'plain'}_"
    tag += "_".join(args)
    tag += "_pipe" if pipe else ""
    out = work / "shim_out" / f"{tag.replace('-', '').replace('=', '')}{SUFFIX[fmt]}"
    transport = ["--pipe", "always" if pipe else "never"] if fmt == "ddp" else []
    ns = parser.parse_args(
        ["--no-progress-bars", "encode", fmt, *args, *transport, "--overwrite",
         "--output", str(out), str(src)]
    )  # fmt: skip
    apply_default_bitrate(ns, config)
    apply_config_defaults_to_args(ns, config)
    truehdd = Path(tools.truehdd) if tools.truehdd else None
    payload = BUILDERS[fmt](ns, src, Path(tools.ffmpeg), truehdd, tools.dee_dir)
    payload.dee_shim = shim
    namer = MediainfoParser(src, payload.track_index)
    temp = run.temp_dir_path(src, work / "shim_temp", track_label=tag)
    ctx = PlanContext(
        namer=namer,
        temp_dir=temp,
        license=tools.license,
        config=config,
        pipe_name=pipe_name(temp) if pipe else None,
    )
    plan = plan_job(payload, namer.get_audio_track_info(), ctx)
    dee_steps = [
        step.dee if isinstance(step, PipeStep) else step
        for step in plan.steps
        if isinstance(step, DeeStep | PipeStep)
    ]
    assert len(dee_steps) == 1
    assert any(isinstance(step, PipeStep) for step in plan.steps) is pipe
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
        ("ddp-atmos", ["--no-oamd-as-is"]),
        ("ddp-atmos", ["--no-oamd-as-is", "--delay=-20ms"]),
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


# --- DD+ Atmos options only the shim has


@pytest.mark.parametrize(
    "args",
    [[], ["--no-oamd-as-is", "--no-surround-90-deg-phase-shift"]],
    ids=["oamd_as_is", "phase90_off"],
)
def test_a_shim_option_changes_the_ddp_atmos_bytes(
    shim, work, parser, config, dee_shim, master, args
):
    # against the shim with neither: DEE's smoothing and its phase shift
    base = encode(
        shim, work, parser, config, "ddp-atmos", ["--no-oamd-as-is"], master, dee_shim
    )
    out = encode(shim, work, parser, config, "ddp-atmos", args, master, dee_shim)
    assert md5(out) != md5(base)


@pytest.mark.parametrize(
    ("args", "rate"),
    [
        (["--atmos-mode", "bluray"], 1280),
        (["--atmos-mode", "standard"], 1152),
        (["--atmos-mode", "standard", "--bitrate", "1000"], 1000),
    ],
    ids=["bluray", "standard", "standard_1000"],
)
def test_ddp_atmos_on_a_7_1_backbone(
    shim, work, parser, config, dee_shim, damf, args, rate
):
    # the sample's master: the synthetic one (15 static noise objects) comes
    # out of a 7.1 backbone without its JOC once DEE trims the start
    out = encode(shim, work, parser, config, "ddp-atmos", args, damf, dee_shim)
    info = mediainfo(out)
    assert "Atmos" in info["commercial_name"]
    assert info["channel_layout"] == "L R C LFE Ls Rs Lb Rb"
    assert int(info["bit_rate"]) == rate * 1000


@pytest.fixture(scope="module")
def impulse_master(work) -> Path:
    # silent but for an impulse one second in, in every element
    return synthetic_damf(work / "shim_impulse_master", seconds=3.0, impulse_at=SR)


@pytest.mark.parametrize(
    "args",
    [[], ["--atmos-mode", "bluray"], ["--atmos-mode", "standard"]],
    ids=["streaming", "bluray", "standard"],
)
def test_ddp_atmos_through_the_shim_lands_on_the_source_sample(
    shim, work, parser, config, dee_shim, impulse_master, args
):
    out = encode(
        shim, work, parser, config, "ddp-atmos", args, impulse_master, dee_shim
    )
    pcm = decode(shim, out)
    assert pcm.channels == (6 if not args else 8)
    frames = [pcm.peak(c)[0] for c in range(pcm.channels) if pcm.peak(c)[1] > 0.02]
    assert frames, "the impulse is missing from every channel"
    # DeeZy trims DEE's 256 samples in every mode; lossy coding may move a
    # transient's peak by a sample
    assert all(abs(frame - SR) <= 1 for frame in frames), frames


@pytest.mark.parametrize(
    ("args", "match"),
    [
        (["--atmos-mode", "bluray"], "7.1 backbone"),
        (["--atmos-mode", "standard"], "7.1 backbone"),
        (["--no-surround-90-deg-phase-shift"], "phase-shift"),
    ],
    ids=["bluray", "standard", "phase90_off"],
)
def test_ddp_atmos_shim_options_are_refused_without_it(
    shim, work, parser, config, master, args, match
):
    with pytest.raises(UnsupportedDeeFeatureError, match=f"{match}.*dee_shim"):
        encode(shim, work, parser, config, "ddp-atmos", args, master, None)


# --- DD+ 7.1 as E-AC-3, which DEE alone can't encode


@pytest.fixture(scope="module")
def impulse71(work) -> Path:
    """One impulse in every channel, one second in."""
    return impulse_wav(work / "shim_impulse71.wav", 8, at=SR, seconds=3.0)


@pytest.mark.parametrize(
    "args",
    [[], ["--channels", "8", "--bitrate", "1792"], ["--delay=-20ms"]],
    ids=["auto", "1792", "delay"],
)
def test_ddp_71_through_the_shim_lands_on_the_source_sample(
    shim, work, parser, config, dee_shim, impulse71, args
):
    out = encode(shim, work, parser, config, "ddp", args, impulse71, dee_shim)
    info = mediainfo(out)
    assert info["format"] == "E-AC-3"
    assert info["channel_layout"] == "L R C LFE Ls Rs Lb Rb"
    rate = 1792 if "1792" in args else 384
    assert int(info["bit_rate"]) == rate * 1000
    pcm = decode(shim, out)
    assert pcm.channels == 8
    # DeeZy trims DEE's 256 samples (and cuts 20 ms for the negative delay)
    expected = SR - (960 if "--delay=-20ms" in args else 0)
    assert pcm.peak(0)[0] == expected
    # the backs come from the dependent substream; a lossy transient may peak a
    # sample off, a substream out of step would be hundreds off. The LFE's
    # low-pass smears the impulse too much to time it.
    peaks = {c: pcm.peak(c)[0] for c in range(8) if c != 3}
    assert all(abs(at - expected) <= 1 for at in peaks.values()), peaks


def test_ddp_71_without_the_shim_is_refused(shim, work, parser, config, impulse71):
    with pytest.raises(UnsupportedDeeFeatureError, match="needs dee_shim"):
        encode(shim, work, parser, config, "ddp", ["--channels", "8"], impulse71, None)


@pytest.mark.skipif(sys.platform != "win32", reason="DeeZy pipes only on Windows")
def test_ddp_71_piped_through_the_shim_matches_the_wav(
    shim, work, parser, config, dee_shim
):
    src = noise_wav(work / "shim_ddp71_noise.wav", 8, seconds=2.0)
    wav = encode(shim, work, parser, config, "ddp", [], src, dee_shim)
    piped = encode(shim, work, parser, config, "ddp", [], src, dee_shim, pipe=True)
    assert md5(piped) == md5(wav)
