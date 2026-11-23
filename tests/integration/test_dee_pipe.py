"""Streaming PCM from ffmpeg into DEE through a Windows named pipe."""

import os
import subprocess
import sys
import time

import pytest

from .harness import md5, noise_wav

pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="named pipes are Windows-only; POSIX stdin is Phase 3",
)

CHANNELS = 6
SECONDS = 3.0
PCM_BYTES = int(48000 * SECONDS) * CHANNELS * 3


def wait_for_pipe(name: str, proc: subprocess.Popen, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if name in os.listdir("\\\\.\\pipe\\"):
            return
        assert proc.poll() is None, proc.communicate()[0]
        time.sleep(0.05)
    raise AssertionError(f"DEE did not create pipe {name}")


@pytest.mark.parametrize(
    ("loudness", "buffers_pcm"),
    [("measure_only", True), ("skip:dialnorm=-31", False)],
)
def test_pipe_output_matches_wav(tools, work, loudness, buffers_pcm):
    wav = noise_wav(work / "pipe_src.wav", CHANNELS, seconds=SECONDS)
    tag = "measure" if buffers_pcm else "skip"
    ref = work / f"pipe_ref_{tag}.ec3"
    common = ["-e", "ddp", "--loudness-management", loudness]
    result = tools.dee(
        "dee_ddp_encoder", "--input-format", "wav", "-i", wav, "-o", ref, *common
    )
    assert result.ok, result.error()

    temp = work / f"pipe_temp_{tag}"
    temp.mkdir(exist_ok=True)
    out = work / f"pipe_out_{tag}.ec3"
    name = f"deezy-test-{os.getpid()}-{tag}"
    pipe = "\\\\.\\pipe\\" + name
    fmt = f"pcm_s24le:sample_rate=48000:channels={CHANNELS}:streaming=1"
    dee = subprocess.Popen(  # noqa: S603
        [
            str(tools.tool("dee_ddp_encoder")), *map(str, tools.license_args()),
            "--overwrite", "1", "--input-format", fmt, "-i", "named_pipe://" + pipe,
            "-o", str(out), *common, "--temp-dir", str(temp), "--keep-temp", "1",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
    )  # fmt: skip
    try:
        wait_for_pipe(name, dee)
        ffmpeg = subprocess.run(  # noqa: S603
            [
                tools.ffmpeg, "-hide_banner", "-v", "error", "-y", "-i", str(wav),
                "-c:a", "pcm_s24le", "-f", "s24le", pipe,
            ],
            capture_output=True,
            text=True,
        )  # fmt: skip
        log, _ = dee.communicate(timeout=120)
    finally:
        if dee.poll() is None:
            dee.kill()
    assert ffmpeg.returncode == 0, ffmpeg.stderr
    assert dee.returncode == 0, log
    assert md5(out) == md5(ref)

    buffered = [
        p for p in temp.rglob("*") if p.is_file() and p.stat().st_size == PCM_BYTES
    ]
    assert bool(buffered) is buffers_pcm
