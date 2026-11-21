"""Helpers for the DEE 6.7 integration tests.

These tests run the real Dolby Encoding Engine tools. They are skipped unless
DEEZY_DEE_DIR names the folder that holds them. Optional variables:

    DEEZY_DEE_LICENSE   license file (default: DEE looks next to the tools)
    DEEZY_FFMPEG        ffmpeg executable (default: ffmpeg on PATH)
    DEEZY_TRUEHDD       truehdd executable, for the Atmos tests
    DEEZY_SHIM          dee_shim executable, for the dee_shim tests
    DEEZY_ATMOS_SAMPLE  a TrueHD Atmos stream, raw or in a container ffmpeg reads
"""

from __future__ import annotations

from array import array
from dataclasses import dataclass
import hashlib
import math
from operator import mul
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
from typing import Literal
import wave

SR = 48000
EXE = ".exe" if sys.platform == "win32" else ""
AC3_SUFFIXES = {".ac3", ".ec3", ".eb3"}


@dataclass(frozen=True)
class Run:
    cmd: list[str]
    rc: int
    out: str

    @property
    def ok(self) -> bool:
        return self.rc == 0

    def error(self) -> str:
        """The first ERROR line of a DEE log, or the end of the output."""
        for line in self.out.splitlines():
            if "ERROR" in line:
                return line.strip()
        return self.out.strip()[-600:]


def run(cmd: list, cwd: Path | None = None, timeout: int = 1800) -> Run:
    args = [str(c) for c in cmd]
    proc = subprocess.run(  # noqa: S603
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=timeout,
    )
    return Run(args, proc.returncode, (proc.stdout or "") + (proc.stderr or ""))


@dataclass(frozen=True)
class Tools:
    dee_dir: Path
    license: Path | None
    ffmpeg: str
    truehdd: str | None
    shim: str | None
    atmos_sample: Path | None

    @classmethod
    def from_env(cls) -> Tools | None:
        dee_dir = os.environ.get("DEEZY_DEE_DIR")
        ffmpeg = os.environ.get("DEEZY_FFMPEG") or shutil.which("ffmpeg")
        if not dee_dir or not ffmpeg:
            return None
        lic = os.environ.get("DEEZY_DEE_LICENSE")
        sample = os.environ.get("DEEZY_ATMOS_SAMPLE")
        return cls(
            dee_dir=Path(dee_dir),
            license=Path(lic) if lic else None,
            ffmpeg=ffmpeg,
            truehdd=os.environ.get("DEEZY_TRUEHDD") or shutil.which("truehdd"),
            shim=os.environ.get("DEEZY_SHIM") or shutil.which("dee_shim"),
            atmos_sample=Path(sample) if sample else None,
        )

    def tool(self, name: str) -> Path:
        return self.dee_dir / f"{name}{EXE}"

    def license_args(self) -> list:
        return ["--license", self.license] if self.license else []

    def dee(self, name: str, *args, cwd: Path | None = None) -> Run:
        """Run one DEE tool with the license and --overwrite 1."""
        return run(
            [self.tool(name), *self.license_args(), "--overwrite", "1", *args], cwd=cwd
        )

    def help(self, name: str, topic: str | None = None) -> str:
        args = ["--morehelp", topic] if topic else ["--help"]
        return run([self.tool(name), *args]).out

    def run_shim(
        self, sub: str, shim_args: list, dee_args: list, cwd: Path | None = None
    ) -> Run:
        """Run dee_shim with DEE's own arguments after `--`."""
        assert self.shim, "dee_shim not found"
        cmd = [self.shim, sub, *shim_args, "--binary", self.tool(f"dee_{sub}"), "--"]
        cmd += [*self.license_args(), "--overwrite", "1", *dee_args]
        env_free = {k: v for k, v in os.environ.items() if not _shim_env(k)}
        args = [str(c) for c in cmd]
        proc = subprocess.run(  # noqa: S603
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            errors="replace",
            env=env_free,
        )
        return Run(args, proc.returncode, (proc.stdout or "") + (proc.stderr or ""))


def _shim_env(key: str) -> bool:
    return key.startswith(("DSHIM_", "DEE_SHIM_")) or key == "RUST_LOG"


# --- WAV input -----------------------------------------------------------------


