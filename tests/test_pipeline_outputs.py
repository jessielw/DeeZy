"""No job overwrites its own source, another source of the run, or another job's output."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path

import pytest

import deezy.cli as cli
from deezy.exceptions import OutputCollisionError
from deezy.pipeline import encode as encode_mod, outputs
from deezy.pipeline.outputs import check_output, run_outputs
from deezy.pipeline.plan import JobPlan
from tests.utils.payload_helpers import generate_dummy_core_payload

CASE_FOLDED = os.path.normcase("A") == "a"


@pytest.fixture
def source(tmp_path: Path) -> Path:
    path = tmp_path / "Movie.ec3"
    path.write_bytes(b"source")
    return path


def test_the_output_may_not_be_its_own_source(source):
    with pytest.raises(OutputCollisionError, match="its own source"):
        check_output(source, source)


def test_its_own_source_is_refused_however_the_path_is_spelled(source, monkeypatch):
    monkeypatch.chdir(source.parent)
    with pytest.raises(OutputCollisionError, match="its own source"):
        check_output(Path("sub", "..", source.name), source)


@pytest.mark.skipif(not CASE_FOLDED, reason="the file system keeps case apart")
def test_its_own_source_is_refused_in_another_case(source):
    with pytest.raises(OutputCollisionError, match="its own source"):
        check_output(source.with_name("MOVIE.EC3"), source)


def test_outside_a_run_two_jobs_may_name_one_output(tmp_path, source):
    output = tmp_path / "out.ec3"
    check_output(output, source)
    check_output(output, source)


def test_a_second_job_with_the_same_output_is_refused(tmp_path, source):
    other = tmp_path / "Other.wav"
    output = tmp_path / "out.ec3"
    with run_outputs([source, other]):
        check_output(output, source)
        with pytest.raises(
            OutputCollisionError, match="also the output of .*Movie.ec3 in"
        ):
            check_output(output, other)


@pytest.mark.skipif(not CASE_FOLDED, reason="the file system keeps case apart")
def test_outputs_that_differ_only_in_case_collide(tmp_path, source):
    other = tmp_path / "Other.wav"
    with run_outputs([source, other]):
        check_output(tmp_path / "out.ec3", source)
        with pytest.raises(OutputCollisionError):
            check_output(tmp_path / "OUT.ec3", other)


def test_an_output_may_not_overwrite_another_source_of_the_run(tmp_path, source):
    other = tmp_path / "Other.ec3"
    with run_outputs([source, other]):
        with pytest.raises(OutputCollisionError, match="overwrite .*Other.ec3, which"):
            check_output(other, source)


def test_the_run_forgets_its_claims_when_it_ends(tmp_path, source):
    output = tmp_path / "out.ec3"
    with run_outputs([source]):
        check_output(output, source)
    assert outputs._claims is None
    with run_outputs([source]):
        check_output(output, source)


def test_parallel_jobs_claim_one_output_once(tmp_path):
    sources = [tmp_path / f"in{n}.wav" for n in range(16)]
    output = tmp_path / "out.ec3"

    def claim(src: Path) -> bool:
        try:
            check_output(output, src)
        except OutputCollisionError:
            return False
        return True

    with run_outputs(sources), ThreadPoolExecutor(max_workers=8) as pool:
        claimed = list(pool.map(claim, sources))
    assert claimed.count(True) == 1


def job(tmp_path: Path, output: Path, source: Path) -> JobPlan:
    return JobPlan(
        format="ddp",
        source=source,
        output=output,
        temp_dir=tmp_path / "temp",
        steps=(),
    )


def test_a_dry_run_is_refused_before_it_prints(tmp_path, source, monkeypatch, capsys):
    monkeypatch.setattr(encode_mod, "plan", lambda _p: job(tmp_path, source, source))
    payload = generate_dummy_core_payload()
    payload.dry_run = True
    payload.overwrite = True
    with pytest.raises(OutputCollisionError):
        encode_mod.encode(payload)
    assert capsys.readouterr().out == ""


def test_a_dry_run_says_an_existing_output_would_be_skipped(
    tmp_path, source, monkeypatch
):
    output = tmp_path / "out.ec3"
    output.write_bytes(b"old")
    monkeypatch.setattr(encode_mod, "plan", lambda _p: job(tmp_path, output, source))
    said = []
    monkeypatch.setattr(encode_mod.logger, "info", said.append)
    payload = generate_dummy_core_payload()
    payload.dry_run = True
    payload.overwrite = False
    assert encode_mod.encode(payload) == output
    assert any("would be skipped" in line for line in said)


def encode_args(tmp_path: Path, **overrides) -> argparse.Namespace:
    fields = {
        "allow_sleep": True,
        "batch_output_dir": None,
        "batch_summary_output": False,
        "jitter_ms": 0,
        "max_batch_results": None,
        "max_logs": None,
        "max_parallel": 1,
        "output": None,
        "output_preview": False,
        "working_dir": str(tmp_path),
    }
    return argparse.Namespace(**{**fields, **overrides})


def test_output_with_several_inputs_is_refused_before_any_job(tmp_path, monkeypatch):
    def must_not_run(*_args):
        raise AssertionError("a job ran")

    monkeypatch.setattr(cli, "encode_single_file", must_not_run)
    args = encode_args(tmp_path, output=str(tmp_path / "out.ec3"))
    with pytest.raises(SystemExit):
        cli.execute_encode_command(
            args, [tmp_path / "a.wav", tmp_path / "b.wav"], {}, None
        )


@pytest.mark.parametrize("mode", ["dry_run", "output_preview"])
def test_a_preview_does_not_create_or_trim_work_files(tmp_path, monkeypatch, mode):
    old_log = tmp_path / "logs" / "old.log"
    old_log.parent.mkdir()
    old_log.touch()
    temp_dir = tmp_path / "temp"
    args = encode_args(
        tmp_path, allow_sleep=False, temp_dir=str(temp_dir), max_logs=0, **{mode: True}
    )

    def acquire(_self):
        pytest.fail("A preview requested a sleep inhibitor")

    monkeypatch.setattr(cli.SleepInhibitor, "acquire", acquire)
    monkeypatch.setattr(
        cli,
        "encode_single_file",
        lambda *_args: (tmp_path / "in.wav", tmp_path / "out.ec3"),
    )
    cli.execute_encode_command(args, [tmp_path / "in.wav"], {}, None)

    assert old_log.is_file()
    assert not (tmp_path / "batch-results").exists()
    assert not temp_dir.exists()


@pytest.mark.parametrize(
    ("inputs", "max_parallel", "ids"),
    [
        (["a.wav"], 1, [None]),
        (["a.wav", "b.wav"], 1, ["f1", "f2"]),
        (["a.wav", "b.wav"], 2, ["f1", "f2"]),
    ],
)
def test_only_a_batch_puts_job_ids_in_its_names(
    tmp_path, monkeypatch, inputs, max_parallel, ids
):
    seen = {}

    def fake_job(_args, input_file, _deps, _worker, _short, file_id):
        seen[input_file.name] = file_id
        return input_file, tmp_path / f"{input_file.stem}.ec3"

    monkeypatch.setattr(cli, "encode_single_file", fake_job)
    args = encode_args(tmp_path, max_parallel=max_parallel, no_progress_bars=True)
    cli.execute_encode_command(args, [tmp_path / n for n in inputs], {}, None)
    assert [seen[n] for n in inputs] == ids


@pytest.mark.parametrize("max_parallel", [1, 2])
def test_a_batch_refuses_its_second_job_with_the_same_output(
    tmp_path, monkeypatch, max_parallel
):
    output = tmp_path / "out.ec3"
    inputs = [tmp_path / "a.wav", tmp_path / "b.wav"]
    refused = []

    def fake_job(_args, input_file, *_rest):
        try:
            check_output(output, input_file)
        except OutputCollisionError:
            refused.append(input_file)
            raise
        return input_file, output

    monkeypatch.setattr(cli, "encode_single_file", fake_job)
    args = encode_args(tmp_path, max_parallel=max_parallel, no_progress_bars=True)
    # a failed job ends the run with exit code 1
    with pytest.raises(SystemExit):
        cli.execute_encode_command(args, inputs, {}, None)
    assert len(refused) == 1
    assert outputs._claims is None
