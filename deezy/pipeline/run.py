"""
Runs a `JobPlan`: the temp directory, the batch's process slots, temp-file
reuse, cleanup of partial output, and the move to the destination.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import random
import re
import shutil
import tempfile
import threading
import time
import uuid

import platformdirs

from deezy.audio_processors.dee import process_dee_job
from deezy.audio_processors.ffmpeg import process_ffmpeg_job
from deezy.audio_processors.pipe import process_pipe_job
from deezy.audio_processors.truehdd import damf_warp_mode, decode_truehd_to_atmos
from deezy.dee.shim import shim_binary
from deezy.exceptions import (
    DependencyNotFoundError,
    InputFileNotFoundError,
    NotEnoughSpaceError,
    OutputExistsError,
    OutputFileNotFoundError,
    PathTooLongError,
)
from deezy.payloads.shared import CorePayload
from deezy.pipeline.plan import (
    DeeStep,
    FfmpegStep,
    JobPlan,
    PipeStep,
    Step,
    TruehddStep,
)
from deezy.pipeline.show import step_line
from deezy.utils.logger import logger
from deezy.utils.paths import (
    MAX_ARTIFACT_NAME,
    MAX_DEE_PATH,
    artifact_stem,
    long_path_str,
)


class _Limits:
    """How many FFmpeg, DEE and truehdd processes a batch runs at once."""

    ffmpeg: threading.Semaphore | None = None
    dee: threading.Semaphore | None = None
    truehdd: threading.Semaphore | None = None
    jitter_ms: int = 0


def init_phase_limits(
    max_parallel: int,
    jitter_ms: int | None = None,
    ffmpeg_limit: int | None = None,
    dee_limit: int | None = None,
    truehdd_limit: int | None = None,
) -> None:
    """
    Size the per-tool slots for a batch of ``max_parallel`` workers.

    A limit above ``max_parallel`` is capped to it, with a warning.
    ``jitter_ms`` is the most a job waits at random before each heavy step.
    """
    limits = {}
    for flag, given in (
        ("ffmpeg", ffmpeg_limit),
        ("dee", dee_limit),
        ("truehdd", truehdd_limit),
    ):
        wanted = given if given is not None else max(1, max_parallel)
        capped = min(max(1, wanted), max_parallel)
        if given is not None and capped != wanted:
            logger.warning(
                f"--limit-{flag} {given} capped to {capped} "
                f"(max_parallel={max_parallel})"
            )
        limits[flag] = capped
    _Limits.ffmpeg = threading.Semaphore(limits["ffmpeg"])
    _Limits.dee = threading.Semaphore(limits["dee"])
    _Limits.truehdd = threading.Semaphore(limits["truehdd"])
    if jitter_ms is not None:
        _Limits.jitter_ms = int(jitter_ms)


@contextmanager
def slot(tool: str) -> Iterator[None]:
    """Hold one of the batch's slots for ``tool`` ('ffmpeg', 'dee', 'truehdd')."""
    sem: threading.Semaphore | None = getattr(_Limits, tool)
    if sem:
        sem.acquire()
    try:
        yield
    finally:
        if sem:
            try:
                sem.release()
            except ValueError:
                pass


def jitter() -> None:
    """A short random wait before a heavy step, when the batch asks for one."""
    if _Limits.jitter_ms > 0:
        time.sleep(random.uniform(0, _Limits.jitter_ms) / 1000.0)  # noqa: S311 - scheduling jitter is not security-sensitive


def short_unique_name(file_input: Path) -> str:
    """A short name for the input's temp directory, unique to its full path."""
    sanitized = re.sub(r"[^A-Za-z0-9_-]", "_", file_input.stem)[:20]
    hash_prefix = hashlib.sha1(
        str(file_input).encode("utf-8"), usedforsecurity=False
    ).hexdigest()[:8]
    return f"{sanitized}_{hash_prefix}"