def write_wav(
    path: Path,
    channels: int,
    hits: dict[tuple[int, int], float],
    seconds: float = 3.0,
    bits: int = 24,
    rate: int = SR,
) -> Path:
    """A silent PCM WAV with single-sample hits, given as {(frame, channel): amp}."""
    width = bits // 8
    frames = int(rate * seconds)
    buf = bytearray(frames * channels * width)
    peak = 2 ** (bits - 1) - 1
    for (frame, ch), amp in hits.items():
        off = (frame * channels + ch) * width
        buf[off : off + width] = int(amp * peak).to_bytes(width, "little", signed=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(bytes(buf))
    return path


def impulse_wav(
    path: Path,
    channels: int,
    at: int = SR,
    which: list[int] | None = None,
    amp: float = 0.5,
    seconds: float = 3.0,
    rate: int = SR,
) -> Path:
    """One impulse at frame `at` in each channel of `which` (default: all)."""
    chans = range(channels) if which is None else which
    return write_wav(
        path, channels, {(at, c): amp for c in chans}, seconds=seconds, rate=rate
    )


def staggered_wav(path: Path, channels: int, start: int = SR, step: int = 2400) -> Path:
    """An impulse in channel c at frame start + c * step."""
    return write_wav(
        path, channels, {(start + c * step, c): 0.5 for c in range(channels)}
    )


def noise_wav(
    path: Path, channels: int, seconds: float = 3.0, amp: float = 0.2
) -> Path:
    """Deterministic white noise, 24-bit."""
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(3)
        w.setframerate(SR)
        w.writeframes(noise_samples(int(SR * seconds) * channels, amp, "little"))
    return path


def noise_samples(count: int, amp: float, byteorder: Literal["little", "big"]) -> bytes:
    """`count` 24-bit samples of deterministic white noise."""
    state = 12345
    peak = int(amp * (2**23 - 1))
    buf = bytearray()
    for _ in range(count):
        state = (1103515245 * state + 12345) & 0x7FFFFFFF
        value = (state % (2 * peak + 1)) - peak
        buf += value.to_bytes(3, byteorder, signed=True)
    return bytes(buf)


# --- Decoded output ------------------------------------------------------------


@dataclass
class Pcm:
    channels: int
    data: array  # interleaved int32

    @property
    def frames(self) -> int:
        return len(self.data) // self.channels

    def channel(self, c: int) -> array:
        return self.data[c :: self.channels]

    def peak(self, c: int) -> tuple[int, float]:
        """(frame, |amplitude| as a fraction of full scale) of the largest sample."""
        x = self.channel(c)
        hi, lo = max(x), min(x)
        value = hi if hi >= -lo else lo
        return x.index(value), abs(value) / 2**31

    def floats(self, c: int, start: int = 0, stop: int | None = None) -> list[float]:
        return [v / 2**31 for v in self.channel(c)[start:stop]]


def read_wav(path: Path) -> Pcm:
    """Read a 32-bit PCM WAV, including WAVE_FORMAT_EXTENSIBLE, which `wave` rejects."""
    raw = Path(path).read_bytes()
    assert raw[:4] == b"RIFF" and raw[8:12] == b"WAVE", f"not a WAV: {path}"
    pos, channels, payload = 12, 0, b""
    while pos + 8 <= len(raw):
        cid, size = raw[pos : pos + 4], struct.unpack_from("<I", raw, pos + 4)[0]
        body = raw[pos + 8 : pos + 8 + size]
        if cid == b"fmt ":
            channels = struct.unpack_from("<H", body, 2)[0]
            assert struct.unpack_from("<H", body, 14)[0] == 32, "expected 32-bit PCM"
        elif cid == b"data":
            payload = body
            break
        pos += 8 + size + (size & 1)
    data = array("i")
    data.frombytes(payload[: len(payload) // 4 * 4])
    return Pcm(channels, data)


def decode(tools: Tools, src: Path, dst: Path | None = None) -> Pcm:
    """Decode the first audio stream with ffmpeg to 32-bit PCM. AC-3 DRC is off."""
    dst = dst or src.with_name(src.name + ".dec.wav")
    cmd = [tools.ffmpeg, "-hide_banner", "-v", "error", "-y"]
    if src.suffix.lower() in AC3_SUFFIXES:
        cmd += ["-drc_scale", "0"]
    cmd += ["-i", src, "-map", "0:a:0", "-c:a", "pcm_s32le", "-f", "wav", dst]
    result = run(cmd)
    assert result.ok, result.out
    return read_wav(dst)


def xcorr(
    ref: Pcm,
    ref_ch: int,
    test: Pcm,
    test_ch: int,
    max_lag: int = 2048,
    window: int = 8192,
) -> tuple[int, float]:
    """(lag, normalized correlation) of `test` against `ref`; a positive lag is late.

    Uses one window around the loudest sample of `ref`, so it needs no numpy.
    """
    usable = min(ref.frames, test.frames) - 2 * (max_lag + window)
    assert usable > 0, "streams too short for the correlation window"
    region = ref.channel(ref_ch)[max_lag + window : max_lag + window + usable]
    hi, lo = max(region), min(region)
    center = region.index(hi if hi >= -lo else lo) + max_lag + window
    start = center - window // 2
    a = ref.floats(ref_ch, start, start + window)
    b = test.floats(test_ch, start - max_lag, start + window + max_lag)
    norm_a = math.sqrt(sum(map(mul, a, a)))
    best_lag, best, best_seg = 0, -math.inf, b[:window]
    for lag in range(-max_lag, max_lag + 1):
        seg = b[lag + max_lag : lag + max_lag + window]
        value = sum(map(mul, a, seg))
        if value > best:
            best_lag, best = lag, value
            best_seg = seg
    norm_b = math.sqrt(sum(map(mul, best_seg, best_seg)))
    return best_lag, best / (norm_a * norm_b + 1e-12)


# --- Misc ----------------------------------------------------------------------


def md5(path: Path) -> str:
    return hashlib.md5(Path(path).read_bytes()).hexdigest()  # noqa: S324


def mediainfo(path: Path) -> dict:
    from pymediainfo import MediaInfo

    tracks = MediaInfo.parse(str(path)).audio_tracks
    assert tracks, f"MediaInfo found no audio in {path}"
    return tracks[0].to_data()


CODEC_DELAY = re.compile(r"Codec delay:\s*(-?\d+)")


def codec_delay(log: str) -> int | None:
    """The `Codec delay:` value from a DEE log written with --loglevel debug."""
    found = CODEC_DELAY.findall(log)
    return int(found[-1]) if found else None


# --- Atmos masters -------------------------------------------------------------


def truehd_stream(tools: Tools, work: Path) -> Path:
    """The Atmos sample as a raw TrueHD stream."""
    assert tools.atmos_sample
    if tools.atmos_sample.suffix.lower() in {".thd", ".mlp", ".truehd"}:
        return tools.atmos_sample
    out = work / "sample.thd"
    if not out.exists():
        result = run(
            [
                tools.ffmpeg, "-hide_banner", "-v", "error", "-y", "-i", tools.atmos_sample,
                "-map", "0:a:0", "-c", "copy", "-f", "truehd", out,
            ]
        )  # fmt: skip
        assert result.ok, result.out
    return out


def make_damf(tools: Tools, thd: Path, out_dir: Path, *extra: str) -> Path:
    """Decode a TrueHD Atmos stream to a DAMF master with truehdd."""
    assert tools.truehdd
    out_dir.mkdir(parents=True, exist_ok=True)
    result = run(
        [
            tools.truehdd, "--loglevel", "warn", "decode", thd,
            "--output-path", out_dir / "m", *extra,
        ]
    )  # fmt: skip
    assert result.ok, result.out
    return out_dir / "m.atmos"


def truehd_content(tools: Tools, thd: Path, out_dir: Path) -> tuple[str, str]:
    """(audio md5, metadata md5) of a TrueHD Atmos stream as truehdd decodes it.

    TrueHD Atmos bytes change from run to run, so compare this, never file hashes.
    """
    damf = make_damf(tools, thd, out_dir)
    audio = damf.with_name(damf.name + ".audio")
    metadata = damf.with_name(damf.name + ".metadata")
    return md5(audio), md5(metadata)


WARP_LINE = re.compile(r"^\s*warpMode:.*\n", re.MULTILINE)


def warp_mode(damf: Path) -> str | None:
    found = re.search(r"^\s*warpMode:\s*(\S+)", damf.read_text(), re.MULTILINE)
    return found.group(1) if found else None


def damf_with_warp(damf: Path, warp: str | None) -> Path:
    """A copy of the DAMF header with this warpMode (None removes it).

    The copy sits next to the original, so it shares the audio and metadata files.
    """
    text = WARP_LINE.sub("", damf.read_text())
    if warp is not None:
        text = re.sub(
            r"^(\s*)(creationToolVersion:.*)$",
            rf"\1\2\n\1warpMode: {warp}",
            text,
            count=1,
            flags=re.MULTILINE,
        )
    # Windows paths ignore case, so the name must tell "loro" from "LoRo".
    tag = hashlib.md5(str(warp).encode()).hexdigest()[:6]  # noqa: S324
    out = damf.with_name(f"warp_{warp or 'none'}_{tag}.atmos")
    out.write_text(text)
    return out


# shaped like the Atmos sample: an LFE-only bed and 15 objects. A master with a
# full 7.1 bed and few objects hides the ProLogicIIx difference that
# test_prologiciix_changes_only_truehd_header_bytes checks.
SYNTHETIC_BED = (3, "LFE")
SYNTHETIC_OBJECTS = [
    (10 + i, (round(-1 + i / 7, 3), 1 - (i % 3), i % 2)) for i in range(15)
]


def synthetic_damf(out_dir: Path, seconds: float = 2.0) -> Path:
    """A short DAMF master of noise: an LFE bed and 15 objects that never move.

    DEE encodes it to the same TrueHD bytes every run, unlike the sample, so
    file hashes can compare its TrueHD Atmos encodes.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    bed_id, bed_name = SYNTHETIC_BED
    header = [
        "version: 0.5.1",
        "presentations:",
        "  - type: home",
        "    simplified: false",
        "    metadata: m.atmos.metadata",
        "    audio: m.atmos.audio",
        "    offset: 0.0",
        "    fps: 24",
        f"    scBedConfiguration: [{bed_id}]",
        "    creationTool: deezy-tests",
        "    creationToolVersion: 1.0",
        "    bedInstances:",
        "      - channels:",
        f"          - channel: {bed_name}",
        f"            ID: {bed_id}",
        "    objects:",
        *(f"      - ID: {oid}" for oid, _ in SYNTHETIC_OBJECTS),
    ]
    (out_dir / "m.atmos").write_text("\n".join(header) + "\n")

    shared = ["samplePos: 0", "active: true"]
    tail = ["importance: 1.0", "gain: 0", "rampLength: 0", "trimBypass: false"]
    events = [f"sampleRate: {SR}", "events:"]
    events += [f"  - ID: {bed_id}", *(f"    {line}" for line in (
        *shared, *tail, "headTrackMode: undefined", "binauralRenderMode: off",
    ))]  # fmt: skip
    for oid, pos in SYNTHETIC_OBJECTS:
        events += [f"  - ID: {oid}", *(f"    {line}" for line in (
            *shared, f"pos: [{', '.join(str(p) for p in pos)}]", "snap: false",
            "elevation: true", "zones: all", "size: 0.0", *tail, "dialog: -1",
            "music: -1", "screenFactor: 0.0", "depthFactor: 0.25",
            "headTrackMode: undefined", "binauralRenderMode: undefined",
        ))]  # fmt: skip
    (out_dir / "m.atmos.metadata").write_text("\n".join(events) + "\n")

    # CAF: 24-bit big-endian PCM, one frame per packet
    channels = 1 + len(SYNTHETIC_OBJECTS)
    pcm = noise_samples(int(SR * seconds) * channels, 0.2, "big")
    desc = struct.pack(">dIIIIII", SR, 0x6C70636D, 0, 3 * channels, 1, channels, 24)
    caf = b"caff" + struct.pack(">HH", 1, 0)
    caf += b"desc" + struct.pack(">q", len(desc)) + desc
    # the data chunk starts with a 4-byte edit count
    caf += b"data" + struct.pack(">qI", len(pcm) + 4, 0) + pcm
    (out_dir / "m.atmos.audio").write_bytes(caf)
    return out_dir / "m.atmos"
