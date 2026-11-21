"""The command lines a plan runs, written out for a shell."""

import os
import shlex
import subprocess

from deezy.audio_processors import dee, ffmpeg
from deezy.audio_processors.truehdd import truehd_extract_command, truehdd_command
from deezy.pipeline.plan import DeeStep, FfmpegStep, JobPlan, Step


def shell_line(argv: list[str]) -> str:
    """``argv`` quoted for this platform's shell."""
    if os.name == "nt":
        return subprocess.list2cmdline(argv)
    return shlex.join(argv)


def step_line(step: Step) -> str:
    """The command line a step runs, with DeeZy's log levels filled in.

    FFmpeg's progress options, which DeeZy adds only to drive its display, are
    left out.
    """
    if isinstance(step, FfmpegStep):
        return shell_line(ffmpeg.with_loglevel(list(step.argv)))
    if isinstance(step, DeeStep):
        return shell_line(dee.with_loglevel(list(step.argv)))
    extract = truehd_extract_command(step.ffmpeg, step.file_input, step.track_index)
    decode = truehdd_command(step.truehdd, step.output_dir, step.warp_mode)
    return f"{shell_line(extract)} | {shell_line(decode)}"


def command_lines(plan: JobPlan) -> list[str]:
    """Every command line of ``plan``, in the order they run."""
    return [step_line(step) for step in plan.steps]