def temp_dir_path(
    file_input: Path,
    temp_base: Path | None,
    track_label: str | None = None,
    keep_temp: bool = False,
) -> Path:
    """
    The job's temp directory, under ``temp_base`` or DeeZy's data folder.

    Kept temp directories are named per input and track, so a later run finds
    them again; others get a random suffix. Raises `PathTooLongError` when the
    directory leaves no room for a job file within the path limit. Nothing is
    created.
    """
    base_name = short_unique_name(file_input)
    safe_label = re.sub(r"[^A-Za-z0-9_-]", "_", track_label)[:8] if track_label else ""
    dir_name = f"{base_name}_{safe_label}" if safe_label else base_name
    if not keep_temp:
        dir_name = f"{dir_name}_{uuid.uuid4().hex[:4]}"
    base = temp_base or Path(platformdirs.user_data_dir()) / "deezy"
    temp_dir = base / dir_name

    # DEE gets an extended-length path when one is too long for it, but FFMPEG
    # and truehdd write into this directory too, so it still has to leave room
    # for a job file inside the platform's ordinary path limit
    if len(str(temp_dir)) + 1 + MAX_ARTIFACT_NAME > MAX_DEE_PATH:
        raise PathTooLongError(
            f"Temp directory '{temp_dir}' is too deep to hold a job file "
            f"within the {MAX_DEE_PATH} character path limit. Use a shorter "
            "--temp-dir."
        )
    return temp_dir


def check_input_file(input_file: Path) -> None:
    if not input_file.exists():
        raise InputFileNotFoundError(f"Could not find {input_file.name}.")


def check_disk_space(
    input_file: Path, drive_path: Path, recommended_free_space: int | None
) -> None:
    """
    Refuse a job when the temp directory's drive lacks the space it needs:
    ``recommended_free_space``, or else 110% of the input's size.
    """
    required = recommended_free_space or int(os.path.getsize(input_file) * 1.1)
    if shutil.disk_usage(drive_path).free < required:
        raise NotEnoughSpaceError(
            "Insufficient storage in the temporary directory to complete the process. "
            f"Calculated required storage (bytes): {required}"
        )


def metadata_path(temp_dir: Path, output: Path) -> Path:
    """The reuse metadata for one output's temp files."""
    return temp_dir / f"{artifact_stem(output)}_metadata.json"


def read_reuse_metadata(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        logger.debug("Failed to read/parse metadata.json; ignoring and continuing.")
        return None


def check_reuse_signature(
    path: Path, encoder_id: str, signature: str, produced_file: str, temp_dir: Path
) -> bool:
    """
    True when ``encoder_id``'s recorded step had this ``signature`` and its
    file is still in ``temp_dir``. The metadata holds one entry per encoder:

        {"source_mtime": ..., "source_size": ...,
         "encoders": {"dd": {"signature": "...", "produced_file": "..."}}}
    """
    meta = read_reuse_metadata(path)
    if not meta:
        return False
    entry = (meta.get("encoders") or {}).get(encoder_id)
    if entry:
        recorded, recorded_file = entry.get("signature"), entry.get("produced_file")
        if recorded and recorded_file and recorded == signature:
            return (temp_dir / recorded_file).exists()
    return False


def write_signature_metadata(
    path: Path, encoder_id: str, signature: str, produced_file: str, source: Path
) -> None:
    """Record ``encoder_id``'s step, merged into the metadata atomically. Never raises."""
    try:
        existing = read_reuse_metadata(path) or {}
        src_mtime = existing.get("source_mtime") or int(source.stat().st_mtime)
        src_size = existing.get("source_size") or int(source.stat().st_size)
        encoders = existing.get("encoders") or {}
        encoders[encoder_id] = {"signature": signature, "produced_file": produced_file}
        meta = {
            "source_mtime": int(src_mtime),
            "source_size": int(src_size),
            "encoders": encoders,
        }
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", delete=False, dir=str(path.parent), encoding="utf-8"
            ) as fh:
                json.dump(meta, fh)
                tmp_path = Path(fh.name)
            os.replace(str(tmp_path), str(path))
        finally:
            if tmp_path and tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    logger.debug("Failed to remove temporary metadata file.")
    except Exception:
        logger.debug("Failed to write metadata.json for reuse.")


