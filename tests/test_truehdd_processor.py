import io
from pathlib import Path

import pytest

from deezy.audio_processors import truehdd as truehdd_mod
from deezy.enums.atmos import WarpMode
from deezy.track_info.track_index import TrackIndex


class FakeProc:
    """Stands in for a Popen: canned stream content and a fixed exit code."""

    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0):
        self.stdout = io.StringIO(stdout)
        self.stderr = io.StringIO(stderr)
        self.returncode = returncode
        self.killed = False
        self.waited = False

    def wait(self):
        self.waited = True
        return self.returncode

    def kill(self):
        self.killed = True


def run_decode(tmp_path, output_dir=None):
    return truehdd_mod.decode_truehd_to_atmos(
        output_dir=output_dir or tmp_path,
        file_input=tmp_path / "in.mkv",
        track_index=TrackIndex.audio(0),
        ffmpeg_path=Path("ffmpeg"),
        truehdd_path=Path("truehdd"),
        warp_mode=WarpMode.NORMAL,
        no_progress_bars=True,
    )


@pytest.fixture
def patch_popen(monkeypatch):
    """Swap in fake processes; returns a setter taking (ffmpeg, truehdd)."""

    def install(ffmpeg_proc, truehdd_proc):
        procs = iter((ffmpeg_proc, truehdd_proc))

        def fake_popen(*_args, **_kwargs):
            proc = next(procs)
            if isinstance(proc, BaseException):
                raise proc
            return proc

        monkeypatch.setattr(truehdd_mod.subprocess, "Popen", fake_popen)

    return install


def test_truehdd_failure_reports_stderr_without_debug(tmp_path, patch_popen):
    """The decoder's own complaint has to reach the raised error."""
    ffmpeg_proc = FakeProc()
    truehdd_proc = FakeProc(stderr="ERROR: unsupported bitstream\n", returncode=3)
    patch_popen(ffmpeg_proc, truehdd_proc)

    with pytest.raises(RuntimeError) as exc:
        run_decode(tmp_path)

    assert "unsupported bitstream" in str(exc.value)


def test_truehdd_failure_falls_back_to_stdout(tmp_path, patch_popen):
    ffmpeg_proc = FakeProc()
    truehdd_proc = FakeProc(stdout="decode aborted\n", returncode=1)
    patch_popen(ffmpeg_proc, truehdd_proc)

    with pytest.raises(RuntimeError) as exc:
        run_decode(tmp_path)

    assert "decode aborted" in str(exc.value)


def test_ffmpeg_failure_is_reported_when_truehdd_succeeds(tmp_path, patch_popen):
    ffmpeg_proc = FakeProc(stderr="Error opening input file\n", returncode=1)
    truehdd_proc = FakeProc(returncode=0)
    patch_popen(ffmpeg_proc, truehdd_proc)

    with pytest.raises(RuntimeError) as exc:
        run_decode(tmp_path)

    assert "Error opening input file" in str(exc.value)


def test_a_broken_pipe_does_not_hide_the_truehdd_error(tmp_path, patch_popen):
    ffmpeg_proc = FakeProc(stderr="Broken pipe\n", returncode=1)
    truehdd_proc = FakeProc(stderr="Unsupported bitstream\n", returncode=3)
    patch_popen(ffmpeg_proc, truehdd_proc)

    with pytest.raises(RuntimeError) as exc:
        run_decode(tmp_path)

    message = str(exc.value)
    assert "FFmpeg failed extracting TrueHD (exit code 1)" in message
    assert "Broken pipe" in message
    assert "truehdd failed decoding TrueHD (exit code 3)" in message
    assert "Unsupported bitstream" in message


def test_captured_output_is_bounded(tmp_path, patch_popen):
    noisy = "".join(f"warn {i}\n" for i in range(truehdd_mod.MAX_CAPTURED_LINES + 40))
    patch_popen(FakeProc(), FakeProc(stderr=noisy, returncode=1))

    with pytest.raises(RuntimeError) as exc:
        run_decode(tmp_path)

    message = str(exc.value)
    assert message.count("warn ") == truehdd_mod.MAX_CAPTURED_LINES
    assert "warn 0\n" not in message


def test_ffmpeg_is_not_orphaned_when_truehdd_cannot_start(tmp_path, patch_popen):
    """truehdd never launching must not leave ffmpeg running on the input."""
    ffmpeg_proc = FakeProc()
    patch_popen(ffmpeg_proc, FileNotFoundError("truehdd not found"))

    with pytest.raises(FileNotFoundError):
        run_decode(tmp_path)

    assert ffmpeg_proc.killed
    assert ffmpeg_proc.waited


def test_missing_atmos_file_is_reported(tmp_path, patch_popen):
    patch_popen(FakeProc(), FakeProc(returncode=0))

    with pytest.raises(FileNotFoundError) as exc:
        run_decode(tmp_path)

    assert truehdd_mod.BASE_ATMOS_FILE_NAME in str(exc.value)


def test_successful_decode_returns_atmos_path(tmp_path, patch_popen):
    (tmp_path / f"{truehdd_mod.BASE_ATMOS_FILE_NAME}.atmos").touch()
    patch_popen(FakeProc(), FakeProc(returncode=0))

    result = run_decode(tmp_path)
    assert result == tmp_path / f"{truehdd_mod.BASE_ATMOS_FILE_NAME}.atmos"


def test_no_warp_mode_is_passed_by_default(tmp_path):
    """A stream with no warp mode keeps none, which DEE renders as warping."""
    cmd = truehdd_mod.truehdd_command(Path("truehdd"), tmp_path, None)
    assert "--warp-mode" not in cmd
    assert cmd[-1] == "-"


@pytest.mark.parametrize(
    ("warp", "name"),
    [
        (WarpMode.NORMAL, "normal"),
        (WarpMode.DPLII, "prologiciix"),
        (WarpMode.LORO, "loro"),
    ],
)
def test_a_chosen_warp_mode_is_passed(tmp_path, warp, name):
    cmd = truehdd_mod.truehdd_command(Path("truehdd"), tmp_path, warp)
    assert cmd[cmd.index("--warp-mode") + 1] == name


def test_damf_warp_mode_reads_the_header(tmp_path):
    damf = tmp_path / "m.atmos"
    damf.write_text("presentations:\n  - type: home\n    warpMode: ProLogicIIx\n")
    assert truehdd_mod.damf_warp_mode(damf) == "ProLogicIIx"
    damf.write_text("presentations:\n  - type: home\n")
    assert truehdd_mod.damf_warp_mode(damf) is None
    assert truehdd_mod.damf_warp_mode(tmp_path / "missing.atmos") is None


def test_bed_conform_is_never_passed(tmp_path):
    """It changes no DEE output, and costs disk space and time."""
    cmd = truehdd_mod.truehdd_command(Path("truehdd"), tmp_path, WarpMode.NORMAL)
    assert "--bed-conform" not in cmd
