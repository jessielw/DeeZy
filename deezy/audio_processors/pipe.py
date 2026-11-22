"""
FFmpeg streaming PCM into DEE through a Windows named pipe.

DEE creates the pipe and waits for a writer, so it starts first; FFmpeg starts
once the pipe exists and writes the samples into it. DEE's progress drives the
display, and FFmpeg runs without one.

DEE ends its encode cleanly at the end of the stream, however the stream
ends, so an FFmpeg that dies partway would leave a short encode that looks
complete. FFmpeg's failure therefore fails the job, whatever DEE reports.
FFmpeg reports how many bytes it wrote, so a caller can also tell whether DEE
read them all.
"""

import os
import re
from subprocess import PIPE, STDOUT, Popen
import threading
import time

from deezy.audio_processors.dee import process_dee_job
from deezy.audio_processors.ffmpeg import MAX_CAPTURED_LINES, with_loglevel
from deezy.exceptions import PipeError
from deezy.utils.logger import logger
from deezy.utils.tool_log import ToolLog

# the Windows namespace named pipes live in
PIPE_ROOT = "\\\\.\\pipe\\"
# DEE opens its pipe within a second of starting
PIPE_OPEN_TIMEOUT = 60.0
# FFmpeg ends as soon as DEE closes the pipe
FFMPEG_EXIT_TIMEOUT = 10.0
# a line of FFmpeg's -progress report, such as 'total_size=1024'
_PROGRESS_LINE = re.compile(r"([a-z0-9_]+)=(.*)")


def pipe_exists(name: str) -> bool:
    """
    Whether the named pipe ``name`` exists.

    Lists the pipe namespace rather than opening the pipe: opening it would
    take the one connection DEE waits for.
    """
    return name in os.listdir(PIPE_ROOT)


class _Feeder:
    """FFmpeg writing into DEE's pipe, on a thread of its own."""

    def __init__(
        self, cmd: list[str], pipe_name: str, log: ToolLog | None = None
    ) -> None:
        self.cmd = cmd
        self.pipe_name = pipe_name
        self.log = log
        self.dee: Popen | None = None
        self.proc: Popen | None = None
        self.returncode: int | None = None
        # the bytes FFmpeg has written into the pipe, from its progress report
        self.written: int | None = None
        self.tail: list[str] = []
        # DEE was ended here because FFmpeg failed
        self.killed_dee = False
        self.error: BaseException | None = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self, dee: Popen) -> None:
        """Wait on a new thread for ``dee`` to open its pipe, then run FFmpeg."""
        self.dee = dee
        self._thread.start()

    def _run(self) -> None:
        if self.dee is None:
            return
        try:
            if not self._wait_for_pipe(self.dee):
                return
            with Popen(  # noqa: S603 - DeeZy's own planned FFmpeg command
                self.cmd, stdout=PIPE, stderr=STDOUT, text=True, errors="replace"
            ) as proc:
                self.proc = proc
                if proc.stdout:
                    for line in proc.stdout:
                        self._read(line.strip())
                self.returncode = proc.wait()
            if self.returncode != 0:
                self._end_dee()
        except BaseException as e:
            self.error = e
            self._end_dee()

    def _read(self, line: str) -> None:
        """Note FFmpeg's progress report, and log and keep its other lines."""
        if not line:
            return
        if report := _PROGRESS_LINE.fullmatch(line):
            key, value = report.groups()
            if key == "total_size" and value.isdigit():
                self.written = int(value)
            return
        logger.debug(line)
        self.tail.append(line)
        del self.tail[:-MAX_CAPTURED_LINES]
        if self.log is not None:
            self.log.add("ffmpeg", line)

    def _wait_for_pipe(self, dee: Popen) -> bool:
        """True once DEE's pipe exists; False if DEE exits first or we stop."""
        deadline = time.monotonic() + PIPE_OPEN_TIMEOUT
        while not self._stop.is_set():
            if pipe_exists(self.pipe_name):
                return True
            if dee.poll() is not None:
                return False
            if time.monotonic() > deadline:
                raise PipeError(
                    f"DEE did not open its pipe within {PIPE_OPEN_TIMEOUT:.0f} s."
                )
            time.sleep(0.01)
        return False

    def _end_dee(self) -> None:
        if self.dee and self.dee.poll() is None:
            self.killed_dee = True
            self.dee.kill()

    def stop(self) -> None:
        """After DEE has exited: let FFmpeg end, or end it."""
        self._stop.set()
        if not self._thread.is_alive():
            return
        self._thread.join(FFMPEG_EXIT_TIMEOUT)
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
        self._thread.join()

    def failure(self) -> PipeError:
        detail = "\n".join(f"  {line}" for line in self.tail)
        return PipeError(
            f"FFMPEG error (exit code {self.returncode}) while piping into DEE. "
            "Please re-run in debug mode." + (f"\n{detail}" if detail else "")
        )


def with_progress_report(cmd: list[str], keep_logs: bool = False) -> list[str]:
    """A planned FFmpeg command with its log level, reporting to stdout."""
    cmd = with_loglevel(cmd, keep_logs)
    at = cmd.index("-i")
    return [*cmd[:at], "-progress", "pipe:1", "-nostats", *cmd[at:]]


def process_pipe_job(
    dee_cmd: list[str],
    ffmpeg_cmd: list[str],
    pipe_name: str,
    step_info: dict | None = None,
    no_progress_bars: bool = False,
    custom_dialnorm: int = 0,
    log: ToolLog | None = None,
) -> int | None:
    """
    Run DEE reading the named pipe ``pipe_name``, and FFmpeg writing into it.

    Returns the bytes FFmpeg wrote into the pipe, or None if it didn't say.
    Raises DEE's error when DEE fails on its own, and FFmpeg's when FFmpeg
    fails, including when DEE then finished the short stream it was given.
    """
    feeder = _Feeder(
        with_progress_report(ffmpeg_cmd, keep_logs=log is not None), pipe_name, log
    )
    dee_error: Exception | None = None
    try:
        process_dee_job(
            dee_cmd,
            step_info=step_info,
            no_progress_bars=no_progress_bars,
            custom_dialnorm=custom_dialnorm,
            on_start=feeder.start,
            log=log,
        )
    except Exception as e:
        dee_error = e
    finally:
        feeder.stop()

    if feeder.error is not None:
        raise feeder.error from dee_error
    if dee_error is not None:
        if feeder.killed_dee:
            raise feeder.failure() from dee_error
        if feeder.returncode not in (None, 0):
            logger.debug(f"FFMPEG exited {feeder.returncode} after DEE failed.")
        raise dee_error
    if feeder.proc is None:
        raise PipeError("DEE finished without FFmpeg writing into its pipe.")
    if feeder.returncode != 0:
        raise feeder.failure()
    return feeder.written
