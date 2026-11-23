"""deezy measure: the printed summary, where the manifest is saved, and the CLI."""

import json
from pathlib import Path

import pytest

import deezy.cli as cli
from deezy.enums.atmos import WarpMode
from deezy.enums.shared import LoudnessPreset, PipeMode
from deezy.exceptions import OutputExistsError, OutputFileNotFoundError
from deezy.pipeline import measure as measure_mod, run
from deezy.pipeline.measure import summary
from deezy.pipeline.plan import DeeStep, JobPlan
from deezy.pipeline.show import command_lines
from tests.utils.payload_helpers import generate_dummy_core_payload


def result(**overrides) -> dict:
    base = {
        "integrated_loudness": -20.928022,
        "integrated_loudness_gating": "level",
        "integrated_speech_percentage": 0.0,
        "integrated_loudness_range": 0.087204,
        "sample_peaks": [-15.17, -15.5, -16.0],
        "true_peaks": [-15.086477, -15.2, -16.0],
    }
    return {**base, **overrides}


def manifest(track: dict) -> dict:
    return {"loudness_manifest": {"version": "2.0.0", "tracks": [track]}}


def test_a_channel_based_measurement_reads_as_one_block():
    lines = summary(
        manifest({"channel_based_loudness": {"multichannel_5_1": result()}})
    )
    assert lines == [
        "  5.1",
        "    Integrated loudness  -20.9 LKFS (level-gated)",
        "    Speech               0.0 %",
        "    Loudness range       0.1 LU",
        "    True peak            -15.1 dBTP",
        "    Sample peak          -15.2 dBFS",
    ]


def test_a_71_measurement_reads_as_71():
    lines = summary(
        manifest({"channel_based_loudness": {"multichannel_7_1": result()}})
    )
    assert lines[0] == "  7.1"


def test_speech_dee_did_not_measure_says_so():
    track = {
        "channel_based_loudness": {"stereo": result(integrated_speech_percentage=-1.0)}
    }
    lines = summary(manifest(track))
    assert lines[0] == "  2.0"
    assert "    Speech               not measured" in lines


def test_an_atmos_measurement_reads_as_one_block_per_render():
    track = {
        "atmos_loudness": {
            "binaural": result(integrated_loudness_gating="speech"),
            "multichannel": result(integrated_speech_percentage=46.916183),
        }
    }
    lines = summary(manifest(track))
    assert lines[0] == "  Atmos, binaural render"
    assert lines[1] == "    Integrated loudness  -20.9 LKFS (speech-gated)"
    assert lines[6] == "  Atmos, 5.1 render"
    assert lines[8] == "    Speech               46.9 %"


def test_missing_values_read_as_not_available():
    lines = summary(manifest({"channel_based_loudness": {"mono": {}}}))
    assert lines == [
        "  1.0",
        "    Integrated loudness  n/a",
        "    Speech               n/a",
        "    Loudness range       n/a",
        "    True peak            n/a",
        "    Sample peak          n/a",
    ]


# --- run_measure


def measure_plan(tmp_path: Path, output: Path | None = None) -> JobPlan:
    temp = tmp_path / "temp"
    argv = ("dee_measure_loudness", "--loglevel", "info")
    dee = DeeStep(argv=argv, output=temp / "loudness.json")
    return JobPlan(
        format="measure",
        source=tmp_path / "in.mkv",
        output=output or dee.output,
        temp_dir=temp,
        steps=(dee,),
        free_space_needed=1,
    )


@pytest.fixture
def dee_writes(monkeypatch):
    """run_steps stands in for DEE, writing ``text`` as its manifest."""
    written = {"text": json.dumps(manifest({"id": "C:/temp/job/measure.wav"}))}

    def fake(plan, _payload):
        out = run.dee_output(plan)
        if written["text"] is not None:
            out.write_text(written["text"], encoding="utf-8")
        return out

    monkeypatch.setattr(run, "run_steps", fake)
    return written


def payload(overwrite=False, keep_temp=False):
    p = generate_dummy_core_payload()
    p.overwrite = overwrite
    p.keep_temp = keep_temp
    return p


def test_the_manifest_names_the_source_and_goes_with_the_temp_dir(tmp_path, dee_writes):
    plan = measure_plan(tmp_path)
    got = run.run_measure(plan, payload())
    (track,) = got["loudness_manifest"]["tracks"]
    assert track["id"] == str(tmp_path / "in.mkv")
    assert not plan.temp_dir.exists()


def test_a_saved_manifest_is_written_to_the_output(tmp_path, dee_writes):
    out = tmp_path / "saved" / "in.loudness.json"
    got = run.run_measure(measure_plan(tmp_path, out), payload())
    assert json.loads(out.read_text(encoding="utf-8")) == got


