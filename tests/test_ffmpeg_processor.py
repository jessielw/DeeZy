import sys

import pytest

from deezy.audio_processors.ffmpeg import (
    MAX_CAPTURED_LINES,
    _capture,
    process_ffmpeg_job,
)

# stands in for ffmpeg: ignores its arguments, writes the given lines, exits with
# the given code
FAKE_FFMPEG = (
    "import sys;"
    "n=int(sys.argv[-2]);code=int(sys.argv[-1]);"
    "[print(f'line {i}') for i in range(n)];"
    "sys.exit(code)"
)


def fake_ffmpeg_cmd(lines: int, exit_code: int) -> list:
    # -v and -i are the anchors the command builder injects around
    return [
        sys.executable,
        "-c",
        FAKE_FFMPEG,
        "-v",
        "-i",
        "input",
        str(lines),
        str(exit_code),
    ]


def test_capture_keeps_bounded_tail():
    sink = []
    for i in range(MAX_CAPTURED_LINES + 25):
        _capture(sink, f"line {i}")

    assert len(sink) == MAX_CAPTURED_LINES
    assert sink[-1] == f"line {MAX_CAPTURED_LINES + 24}"


def test_capture_skips_blank_lines():
    sink = []
    _capture(sink, "")
    assert sink == []


def test_success_returns_true():
    assert process_ffmpeg_job(
        fake_ffmpeg_cmd(3, 0), steps=False, duration=None, no_progress_bars=True
    )


def test_failure_reports_output_not_just_exit_code():
    """A failing FFMPEG has to say why without a debug re-run."""
    with pytest.raises(ValueError) as exc:
        process_ffmpeg_job(
            fake_ffmpeg_cmd(3, 2), steps=False, duration=None, no_progress_bars=True
        )

    message = str(exc.value)
    assert "exit code 2" in message
    assert "line 2" in message


def test_failure_detail_is_bounded():
    with pytest.raises(ValueError) as exc:
        process_ffmpeg_job(
            fake_ffmpeg_cmd(MAX_CAPTURED_LINES + 50, 1),
            steps=False,
            duration=None,
            no_progress_bars=True,
        )

    message = str(exc.value)
    # only the tail survives, and the first line is long gone
    assert message.count("line ") == MAX_CAPTURED_LINES
    assert "line 0\n" not in message