def announce(step: Step, print_commands: bool) -> None:
    """Print the step's command line (``--print-commands``) as it starts."""
    if print_commands:
        print(step_line(step), flush=True)


def run_ffmpeg(step: FfmpegStep, plan: JobPlan, payload: CorePayload) -> None:
    """
    Write the job's WAV with FFmpeg, or reuse the one an earlier run made.

    FFmpeg errors propagate: without the WAV, DEE has nothing to encode.
    """
    signature = " ".join(step.argv)
    meta = metadata_path(plan.temp_dir, plan.output)
    reuse = bool(getattr(payload, "reuse_temp_files", False))
    if reuse and check_reuse_signature(
        meta, step.reuse_id, signature, step.output.name, plan.temp_dir
    ):
        logger.info("Reusing extracted wav from temp folder")
        return

    jitter()
    with slot("ffmpeg"):
        announce(step, payload.print_commands)
        ffmpeg_job = process_ffmpeg_job(
            cmd=list(step.argv),
            steps=True,
            duration=step.duration,
            step_info={"current": 1, "total": 3, "name": "FFMPEG"},
            no_progress_bars=payload.no_progress_bars,
        )
    logger.debug(f"FFMPEG job: {ffmpeg_job}.")
    if reuse:
        write_signature_metadata(
            meta, step.reuse_id, signature, step.output.name, plan.source
        )


def run_truehdd(step: TruehddStep, plan: JobPlan, payload: CorePayload) -> None:
    """Decode the TrueHD Atmos stream to a DAMF, or reuse an earlier decode."""
    meta = metadata_path(plan.temp_dir, plan.output)
    reuse = bool(getattr(payload, "reuse_temp_files", False))
    jitter()
    with slot("truehdd"):
        if reuse and check_reuse_signature(
            meta, step.reuse_id, step.signature, step.output.name, plan.temp_dir
        ):
            logger.info("Reusing decoded atmos from temp folder")
            return
        announce(step, payload.print_commands)
        decode_truehd_to_atmos(
            output_dir=step.output_dir,
            file_input=step.file_input,
            track_index=step.track_index,
            ffmpeg_path=step.ffmpeg,
            truehdd_path=step.truehdd,
            warp_mode=step.warp_mode,
            duration=step.duration,
            step_info={"current": 1, "total": 3, "name": "truehdd"},
            no_progress_bars=payload.no_progress_bars,
        )
        if step.warp_mode is None and damf_warp_mode(step.output) is None:
            logger.info(
                "The TrueHD Atmos stream has no warp mode, so DEE renders it as "
                "warping, its default. Use --thd-warp-mode to choose another."
            )
        if reuse:
            write_signature_metadata(
                meta, step.reuse_id, step.signature, step.output.name, plan.source
            )


def missing_tool(tool: Path) -> DependencyNotFoundError:
    """The error for a DEE tool that isn't in the DEE folder."""
    hint = ""
    if tool.stem == "dee_dthd_encoder":
        hint = " DEE 6.7 for Linux comes without the TrueHD encoder."
    return DependencyNotFoundError(f"{tool.name} is not in {tool.parent}.{hint}")


