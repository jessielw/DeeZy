import logging
import subprocess
import threading
from pathlib import Path

from deezy.enums.atmos import WarpMode
from deezy.enums.shared import TrackType
from deezy.track_info.track_index import TrackIndex
from deezy.utils.logger import logger
from deezy.utils.progress import ProgressHandler, create_ffmpeg_parser

BASE_ATMOS_FILE_NAME = "atmos_meta"


def decode_truehd_to_atmos(
    output_dir: Path,
    file_input: Path,
    track_index: TrackIndex,
    ffmpeg_path: Path,
    truehdd_path: Path,
    bed_conform: bool,
    warp_mode: WarpMode,
    duration: float | None = None,
    step_info: dict | None = None,
    no_progress_bars: bool = False,
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
        "-hide_banner",
        "-y",
        "-i",
        str(file_input),
        "-map",
        f"0:a:{track_index.index}"
        if track_index.track_type is TrackType.AUDIO
        else f"0:{track_index.index}",
        "-c",
        "copy",
        "-f",
        "truehd",
        "-",
        "-v",
        "-stats",
    ]

    # inject verbosity level into cmd list depending on logging level
    logger_level = logger.getEffectiveLevel()
    inject = ffmpeg_cmd.index("-v") + 1
    if logger_level == logging.DEBUG:
        ffmpeg_cmd.insert(inject, "warning")  # even in debug, suppress file info spam
    else:
        ffmpeg_cmd.insert(inject, "quiet")

    truehdd_cmd = [
        str(truehdd_path),
        "--progress",
        "decode",
        "--output-path",
        str(output_dir / BASE_ATMOS_FILE_NAME),
        "--warp-mode",
        warp_mode.to_truehdd_cmd(),
        "--bed-conform",
        "-",
    ]
    # remove bed conform if desired
    if not bed_conform:
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

    ffmpeg_err_lines: list[str] = []
    truehdd_err_lines: list[str] = []
    truehdd_out_lines: list[str] = []

    # setup progress handler
    progress_handler = ProgressHandler(logger_level, no_progress_bars, step_info)
    step_label = progress_handler.get_step_label(
        "TrueHD extract & decode", default_current=1, default_total=2
    )
    ffmpeg_parser = create_ffmpeg_parser(duration) if duration else None

    def _stream_reader(
        prefix: str,
        stream,
        sink: list[str],
        progress=None,
        task_id=None,
    ):
        try:
            last_percent = 0.0
            for line in iter(stream.readline, ""):
                line = line.rstrip("\r\n")
                if not line:
                    continue

                # handle ffmpeg progress lines
                if prefix == "ffmpeg" and ffmpeg_parser and duration:
                    if (
                        "Application provided invalid, non monotonically increasing dts"
                        in line
                    ):
                        continue
                    percent_data = ffmpeg_parser(line)
                    if percent_data:
                        last_percent = percent_data.value
                        if progress and task_id is not None:
                            progress.update(task_id, completed=percent_data.value)
                            logger.debug(f"{step_label} {percent_data.formatted}")
                        else:
                            logger.info(f"{step_label} {percent_data.formatted}")
                            logger.debug(f"{step_label} {percent_data.formatted}")
                        sink.append(percent_data.formatted)
                        continue

                # filter out ffmpeg metadata spam even in debug mode
                if prefix == "ffmpeg":
                    # suppress common metadata lines that clutter output
                    if any(
                        keyword in line
                        for keyword in [
                            "Input #",
                            "Metadata:",
                            "Duration:",
                            "Stream #",
                            "  ",
                            "Output #",
                            "Stream mapping:",
                            "Press [q]",
                            "configuration:",
                            "built with",
                            "libav",
                            "encoder",
                        ]
                    ):
                        continue
                    # only log important ffmpeg lines (errors, warnings)
                    if any(
                        keyword in line
                        for keyword in [
                            "error",
                            "Error",
                            "ERROR",
                            "warning",
                            "Warning",
                            "WARNING",
                        ]
                    ):
                        logger.debug(f"[{prefix}] {line}")
                        sink.append(line)
                        continue

                # default debug logging for non-ffmpeg streams
                if logger_level == logging.DEBUG and prefix != "ffmpeg":
                    logger.debug(f"[{prefix}] {line}")
                    sink.append(line)

            # ensure 100% completion
            if prefix == "ffmpeg" and last_percent < 100.0 and duration:
                if progress and task_id is not None:
                    progress.update(task_id, completed=100)
                    progress.refresh()
                else:
                    logger.info(f"{step_label} 100.0%")
                    logger.debug(f"{step_label} 100.0%")

        finally:
            try:
                stream.close()
            except Exception:
                pass

    # run with or without progress bars
    with progress_handler.progress_context(step_label) as (progress, task_id):
        threads = (
            threading.Thread(
                target=_stream_reader,
                args=(
                    "ffmpeg",
                    ffmpeg_proc.stderr,
                    ffmpeg_err_lines,
                    progress,
                    task_id,
                ),
                daemon=True,
            ),
            threading.Thread(
                target=_stream_reader,
                args=(
                    "truehdd-err",
                    truehdd_proc.stderr,
                    truehdd_err_lines,
                    None,
                    None,
                ),
                daemon=True,
            ),
            threading.Thread(
                target=_stream_reader,
                args=(
                    "truehdd-out",
                    truehdd_proc.stdout,
                    truehdd_out_lines,
                    None,
                    None,
                ),
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
