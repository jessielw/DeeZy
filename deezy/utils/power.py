"""Best-effort system sleep inhibition during long-running encodes."""

import ctypes
import os
import platform
import shutil
import signal
import subprocess
from types import TracebackType

from deezy.utils.logger import logger

_ES_SYSTEM_REQUIRED = 0x00000001
_ES_CONTINUOUS = 0x80000000
_INHIBIT_REASON = "Audio encoding in progress"


class SleepInhibitor:
    """Keep the system awake until released, without keeping the display on.

    Acquisition and release are deliberately fail-open: power-management support
    must never prevent an encode from running or completing.
    """

    def __init__(self) -> None:
        self._active = False
        self._process: subprocess.Popen[bytes] | None = None
        self._owns_process_group = False
        self._windows_setter = None

    @property
    def active(self) -> bool:
        """Whether an inhibitor was successfully acquired."""
        return self._active

    def acquire(self) -> bool:
        """Acquire the platform sleep inhibitor and return whether it succeeded."""
        if self._active:
            return True

        system = platform.system()
        try:
            if system == "Windows":
                self._acquire_windows()
            elif system == "Darwin":
                self._acquire_macos()
            elif system == "Linux":
                self._acquire_linux()
            else:
                raise RuntimeError(f"unsupported platform: {system or 'unknown'}")
        except Exception as exc:
            logger.warning(
                f"Could not prevent system sleep; encoding will continue: {exc}"
            )
            return False

        self._active = True
        logger.debug("System sleep inhibited while encoding.")
        return True

    def release(self) -> None:
        """Release the inhibitor if one is active."""
        if not self._active:
            return

        try:
            if self._windows_setter is not None:
                if not self._windows_setter(_ES_CONTINUOUS):
                    raise OSError(
                        "SetThreadExecutionState failed while restoring sleep"
                    )
            elif self._process is not None:
                self._stop_process()
        except Exception as exc:
            logger.warning(f"Could not restore normal system sleep behavior: {exc}")
        finally:
            self._active = False
            self._process = None
            self._windows_setter = None
            self._owns_process_group = False

    def _acquire_windows(self) -> None:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        setter = kernel32.SetThreadExecutionState
        setter.argtypes = [ctypes.c_uint]
        setter.restype = ctypes.c_uint

        if not setter(_ES_CONTINUOUS | _ES_SYSTEM_REQUIRED):
            error_code = ctypes.get_last_error()
            raise OSError(error_code, "SetThreadExecutionState failed")
        self._windows_setter = setter

    def _acquire_macos(self) -> None:
        caffeinate = shutil.which("caffeinate")
        if caffeinate is None:
            raise RuntimeError("caffeinate is unavailable")

        self._start_process([caffeinate, "-i", "-w", str(os.getpid())])

    def _acquire_linux(self) -> None:
        systemd_inhibit = shutil.which("systemd-inhibit")
        sleep = shutil.which("sleep")
        if systemd_inhibit is None or sleep is None:
            raise RuntimeError("systemd-inhibit is unavailable")

        self._start_process(
            [
                systemd_inhibit,
                "--what=sleep",
                "--who=DeeZy",
                f"--why={_INHIBIT_REASON}",
                "--mode=block",
                sleep,
                "infinity",
            ],
            owns_process_group=True,
        )

    def _start_process(
        self, command: list[str], *, owns_process_group: bool = False
    ) -> None:
        process = subprocess.Popen(  # noqa: S603
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=owns_process_group,
        )
        if process.poll() is not None:
            raise RuntimeError("the platform sleep inhibitor exited unexpectedly")

        self._process = process
        self._owns_process_group = owns_process_group

    def _stop_process(self) -> None:
        process = self._process
        if process is None or process.poll() is not None:
            return

        if self._owns_process_group and hasattr(os, "killpg"):
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except OSError:
                process.terminate()
        else:
            process.terminate()

        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            if self._owns_process_group and hasattr(os, "killpg"):
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except OSError:
                    process.kill()
            else:
                process.kill()
            process.wait(timeout=2)

    def __enter__(self) -> "SleepInhibitor":
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.release()
