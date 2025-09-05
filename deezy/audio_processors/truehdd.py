from pathlib import Path
import subprocess
import threading

from deezy.audio_processors.ffmpeg import convert_ffmpeg_to_percent
from deezy.enums.shared import ProgressMode
from deezy.utils.utils import PrintSameLine

BASE_ATMOS_FILE_NAME = "atmos_meta"


def decode_truehd_to_atmos(
    output_dir: Path,
    file_input: Path,
    track_index: int,
    ffmpeg_path: Path,
    truehdd_path: Path,
    progress_mode: ProgressMode,
    no_bed_conform: bool = False,
    duration: float | None = None,
) -> Path:
    """
    Extract the TrueHD track and run truehdd decode to produce .atmos files.

    If use_pipe is False (default) this writes a temporary .thd file and calls:
        ffmpeg -i input -map 0:a:<track_index> -c copy <base>.thd
        truehdd decode --output <base> <base>.thd

    If use_pipe is True it pipes ffmpeg stdout into truehdd stdin:
        ffmpeg -i input -map 0:a:<track_index> -c copy -f truehd -
        truehdd decode --output <base> -

    Returns list of paths to the generated .atmos files (raises on failure).
    """
    # pipe mode: stream TrueHD from ffmpeg to truehdd stdin
    ffmpeg_cmd = [
        str(ffmpeg_path),
        "-y",
        "-i",
        str(file_input),
        "-map",
        f"0:a:{track_index}",
        "-c",
        "copy",
        "-f",
        "truehd",
        "-",
        "-hide_banner",
        "-v",
        "-stats",
    ]

    # inject verbosity level into cmd list depending on progress_mode
    inject = ffmpeg_cmd.index("-v") + 1
    if progress_mode is ProgressMode.STANDARD:
        ffmpeg_cmd.insert(inject, "quiet")
    elif progress_mode is ProgressMode.DEBUG:
        ffmpeg_cmd.insert(inject, "info")

    truehdd_cmd = [
        str(truehdd_path),
        "--progress",
        "decode",
        "--output-path",
        str(output_dir / BASE_ATMOS_FILE_NAME),
        "--bed-conform",
        "-",
    ]
    # remove bed conform if desired
    if no_bed_conform:
        truehdd_cmd.remove("--bed-conform")

    ffmpeg_proc = subprocess.Popen(
        ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    try:
        truehdd_proc = subprocess.Popen(
            truehdd_cmd,
            stdin=ffmpeg_proc.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    finally:
        if ffmpeg_proc.stdout:
            ffmpeg_proc.stdout.close()

    # helpers
    print_same_line = PrintSameLine()

    ffmpeg_err_lines: list[str] = []
    truehdd_err_lines: list[str] = []
    truehdd_out_lines: list[str] = []

    def _stream_reader(prefix: str, stream, sink: list[str]):
        try:
            for line in iter(stream.readline, ""):
                line = line.rstrip("\r\n")
                if not line:
                    continue

                # special handling for ffmpeg progress lines
                if prefix == "ffmpeg":
                    # try to convert to percentage when duration provided
                    if duration:
                        percent = convert_ffmpeg_to_percent(line, duration)
                        if percent:
                            # print on same line like ffmpeg.py does
                            print_same_line.print_msg(percent)
                            sink.append(percent)
                            # don't print raw ffmpeg line
                            continue

                # default printing
                if progress_mode is ProgressMode.DEBUG:
                    print(f"[{prefix}] {line}")
                    sink.append(line)
        finally:
            try:
                stream.close()
            except Exception:
                pass

    threads = (
        threading.Thread(
            target=_stream_reader,
            args=("ffmpeg", ffmpeg_proc.stderr, ffmpeg_err_lines),
            daemon=True,
        ),
        threading.Thread(
            target=_stream_reader,
            args=("truehdd-err", truehdd_proc.stderr, truehdd_err_lines),
            daemon=True,
        ),
        threading.Thread(
            target=_stream_reader,
            args=("truehdd-out", truehdd_proc.stdout, truehdd_out_lines),
            daemon=True,
        ),
    )

    for t in threads:
        t.start()

    truehdd_return = truehdd_proc.wait()
    ffmpeg_return = ffmpeg_proc.wait()

    for t in threads:
        t.join(timeout=0.1)

    ffmpeg_err = "\n".join(ffmpeg_err_lines)
    truehdd_err = "\n".join(truehdd_err_lines)
    truehdd_out = "\n".join(truehdd_out_lines)

    if ffmpeg_return != 0:
        raise RuntimeError(
            f"ffmpeg (pipe) failed extracting TrueHD: {ffmpeg_err.strip()}"
        )

    if truehdd_return != 0:
        raise RuntimeError(
            f"truehdd decode (pipe) failed: {(truehdd_err or truehdd_out).strip()}"
        )

    # find generated atmos file (dee will get all 3 we only need to pass the main atmos file)
    main_atmos_file = output_dir / f"{BASE_ATMOS_FILE_NAME}.atmos"
    if not main_atmos_file.exists():
        raise FileNotFoundError(
            f"Failed to locate atmos file after generation: {main_atmos_file}"
        )

    return main_atmos_file
