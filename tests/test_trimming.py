import argparse
import os
import tempfile
import time
from pathlib import Path

from deezy.cli.__init__ import execute_encode_command


def _create_files(dirpath: Path, prefix: str, count: int) -> list[Path]:
    files = []
    for i in range(count):
        p = dirpath / f"{prefix}_{i}.log"
        p.write_text(f"test {i}\n")
        # stagger mtimes so sorting by mtime is deterministic
        os.utime(p, (time.time() + i, time.time() + i))
        files.append(p)
    return files


def test_trim_logs_respects_cli_max_logs():
    with tempfile.TemporaryDirectory() as td:
        work_dir = Path(td)
        logs_dir = work_dir / "logs"
        batch_dir = work_dir / "batch-results"
        logs_dir.mkdir(parents=True)
        batch_dir.mkdir(parents=True)

        # create 5 log files with increasing mtime
        _create_files(logs_dir, "log", 5)

        args = argparse.Namespace()
        args.max_parallel = 1
        args.working_dir = str(work_dir)
        args.max_logs = 2
        args.max_batch_results = None
        # other attributes used by function but not relevant for trimming
        args.batch_summary_output = False

        # call with no inputs so execute_encode_command returns after trimming
        execute_encode_command(args, [], {}, None)

        remaining = sorted(list(logs_dir.glob("*.log")))
        # should have only 2 newest files
        assert len(remaining) == 2


def test_trim_batch_results_respects_cli_max_batch_results():
    with tempfile.TemporaryDirectory() as td:
        work_dir = Path(td)
        logs_dir = work_dir / "logs"
        batch_dir = work_dir / "batch-results"
        logs_dir.mkdir(parents=True)
        batch_dir.mkdir(parents=True)

        # create 4 json files
        for i in range(4):
            p = batch_dir / f"result_{i}.json"
            p.write_text(f'{{"i": {i}}}\n')
            os.utime(p, (time.time() + i, time.time() + i))

        args = argparse.Namespace()
        args.max_parallel = 1
        args.working_dir = str(work_dir)
        args.max_logs = None
        args.max_batch_results = 1
        args.batch_summary_output = False

        execute_encode_command(args, [], {}, None)

        remaining = sorted(list(batch_dir.glob("*.json")))
        assert len(remaining) == 1
