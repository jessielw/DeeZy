"""The files a run's jobs write, so that no job overwrites a source or another job's output."""

from collections.abc import Iterable, Iterator
from contextlib import contextmanager
import os
from pathlib import Path
import threading

from deezy.exceptions import OutputCollisionError

_lock = threading.Lock()
# while a run is open: output key -> the source whose job writes it
_claims: dict[str, Path] | None = None
# while a run is open: source key -> the source
_sources: dict[str, Path] = {}


def path_key(path: Path | str) -> str:
    """
    One spelling per file: absolute, normalised and, on Windows, case-folded
    (NTFS ignores case, so `Movie.ec3` and `movie.ec3` are one file).
    """
    return os.path.normcase(os.path.abspath(path))


def begin_run(sources: Iterable[Path]) -> None:
    """
    Open a run of jobs over ``sources``. Until `end_run`, each job claims its
    output in `check_output`, and a job whose output is another job's, or one
    of the run's sources, is refused before it does any work.
    """
    global _claims, _sources
    with _lock:
        _claims = {}
        _sources = {path_key(source): Path(source) for source in sources}


def end_run() -> None:
    """Close the run `begin_run` opened."""
    global _claims, _sources
    with _lock:
        _claims = None
        _sources = {}


@contextmanager
def run_outputs(sources: Iterable[Path]) -> Iterator[None]:
    """A run over ``sources`` for the length of a ``with`` block."""
    begin_run(sources)
    try:
        yield
    finally:
        end_run()


def _same_file(a: Path, b: Path) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def check_output(output: Path, source: Path) -> None:
    """
    Refuse an output that would overwrite the job's own source (even with
    --overwrite), and, while a run is open, one of the run's other sources or
    another job's output; otherwise claim it for this job.
    """
    if path_key(output) == path_key(source) or _same_file(output, source):
        raise OutputCollisionError(
            f"The output would overwrite its own source: {output}. "
            "Give another name with --output or --output-template."
        )
    key = path_key(output)
    with _lock:
        if _claims is None:
            return
        other = _sources.get(key)
        if other is not None:
            raise OutputCollisionError(
                f"The output {output} would overwrite {other}, "
                "which this run also encodes."
            )
        other = _claims.get(key)
        if other is not None:
            raise OutputCollisionError(
                f"The output {output} is also the output of {other} in "
                "this run. Give each job its own name, with an output "
                "template that tells them apart (for example {stem} or "
                "{worker})."
            )
        _claims[key] = Path(source)
