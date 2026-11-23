"""
Benchmark: FFmpeg piped into DEE vs FFmpeg to a temp WAV, then DEE.

Windows only (named pipes). Runs DeeZy's DD+ commands both ways on one source,
one job at a time and several at once, and prints the wall times.

    set DEEZY_DEE_DIR, DEEZY_FFMPEG (and DEEZY_DEE_LICENSE if DEE needs it)
    python scripts/bench_pipe.py SOURCE --parallel 1,4 --repeats 3

The WAV path is the one DeeZy runs today: FFmpeg writes a 32-bit RF64 WAV into
the job's temp folder, then dee_ddp_encoder reads it (--wav-pcm picks another
sample format). The pipe path starts DEE on a named pipe first, then FFmpeg
writes raw PCM into it (DEE's raw input takes s16le, s24le or f32le, not
s32le). Every job runs in its own folder under --work, which should be on the
disk DeeZy's temp folder uses.

Each pipe output is compared with the WAV output of the same settings; the
result is in the "same" column.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time

PIPE_DIR = "\\\\.\\pipe\\"


@dataclass(frozen=True)
class Tools:
    dee: Path
    ffmpeg: str
    license: Path | None

    @classmethod
    def from_env(cls) -> Tools:
        dee_dir = os.environ.get("DEEZY_DEE_DIR")
        ffmpeg = os.environ.get("DEEZY_FFMPEG") or shutil.which("ffmpeg")
        if not dee_dir or not ffmpeg:
            sys.exit("set DEEZY_DEE_DIR and DEEZY_FFMPEG (or put ffmpeg on PATH)")
        lic = os.environ.get("DEEZY_DEE_LICENSE")
        return cls(
            Path(dee_dir) / "dee_ddp_encoder.exe", ffmpeg, Path(lic) if lic else None
        )

    def dee_args(self) -> list[str]:
        lic = ["--license", str(self.license)] if self.license else []
        return [str(self.dee), "--loglevel", "info", "--progress", "1", *lic]


@dataclass(frozen=True)
class Settings:
    channels: int
    bitrate: int
    loudness: str
    pcm: str  # pipe sample format: s24le or f32le
    wav_pcm: str  # WAV sample format; DeeZy writes s32le

    def encode_args(self) -> list[str]:
        """DeeZy's DD+ options after the input, as --print-commands shows them."""
        layout = {1: "mono", 2: "stereo", 6: "5.1"}[self.channels]
        start = "0.005333" if self.channels == 6 else "0.006"
        return [
            "--timecode-frame-rate", "not_indicated", "--start", start,
            "--data-rate", str(self.bitrate), "--loudness-management", self.loudness,
            "-c", layout,
            "-e", "ddp:drc_profile_line=film_light:drc_profile_rf=film_light:"
            "lfe_filter=1:surround_90deg_phase_shift=1:surround_3dB_attenuation=1:"
            "preferred_downmix_mode=loro:loro_cmix=-3:loro_smix=-3:"
            "ltrt_cmix=-3:ltrt_smix=-3",
        ]  # fmt: skip


@dataclass
class JobTime:
    """Seconds from the job's start."""

    total: float
    ffmpeg: float  # FFmpeg done
    ready: float | None = None  # pipe path: DEE's pipe exists, FFmpeg starts

    def describe(self) -> str:
        if self.ready is None:
            return f"{self.total:.1f} (ffmpeg {self.ffmpeg:.1f})"
        return f"{self.total:.1f} (pipe {self.ready:.2f}, ffmpeg {self.ffmpeg:.1f})"


def ffmpeg_head(tools: Tools, source: Path) -> list[str]:
    return [
        tools.ffmpeg, "-y", "-drc_scale", "0", "-hide_banner", "-v", "error",
        "-i", str(source), "-map", "0:a:0", "-map_metadata", "-1",
    ]  # fmt: skip


def check(proc: subprocess.CompletedProcess | subprocess.Popen, what: str, log: str):
    if proc.returncode != 0:
        raise RuntimeError(f"{what} exited {proc.returncode}:\n{log[-2000:]}")


