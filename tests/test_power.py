import argparse
import subprocess

import pytest

import deezy.cli as cli
from deezy.utils import power


class FakeSetter:
    def __init__(self, result: int = 1) -> None:
        self.result = result
        self.calls: list[int] = []
        self.argtypes = None
        self.restype = None

    def __call__(self, flags: int) -> int:
        self.calls.append(flags)
        return self.result


class FakeProcess:
    def __init__(self, returncode: int | None = None) -> None:
        self.returncode = returncode
        self.pid = 1234
        self.terminated = False
        self.killed = False
        self.wait_timeouts: list[int] = []

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = 0

    def kill(self) -> None:
        self.killed = True
        self.returncode = -1

    def wait(self, timeout: int) -> int:
        self.wait_timeouts.append(timeout)
        return self.returncode or 0


def test_windows_inhibitor_sets_and_restores_execution_state(monkeypatch):
    setter = FakeSetter()
    kernel32 = type("Kernel32", (), {"SetThreadExecutionState": setter})()
    monkeypatch.setattr(power.platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        power.ctypes,
        "WinDLL",
        lambda *_args, **_kwargs: kernel32,
        raising=False,
    )

    inhibitor = power.SleepInhibitor()
    assert inhibitor.acquire() is True
    assert inhibitor.active is True

    inhibitor.release()

    assert setter.calls == [
        power._ES_CONTINUOUS | power._ES_SYSTEM_REQUIRED,
        power._ES_CONTINUOUS,
    ]
    assert inhibitor.active is False


@pytest.mark.parametrize(
    ("system", "paths", "expected"),
    [
        (
            "Darwin",
            {"caffeinate": "/usr/bin/caffeinate"},
            ["/usr/bin/caffeinate", "-i", "-w"],
        ),
        (
            "Linux",
            {
                "systemd-inhibit": "/usr/bin/systemd-inhibit",
                "sleep": "/usr/bin/sleep",
            },
            [
                "/usr/bin/systemd-inhibit",
                "--what=sleep",
                "--who=DeeZy",
                "--why=Audio encoding in progress",
                "--mode=block",
                "/usr/bin/sleep",
                "infinity",
            ],
        ),
    ],
)
def test_command_inhibitors_are_started_and_stopped(
    monkeypatch, system, paths, expected
):
    process = FakeProcess()
    popen_calls = []
    monkeypatch.setattr(power.platform, "system", lambda: system)
    monkeypatch.setattr(power.shutil, "which", paths.get)

    def fake_popen(command, **kwargs):
        popen_calls.append((command, kwargs))
        return process

    monkeypatch.setattr(power.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(power.os, "getpid", lambda: 99)
    monkeypatch.setattr(
        power.os,
        "killpg",
        lambda _pid, _signal: process.terminate(),
        raising=False,
    )

    inhibitor = power.SleepInhibitor()
    assert inhibitor.acquire() is True
    inhibitor.release()

    command, kwargs = popen_calls[0]
    if system == "Darwin":
        assert command[:3] == expected
        assert command[3] == "99"
        assert process.terminated is True
    else:
        assert command == expected
        assert kwargs["start_new_session"] is True
        assert process.terminated is True
    assert kwargs["stdout"] is subprocess.DEVNULL
    assert inhibitor.active is False


def test_missing_platform_support_is_fail_open(monkeypatch):
    monkeypatch.setattr(power.platform, "system", lambda: "Linux")
    monkeypatch.setattr(power.shutil, "which", lambda _name: None)

    inhibitor = power.SleepInhibitor()

    assert inhibitor.acquire() is False
    assert inhibitor.active is False


def test_context_manager_releases_after_exception(monkeypatch):
    inhibitor = power.SleepInhibitor()
    monkeypatch.setattr(inhibitor, "_acquire_windows", lambda: None)
    monkeypatch.setattr(power.platform, "system", lambda: "Windows")
    released = []
    inhibitor._windows_setter = lambda _flags: released.append(True) or 1  # type: ignore[reportAttributeAccessIssue]

    with pytest.raises(RuntimeError):
        with inhibitor:
            raise RuntimeError("encode failed")

    assert released == [True]
    assert inhibitor.active is False


def test_allow_sleep_cli_flag_is_available():
    parser = cli.create_common_argument_groups()["encode_group"]

    args = parser.parse_args(["--allow-sleep"])

    assert args.allow_sleep is True


@pytest.mark.parametrize(
    ("allow_sleep", "expected_events"),
    [(False, ["acquire", "release"]), (True, ["release"])],
)
def test_encode_lifecycle_controls_inhibitor(
    tmp_path, monkeypatch, allow_sleep, expected_events
):
    events = []

    class FakeInhibitor:
        def acquire(self):
            events.append("acquire")

        def release(self):
            events.append("release")

    args = argparse.Namespace(
        allow_sleep=allow_sleep,
        batch_output_dir=None,
        batch_summary_output=False,
        jitter_ms=0,
        max_batch_results=None,
        max_logs=None,
        max_parallel=1,
        output_preview=False,
        working_dir=str(tmp_path),
    )
    input_file = tmp_path / "input.wav"
    output_file = tmp_path / "output.ec3"
    monkeypatch.setattr(cli, "SleepInhibitor", FakeInhibitor)
    monkeypatch.setattr(
        cli, "encode_single_file", lambda *_args: (input_file, output_file)
    )

    cli.execute_encode_command(args, [input_file], {}, None)

    assert events == expected_events