def run_dee(
    step: DeeStep, no_progress_bars: bool, print_commands: bool = False
) -> None:
    """
    Run DEE in one of the batch's DEE slots.

    A failed run leaves a 0-byte or cut-off file at the step's output, so it is
    deleted rather than kept with the temp files.
    """
    # dee_shim would refuse a missing DEE tool with a less helpful message
    binary = shim_binary(step.argv)
    if binary is not None and not binary.is_file():
        raise missing_tool(binary)
    jitter()
    with slot("dee"):
        announce(step, print_commands)
        try:
            dee_job = process_dee_job(
                cmd=list(step.argv),
                step_info={"current": 2, "total": 3, "name": "DEE measure"},
                no_progress_bars=no_progress_bars,
                custom_dialnorm=step.custom_dialnorm,
            )
        except FileNotFoundError as e:
            tool = Path(step.argv[0])
            if tool.is_file():
                raise
            raise missing_tool(tool) from e
        except BaseException:
            try:
                Path(long_path_str(step.output)).unlink(missing_ok=True)
            except OSError:
                logger.debug(f"Could not delete the partial encode {step.output}.")
            raise
    logger.debug(f"Dee job: {dee_job}.")


def _stopped_short(step: PipeStep, written: int | None) -> bool:
    """Whether FFmpeg wrote more samples than DEE was told to read."""
    count = step.pipe.sample_count
    if count is None:
        return False
    if written is None:
        logger.debug("FFMPEG did not report what it wrote into the pipe.")
        return True
    return written // step.pipe.frame_bytes > count


def _without_sample_count(step: PipeStep) -> tuple[str, ...]:
    """The step's DEE command, with no sample count in its input format."""
    told = step.pipe.dee_input_format
    untold = replace(step.pipe, sample_count=None).dee_input_format
    return tuple(untold if arg == told else arg for arg in step.dee.argv)


def run_pipe(
    step: PipeStep, no_progress_bars: bool, print_commands: bool = False
) -> None:
    """
    Run FFmpeg into DEE through the step's named pipe, holding a DEE and an
    FFmpeg slot.

    Only a pipe step holds two slots, and every one takes DEE's first, so jobs
    waiting on each other's slots can't block each other for good. DEE stops
    silently at the pipe's sample count, so a source longer than its count
    (one whose length was misreported) is encoded again without one. A failed
    run's partial output is deleted, as in `run_dee`.
    """
    jitter()
    with slot("dee"), slot("ffmpeg"):
        announce(step, print_commands)

        def encode(dee_argv: tuple[str, ...]) -> int | None:
            return process_pipe_job(
                dee_cmd=list(dee_argv),
                ffmpeg_cmd=list(step.ffmpeg_argv),
                pipe_name=step.pipe.name,
                step_info={"current": 1, "total": 2, "name": "DEE measure"},
                no_progress_bars=no_progress_bars,
                custom_dialnorm=step.dee.custom_dialnorm,
            )

        try:
            if _stopped_short(step, encode(step.dee.argv)):
                logger.warning(
                    "The source is longer than its reported duration, so DEE "
                    "stopped short of the end. Encoding it again without a "
                    "sample count; its progress will be coarse."
                )
                encode(_without_sample_count(step))
        except BaseException:
            try:
                Path(long_path_str(step.dee.output)).unlink(missing_ok=True)
            except OSError:
                logger.debug(f"Could not delete the partial encode {step.dee.output}.")
            raise