def test_an_existing_manifest_is_kept_without_overwrite(tmp_path, dee_writes):
    out = tmp_path / "in.loudness.json"
    out.write_text("keep", encoding="utf-8")
    with pytest.raises(OutputExistsError):
        run.run_measure(measure_plan(tmp_path, out), payload())
    assert out.read_text(encoding="utf-8") == "keep"

    run.run_measure(measure_plan(tmp_path, out), payload(overwrite=True))
    assert json.loads(out.read_text(encoding="utf-8"))["loudness_manifest"]


def test_no_manifest_from_dee_is_an_error(tmp_path, dee_writes):
    dee_writes["text"] = None
    with pytest.raises(OutputFileNotFoundError):
        run.run_measure(measure_plan(tmp_path), payload())
    dee_writes["text"] = "not json"
    with pytest.raises(OutputFileNotFoundError):
        run.run_measure(measure_plan(tmp_path), payload())


def test_a_dry_run_prints_the_commands_and_runs_nothing(tmp_path, monkeypatch, capsys):
    plan = measure_plan(tmp_path)
    monkeypatch.setattr(measure_mod, "plan", lambda _payload: plan)

    def must_not_run(*_args):
        raise AssertionError("a dry run ran the plan")

    monkeypatch.setattr(measure_mod, "run_measure", must_not_run)
    p = payload()
    p.dry_run = True
    assert measure_mod.measure(p) is None
    assert capsys.readouterr().out.splitlines() == command_lines(plan)


# --- the CLI


@pytest.fixture
def parser():
    main = cli.create_main_parser()
    sub = main.add_subparsers(dest="sub_command")
    groups = cli.create_common_argument_groups()
    cli.create_encode_parsers(sub, groups)
    cli.create_other_parsers(sub, groups)
    return main


DEPS = {
    "ffmpeg_path": Path("/tools/ffmpeg"),
    "truehdd_path": None,
    "dee_path": Path("/tools/dee"),
}


def test_output_and_output_dir_are_exclusive(parser):
    with pytest.raises(SystemExit):
        parser.parse_args(["measure", "--output", "a.json", "--output-dir", "d", "x"])


def test_output_takes_one_input(parser, capsys):
    args = parser.parse_args(["measure", "--output", "a.json", "x.mkv", "y.mkv"])
    with pytest.raises(SystemExit) as stop:
        cli.execute_measure_command(args, [Path("x.mkv"), Path("y.mkv")], DEPS, None)
    assert stop.value.code == 1
    assert "--output-dir" in capsys.readouterr().err


def test_each_input_is_reported_and_failures_set_the_exit_code(
    parser, monkeypatch, capsys
):
    measured = manifest({"channel_based_loudness": {"stereo": result()}})

    def fake_measure(p):
        if p.file_input.name == "bad.mkv":
            raise OutputFileNotFoundError("no manifest")
        return measured

    monkeypatch.setattr(cli, "measure", fake_measure)
    files = [Path("a.mkv"), Path("bad.mkv"), Path("b.mkv")]
    args = parser.parse_args(["measure", *map(str, files)])
    with pytest.raises(SystemExit) as stop:
        cli.execute_measure_command(args, files, DEPS, None)
    assert stop.value.code == 1
    out, err = capsys.readouterr()
    assert out.splitlines()[0] == "a.mkv (track a:0)"
    assert out.count("Integrated loudness") == 2
    assert "1 of 3 measurements failed." in err


def test_the_shim_found_reaches_the_payload(parser, monkeypatch):
    shim = object()
    seen = []

    def fake_measure(p):
        seen.append(p.dee_shim)

    monkeypatch.setattr(cli, "measure", fake_measure)
    args = parser.parse_args(["measure", "x.mkv"])
    cli.execute_measure_command(args, [Path("x.mkv")], {**DEPS, "dee_shim": shim}, None)
    assert seen == [shim]


def test_the_payload_takes_the_measure_options(parser):
    args = parser.parse_args(
        ["measure", "--output-dir", "loud", "--loudness-preset", "ebu_r128"]
        + ["--thd-warp-mode", "loro", "--pipe", "never", "x.mkv"]
    )
    p = cli.PayloadBuilder.build_measure_payload(
        args, Path("x.mkv"), DEPS["ffmpeg_path"], None, DEPS["dee_path"]
    )
    assert p.output_dir == Path("loud")
    assert p.file_output is None
    assert p.loudness_preset is LoudnessPreset.EBU_R128
    assert p.thd_warp_mode is WarpMode.LORO
    assert p.pipe is PipeMode.NEVER