def run_wav(tools: Tools, source: Path, job_dir: Path, s: Settings) -> JobTime:
    wav = job_dir / "job.wav"
    out = job_dir / "out.ec3"
    t0 = time.perf_counter()
    ff = subprocess.run(  # noqa: S603
        [
            *ffmpeg_head(tools, source),
            "-c",
            f"pcm_{s.wav_pcm}",
            "-rf64",
            "always",
            str(wav),
        ],  # fmt: skip
        capture_output=True,
        text=True,
        errors="replace",
    )
    check(ff, "ffmpeg", ff.stderr)
    t1 = time.perf_counter()
    dee = subprocess.run(  # noqa: S603
        [
            *tools.dee_args(), "--overwrite", "1", "--temp-dir", str(job_dir),
            "--input-format", "wav", "-i", str(wav), "-o", str(out),
            *s.encode_args(),
        ],
        capture_output=True,
        text=True,
        errors="replace",
    )  # fmt: skip
    check(dee, "dee", dee.stdout + dee.stderr)
    return JobTime(total=time.perf_counter() - t0, ffmpeg=t1 - t0)


def wait_for_pipe(name: str, proc: subprocess.Popen, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if name in os.listdir(PIPE_DIR):
            return
        if proc.poll() is not None:
            log = proc.communicate()[0]
            raise RuntimeError(f"DEE exited before opening its pipe:\n{log}")
        time.sleep(0.01)
    raise RuntimeError(f"DEE did not create pipe {name}")


def run_pipe(
    tools: Tools, source: Path, job_dir: Path, s: Settings, name: str
) -> JobTime:
    out = job_dir / "out.ec3"
    pipe = PIPE_DIR + name
    fmt = f"pcm_{s.pcm}:sample_rate=48000:channels={s.channels}:streaming=1"
    t0 = time.perf_counter()
    dee = subprocess.Popen(  # noqa: S603
        [
            *tools.dee_args(), "--overwrite", "1", "--temp-dir", str(job_dir),
            "--input-format", fmt, "-i", "named_pipe://" + pipe, "-o", str(out),
            *s.encode_args(),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
    )  # fmt: skip
    # drain DEE's log while it runs, as DeeZy does for progress; a full
    # stdout pipe would stall DEE and FFmpeg behind it
    lines: list[str] = []
    reader = threading.Thread(target=lambda: lines.extend(dee.stdout), daemon=True)
    reader.start()
    try:
        wait_for_pipe(name, dee)
        t_ready = time.perf_counter()
        ff = subprocess.run(  # noqa: S603
            [*ffmpeg_head(tools, source), "-c", f"pcm_{s.pcm}", "-f", s.pcm, pipe],
            capture_output=True,
            text=True,
            errors="replace",
        )
        t_ff = time.perf_counter()
        dee.wait(timeout=7200)
    finally:
        if dee.poll() is None:
            dee.kill()
            dee.wait()
        reader.join()
    check(ff, "ffmpeg", ff.stderr)
    check(dee, "dee", "".join(lines))
    return JobTime(total=time.perf_counter() - t0, ffmpeg=t_ff - t0, ready=t_ready - t0)


def md5(path: Path) -> str:
    h = hashlib.md5()  # noqa: S324 - comparing outputs, not security
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def batch(
    tools: Tools,
    source: Path,
    work: Path,
    s: Settings,
    transport: str,
    parallel: int,
    tag: str,
) -> tuple[float, list[JobTime], list[str]]:
    """Run ``parallel`` identical jobs at once. Returns wall time, jobs, md5s."""
    dirs = []
    for j in range(parallel):
        d = work / f"{tag}-{j}"
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True)
        dirs.append(d)

    def one(j: int) -> JobTime:
        if transport == "wav":
            return run_wav(tools, source, dirs[j], s)
        return run_pipe(
            tools, source, dirs[j], s, f"deezy-bench-{os.getpid()}-{tag}-{j}"
        )

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=parallel) as pool:
        jobs = list(pool.map(one, range(parallel)))
    wall = time.perf_counter() - t0
    hashes = [md5(d / "out.ec3") for d in dirs]
    for d in dirs:
        shutil.rmtree(d, ignore_errors=True)
    return wall, jobs, hashes