def finalize_output(dee_output: Path, output: Path) -> None:
    """Move DEE's finished encode from the temp directory to its destination."""
    if not dee_output.is_file():
        raise OutputFileNotFoundError(
            f"DEE reported success but left no output at {dee_output.name}"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    # the destination may be longer than the host can open unescaped, and
    # overwriting was already settled by the early output-exists check
    src, dst = long_path_str(dee_output), long_path_str(output)
    try:
        # atomic, and a cheap rename when temp shares a volume with the output
        os.replace(src, dst)
    except OSError:
        # different volumes; copy across and drop the temp copy
        shutil.move(src, dst)
    logger.debug(f"Moved encode to output path {output}.")


def dee_output(plan: JobPlan) -> Path:
    """What the plan's last DEE step writes into the temp directory."""
    for step in reversed(plan.steps):
        if isinstance(step, PipeStep):
            return step.dee.output
        if isinstance(step, DeeStep):
            return step.output
    raise OutputFileNotFoundError("The plan has no DEE step.")


def run_steps(plan: JobPlan, payload: CorePayload) -> Path:
    """Run every step of ``plan`` and return what its DEE step wrote."""
    for step in plan.steps:
        if isinstance(step, FfmpegStep):
            logger.debug(f"ffmpeg_cmd={list(step.argv)}.")
            run_ffmpeg(step, plan, payload)
        elif isinstance(step, TruehddStep):
            run_truehdd(step, plan, payload)
        elif isinstance(step, PipeStep):
            logger.debug(f"dee_cmd={list(step.dee.argv)}.")
            logger.debug(f"ffmpeg_cmd={list(step.ffmpeg_argv)}.")
            run_pipe(step, payload.no_progress_bars, payload.print_commands)
        else:
            logger.debug(f"dee_cmd={list(step.argv)}.")
            run_dee(step, payload.no_progress_bars, payload.print_commands)
    return dee_output(plan)


def run_measure(plan: JobPlan, payload: CorePayload) -> dict:
    """
    Run a measurement plan and return DEE's loudness manifest, saved at the
    plan's output unless that is DEE's own copy in the temp directory.
    """
    manifest_path = dee_output(plan)
    save = plan.output != manifest_path
    keep_temp = bool(getattr(payload, "keep_temp", False))
    plan.temp_dir.mkdir(parents=True, exist_ok=True)
    try:
        check_disk_space(plan.source, plan.temp_dir, plan.free_space_needed)
        if save and plan.output.exists() and not payload.overwrite:
            raise OutputExistsError(f"Output already exists: {plan.output}")
        run_steps(plan, payload)
        try:
            text = Path(long_path_str(manifest_path)).read_text(encoding="utf-8")
            manifest = json.loads(text)
        except (OSError, ValueError) as e:
            raise OutputFileNotFoundError(
                f"DEE reported success but left no readable loudness manifest ({e})"
            ) from e
        # DEE names each track after what it read: DeeZy's temp WAV, pipe or DAMF
        for track in manifest.get("loudness_manifest", {}).get("tracks", []):
            track["id"] = str(plan.source)
        if save:
            plan.output.parent.mkdir(parents=True, exist_ok=True)
            Path(long_path_str(plan.output)).write_text(
                json.dumps(manifest, indent=4) + "\n", encoding="utf-8"
            )
            logger.info(f"Loudness manifest saved: {plan.output}")
        return manifest
    finally:
        clean_temp(plan.temp_dir, keep_temp)


def run_plan(plan: JobPlan, payload: CorePayload) -> Path:
    """Run every step of ``plan`` and return the finished output."""
    if plan.preview:
        logger.info(f"Output preview: {plan.output}")
        return plan.output

    keep_temp = bool(getattr(payload, "keep_temp", False))
    plan.temp_dir.mkdir(parents=True, exist_ok=True)
    try:
        logger.debug(f"Temp directory {plan.temp_dir}.")
        check_disk_space(plan.source, plan.temp_dir, plan.free_space_needed)
        if plan.output.exists():
            if not payload.overwrite:
                raise OutputExistsError(f"Output already exists: {plan.output}")
            logger.debug(
                f"Output already exists and will be overwritten: {plan.output}"
            )

        dee_output = run_steps(plan, payload)
        finalize_output(dee_output, plan.output)
        if not plan.output.is_file():
            raise OutputFileNotFoundError(f"{plan.output.name} output not found")
        return plan.output
    finally:
        clean_temp(plan.temp_dir, keep_temp)


def clean_temp(temp_dir: Path, keep_temp: bool) -> None:
    """Delete the job's temp directory unless it is kept. Never raises."""
    if keep_temp or not temp_dir.exists():
        return
    try:
        logger.debug(f"Cleaning temp directory ({temp_dir}).")
        shutil.rmtree(temp_dir)
        logger.debug("Temp directory cleaned.")
    except Exception as cleanup_exc:
        logger.warning(f"Cleaning temp dir failed ({temp_dir}): {cleanup_exc}")
