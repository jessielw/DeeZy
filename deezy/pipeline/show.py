"""The command lines a plan runs, written out for a shell."""

import os
import shlex
import subprocess

from deezy.audio_processors import dee, ffmpeg
from deezy.audio_processors.truehdd import truehd_extract_command, truehdd_command
from deezy.pipeline.plan import DeeStep, FfmpegStep, JobPlan, PipeStep, Step


def shell_line(argv: list[str]) -> str:
    """``argv`` quoted for this platform's shell."""
    if os.name == "nt":
        return subprocess.list2cmdline(argv)
    return shlex.join(argv)


def step_lines(step: Step) -> list[str]:
    """The command lines a step runs, with DeeZy's log levels filled in.

    A pipe step runs two at once: DEE, which opens the pipe, then FFmpeg,
    which writes into it. FFmpeg's progress options, which DeeZy adds only to
    drive its display, are left out.
    """
    if isinstance(step, PipeStep):
        return [
            shell_line(dee.with_loglevel(list(step.dee.argv))),
            shell_line(ffmpeg.with_loglevel(list(step.ffmpeg_argv))),
        ]
    if isinstance(step, FfmpegStep):
        return [shell_line(ffmpeg.with_loglevel(list(step.argv)))]
    if isinstance(step, DeeStep):
        return [shell_line(dee.with_loglevel(list(step.argv)))]
    extract = truehd_extract_command(step.ffmpeg, step.file_input, step.track_index)
    decode = truehdd_command(step.truehdd, step.output_dir, step.warp_mode)
    return [f"{shell_line(extract)} | {shell_line(decode)}"]


def step_line(step: Step) -> str:
    """`step_lines`, one per line."""
    return "\n".join(step_lines(step))


def command_lines(plan: JobPlan) -> list[str]:
    """Every command line of ``plan``, in the order they start."""
    return [line for step in plan.steps for line in step_lines(step)]