def probe_channels(tools: Tools, source: Path) -> int:
    ffprobe = Path(tools.ffmpeg).with_name(
        "ffprobe" + (".exe" if tools.ffmpeg.lower().endswith(".exe") else "")
    )
    out = subprocess.run(  # noqa: S603
        [
            str(ffprobe), "-v", "error", "-select_streams", "a:0",
            "-show_entries", "stream=channels", "-of", "json", str(source),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout  # fmt: skip
    return int(json.loads(out)["streams"][0]["channels"])


def main() -> None:
    if sys.platform != "win32":
        sys.exit("this benchmark uses Windows named pipes")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("source", type=Path, help="audio source FFmpeg can read")
    ap.add_argument("--work", type=Path, default=Path(tempfile.gettempdir()))
    ap.add_argument("--parallel", default="1,4", help="comma list (default 1,4)")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument(
        "--loudness",
        action="append",
        help="DEE --loudness-management value; repeat for several "
        "(default: DeeZy's measure_only and skip:dialnorm=-27)",
    )
    ap.add_argument("--bitrate", type=int, default=448)
    ap.add_argument("--pcm", choices=["s24le", "f32le"], default="s24le")
    ap.add_argument("--wav-pcm", choices=["s32le", "s24le", "f32le"], default="s32le")
    ap.add_argument("--json", type=Path, help="also write the results here")
    args = ap.parse_args()

    tools = Tools.from_env()
    channels = probe_channels(tools, args.source)
    loudness = args.loudness or [
        "measure_only:preset=manual:dialogue_intelligence=1:speech_threshold=15",
        "skip:dialnorm=-27",
    ]
    parallels = [int(p) for p in args.parallel.split(",")]
    work = args.work / f"deezy-bench-{os.getpid()}"
    work.mkdir(parents=True, exist_ok=True)

    results = []
    try:
        for lm in loudness:
            s = Settings(channels, args.bitrate, lm, args.pcm, args.wav_pcm)
            for n in parallels:
                times: dict[str, list[float]] = {"wav": [], "pipe": []}
                hashes: set[str] = set()
                for r in range(args.repeats):
                    # alternate the order so drift doesn't favour one side
                    order = ("wav", "pipe") if r % 2 == 0 else ("pipe", "wav")
                    for transport in order:
                        wall, jobs, md5s = batch(
                            tools, args.source, work, s, transport, n, f"{transport}{n}"
                        )
                        times[transport].append(wall)
                        hashes.update(md5s)
                        print(
                            f"  {lm.split(':')[0]:<12} x{n} {transport:<4} "
                            f"run {r + 1}: {wall:7.1f} s  "
                            + ", ".join(j.describe() for j in jobs),
                            flush=True,
                        )
                results.append(
                    {
                        "loudness": lm,
                        "parallel": n,
                        "wav": times["wav"],
                        "pipe": times["pipe"],
                        "same_output": len(hashes) == 1,
                        "settings": asdict(s),
                    }
                )
    finally:
        shutil.rmtree(work, ignore_errors=True)

    print()
    print(f"WAV {args.wav_pcm}, pipe {args.pcm}, {channels} channels")
    print(f"{'loudness':<14}{'jobs':>5}{'wav s':>9}{'pipe s':>9}{'pipe/wav':>10}  same")
    for res in results:
        w = statistics.median(res["wav"])
        p = statistics.median(res["pipe"])
        print(
            f"{res['loudness'].split(':')[0]:<14}{res['parallel']:>5}"
            f"{w:>9.1f}{p:>9.1f}{p / w:>10.2f}  {'yes' if res['same_output'] else 'NO'}"
        )
    print("(medians of the batch wall time)")
    if args.json:
        args.json.write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
