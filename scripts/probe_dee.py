"""Probe the DEE 6.7 tools and write what DeeZy relies on to a JSON fixture.

Every value comes from running the tools, not from their documentation:
accepted and automatic data rates per tool, mode and layout, the AAC codec delay
for every rate, the AC-4 manifest offsets, and each tool's options and defaults.

usage:
    python scripts/probe_dee.py --dee DIR [--license FILE] [--atmos-master M.atmos]
                                [--ffmpeg FILE] [--out deezy/dee/data/dee_6_7_0.json]

Atmos rates need a DAMF master (--atmos-master). Without one they are left out.
The script also lists the rates DeeZy offers that DEE rejects.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import itertools
import json
from pathlib import Path
import re
import struct
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.integration.harness import (  # noqa: E402
    Tools,
    codec_delay,
    mediainfo,
    noise_wav,
)

TOOLS = [
    "dee_ddp_encoder",
    "dee_ddpjoc_encoder",
    "dee_dthd_encoder",
    "dee_ac4_encoder",
    "dee_ac4ajoc_encoder",
    "dee_ac4ims_encoder",
    "dee_aac_encoder",
    "dee_measure_loudness",
]
SECONDS = 2.0
DDP_LIST = (
    "32|40|48|56|64|72|80|88|96|104|112|120|128|144|160|176|192|200|208|216|224|232|"
    "240|248|256|272|288|304|320|336|352|368|384|400|448|512|576|640|704|768|832|896|"
    "960|1008|1024"
)


def pe_id(path: Path) -> str:
    """COFF TimeDateStamp-SizeOfImage, the build identity dee_shim pins."""
    head = path.read_bytes()[:4096]
    pe = struct.unpack_from("<I", head, 0x3C)[0]
    stamp = struct.unpack_from("<I", head, pe + 8)[0]
    size = struct.unpack_from("<I", head, pe + 24 + 56)[0]
    return f"{stamp:08X}-{size:08X}"


def help_facts(tools: Tools, tool: str) -> dict:
    text = tools.help(tool)

    def default(option: str) -> str | None:
        found = re.search(rf"{re.escape(option)} arg \(=([^)]*)\)", text)
        return found.group(1) if found else None

    return {
        "pe_id": pe_id(tools.tool(tool)),
        "has_temp_dir": "--temp-dir" in text,
        "has_input_format": "--input-format" in text,
        "start_default": default("--start"),
        "loudness_default": default("--loudness-management"),
    }


def deezy_rates() -> dict[str, set[int]]:
    """The rates DeeZy 1.x offers, to report the ones DEE rejects."""
    from deezy.enums.ac4 import Ac4Channels
    from deezy.enums.atmos import AtmosMode
    from deezy.enums.dd import DolbyDigitalChannels
    from deezy.enums.ddp import DolbyDigitalPlusChannels
    from deezy.enums.ddp_bluray import DolbyDigitalPlusBlurayChannels

    def collect(enum) -> dict[str, set[int]]:
        out = {}
        for member in enum:
            try:
                out[str(member)] = set(member.get_bitrate_obj().choices)
            except Exception:  # noqa: S112 - AUTO members have no list
                continue
        return out

    return {
        "dd": collect(DolbyDigitalChannels),
        "ddp": collect(DolbyDigitalPlusChannels),
        "ddp_bluray": collect(DolbyDigitalPlusBlurayChannels),
        "atmos": collect(AtmosMode),
        "ac4": collect(Ac4Channels),
    }


class Prober:
    def __init__(self, tools: Tools, work: Path, master: Path | None, jobs: int):
        self.tools, self.work, self.master, self.jobs = tools, work, master, jobs
        self.wav = {
            ch: noise_wav(work / f"n{ch}.wav", ch, SECONDS) for ch in (1, 2, 6, 8)
        }
        self._ids = itertools.count(1)

    def out(self, ext: str) -> Path:
        return self.work / f"o{next(self._ids)}{ext}"

    def rates(self, label: str, candidates, encode) -> dict:
        """encode(rate or 'auto') -> (Run, output). Returns accepted rates and auto."""
        cands = sorted(set(candidates))
        with ThreadPoolExecutor(self.jobs) as pool:
            results = list(pool.map(encode, cands))
        accepted = [r for r, (run, _) in zip(cands, results, strict=True) if run.ok]
        run, out = encode("auto")
        auto, how = auto_rate(out, accepted) if run.ok else (None, None)
        print(f"  {label:34} auto={auto}{how} accepted={accepted}", flush=True)
        return {"auto": auto, "rates": accepted}

    def basic_args(self, tool: str) -> list | None:
        """Arguments for one small encode with each tool; None without a master."""
        w6, out = self.wav[6], self.out
        wav_in = ["--input-format", "wav", "-i", w6]
        if tool == "dee_ddp_encoder":
            return [*wav_in, "-o", out(".ec3"), "-e", "ddp"]
        if tool == "dee_dthd_encoder":
            return [
                "--presentation",
                "6ch",
                *wav_in,
                "-o",
                out(".thd"),
                "--temp-dir",
                self.work,
            ]
        if tool == "dee_ac4_encoder":
            o = out(".ac4")
            return [*wav_in, "-o", o, "--output-manifest", o.with_suffix(".json")]
        if tool == "dee_ac4ims_encoder":
            return [*wav_in, "-o", out(".ac4")]
        if tool == "dee_aac_encoder":
            return [*wav_in, "-o", out(".aac")]
        if tool == "dee_measure_loudness":
            return [*wav_in, "--output-manifest", out(".json")]
        if not self.master:
            return None
        if tool == "dee_ddpjoc_encoder":
            master = ["--input-format", "atmos_mezz", "-i", self.master]
            return [*master, "-o", out(".ec3"), "-e", "ddpjoc", "--duration", "0.5"]
        if tool == "dee_ac4ajoc_encoder":
            o = out(".ac4")
            return ["-i", self.master, "-o", o, "--level", "3", "--duration", "0.5",
                    "--output-manifest", o.with_suffix(".json")]  # fmt: skip
        return None

    def loudness_modes(self, tool: str) -> dict | None:
        """Which --loudness-management modes the tool runs with, for its usual input."""
        modes = ["skip", "skip:dialnorm=-31", "measure_only", "measure_and_correct"]
        if self.basic_args(tool) is None:
            return None
        return {m: self.tools.dee(tool, *self.basic_args(tool), "--loudness-management", m).ok
                for m in modes}  # fmt: skip

    def ddp(self) -> dict:
        def job(mode, ch, layout, ext):
            def encode(rate):
                out = self.out(ext)
                args = ["--input-format", "wav", "-i", self.wav[ch], "-o", out]
                args += ["-e", mode, "--loudness-management", "skip:dialnorm=-31"]
                args += ["--data-rate", str(rate)]
                if layout:
                    args += ["-c", layout]
                return self.tools.dee("dee_ddp_encoder", *args), out

            return encode

        dd_list = [96, 112, 128, 160, 192, 224, 256, 272, 320, 384, 448, 512, 576, 640]
        ddp_list = [int(v) for v in DDP_LIST.split("|")]
        extra = {1152, 1280, 1408, 1536, 1664, 2048}
        plan = {
            "dd": [("1.0", 1, "mono"), ("2.0", 2, "stereo"), ("5.1", 6, "5.1")],
            "ddp": [("1.0", 1, "mono"), ("2.0", 2, "stereo"), ("5.1", 6, "5.1")],
            "bluray": [("7.1", 8, None)],
            "bluray_secondary": [("2.0", 2, None), ("5.1", 6, None)],
        }
        result = {}
        for mode, layouts in plan.items():
            cands = dd_list if mode == "dd" else [*ddp_list, *extra]
            ext = {"dd": ".ac3", "bluray": ".eb3"}.get(mode, ".ec3")
            result[mode] = {
                name: self.rates(
                    f"ddp_encoder -e {mode} {name}", cands, job(mode, ch, lay, ext)
                )
                for name, ch, lay in layouts
            }
        return result

    def ac4(self) -> dict:
        def job(ch, layout):
            def encode(rate):
                out = self.out(".ac4")
                args = [
                    "--input-format",
                    "wav",
                    "-i",
                    self.wav[ch],
                    "-o",
                    out,
                    "-c",
                    layout,
                ]
                args += ["--output-manifest", out.with_suffix(".json")]
                args += [
                    "--loudness-management",
                    "measure_only",
                    "--data-rate",
                    str(rate),
                ]
                return self.tools.dee("dee_ac4_encoder", *args), out

            return encode

        cands = [48, 64, 96, 128, 144, 192, 256, 288, 320, 384, 448, 512, 768, 1024]
        return {
            name: self.rates(f"ac4_encoder {name}", cands, job(ch, lay))
            for name, ch, lay in (("2.0", 2, "stereo"), ("5.1", 6, "5.1"))
        }

    def ac4_offsets(self) -> dict:
        offsets = {}
        for name, ch in (("2.0", 2), ("5.1", 6)):
            out = self.out(".ac4")
            run = self.tools.dee(
                "dee_ac4_encoder", "--input-format", "wav", "-i", self.wav[ch], "-o", out,
                "--output-manifest", out.with_suffix(".json"),
                "--loudness-management", "measure_only",
            )  # fmt: skip
            if run.ok:
                offsets[name] = manifest_offset(out.with_suffix(".json"))
        print(f"  ac4_encoder manifest offsets {offsets}")
        return offsets

    def ims(self) -> dict:
        def encode(rate):
            out = self.out(".ac4")
            args = ["--input-format", "wav", "-i", self.wav[6], "-o", out]
            return self.tools.dee(
                "dee_ac4ims_encoder", *args, "--data-rate", str(rate)
            ), out

        cands = [48, 64, 96, 128, 144, 192, 256, 288, 320, 384, 448]
        return self.rates("ac4ims_encoder 5.1 in", cands, encode)

    def aac(self) -> dict:
        def encode(enc, rate):
            out = self.out(".aac")
            run = self.tools.dee(
                "dee_aac_encoder", "--loglevel", "debug", "--input-format", "wav",
                "-i", self.wav[2], "-o", out, "-e", enc, "--data-rate", str(rate),
                "--loudness-management", "skip",
            )  # fmt: skip
            return run

        result = {}
        for enc in ("aaclc", "heaac", "heaacv2"):
            cands = list(range(8, 600))
            with ThreadPoolExecutor(self.jobs) as pool:
                runs = list(pool.map(lambda r, e=enc: encode(e, r), cands))
            ok = [
                (r, codec_delay(run.out))
                for r, run in zip(cands, runs, strict=True)
                if run.ok
            ]
            bands = []
            for rate, delay in ok:
                if bands and bands[-1][2] == delay and bands[-1][1] == rate - 1:
                    bands[-1][1] = rate
                else:
                    bands.append([rate, rate, delay])
            result[enc] = {"range": [ok[0][0], ok[-1][0]], "codec_delay_bands": bands}
            print(
                f"  aac_encoder -e {enc:8} range={result[enc]['range']} bands={bands}"
            )
        return result

    def joc(self) -> dict:
        def job(mode):
            def encode(rate):
                out = self.out(".ec3")
                return self.tools.dee(
                    "dee_ddpjoc_encoder", "--input-format", "atmos_mezz", "-i", self.master,
                    "-o", out, "-e", mode, "--data-rate", str(rate), "--duration", "0.5",
                ), out  # fmt: skip

            return encode

        cands = [int(v) for v in DDP_LIST.split("|") if int(v) >= 256]
        cands += [1152, 1280, 1408, 1512, 1536, 1664, 1792, 2048]
        return {
            m: self.rates(f"ddpjoc_encoder -e {m}", cands, job(m))
            for m in ("ddpjoc", "bluray")
        }

    def ajoc(self) -> dict:
        def job(level):
            def encode(rate):
                out = self.out(".ac4")
                return self.tools.dee(
                    "dee_ac4ajoc_encoder", "-i", self.master, "-o", out, "--level", str(level),
                    "--output-manifest", out.with_suffix(".json"), "--data-rate", str(rate),
                    "--duration", "0.5",
                ), out  # fmt: skip

            return encode

        cands = [64, 96, 128, 144, 192, 256, 288, 320, 384, 448, 512, 768, 1024, 1500]
        result = {
            f"level{lv}": self.rates(f"ac4ajoc_encoder --level {lv}", cands, job(lv))
            for lv in (3, 4)
        }
        _, out = job(3)("auto")
        result["manifest_offset"] = manifest_offset(out.with_suffix(".json"))
        return result


def auto_rate(out: Path, accepted: list[int]) -> tuple[int | None, str]:
    """The coded rate, from MediaInfo or, for raw AC-4, from the size per second."""
    info = mediainfo(out)
    if "bit_rate" in info:
        return int(info["bit_rate"]) // 1000, ""
    manifest = out.with_suffix(".json")
    samples = SECONDS * 48000
    if manifest.exists():
        found = re.search(r'"duration"\s*:\s*(\d+)', manifest.read_text())
        samples = int(found.group(1)) + 2 * 2048 if found else samples  # pre/postroll
    kbps = out.stat().st_size * 8 / (samples / 48000) / 1000
    return min(accepted, key=lambda r: abs(r - kbps)), f" (from size, {kbps:.0f})"


def manifest_offset(path: Path):
    found = re.search(r'"offset"\s*:\s*(-?\d+)', path.read_text())
    return int(found.group(1)) if found else None


def rejected_deezy_rates(fixture: dict) -> list[str]:
    rates = fixture["rates"]
    checks = []
    deezy = deezy_rates()
    for layout, offered in deezy["dd"].items():
        if layout in rates["dee_ddp_encoder"]["dd"]:
            checks.append(
                (f"dd {layout}", offered, rates["dee_ddp_encoder"]["dd"][layout])
            )
    for layout, offered in deezy["ddp"].items():
        if layout in rates["dee_ddp_encoder"]["ddp"]:
            checks.append(
                (f"ddp {layout}", offered, rates["dee_ddp_encoder"]["ddp"][layout])
            )
    for layout, offered in deezy["ddp_bluray"].items():
        checks.append(
            (f"ddp-bluray {layout}", offered, rates["dee_ddp_encoder"]["bluray"]["7.1"])
        )
    joc = rates.get("dee_ddpjoc_encoder", {})
    for mode, offered in deezy["atmos"].items():
        key = "ddpjoc" if mode == "STREAMING" else "bluray"
        if key in joc:
            checks.append((f"atmos {mode.lower()}", offered, joc[key]))
    for layout, offered in deezy["ac4"].items():
        checks.append((f"ac4 (IMS) {layout}", offered, rates["dee_ac4ims_encoder"]))
    lines = []
    for label, offered, probed in checks:
        bad = sorted(offered - set(probed["rates"]))
        if bad:
            lines.append(f"{label}: DeeZy offers {bad}, DEE rejects them")
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dee", required=True, type=Path)
    parser.add_argument("--license", type=Path)
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--atmos-master", type=Path)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument(
        "--out", type=Path, default=ROOT / "deezy/dee/data/dee_6_7_0.json"
    )
    args = parser.parse_args()

    tools = Tools(args.dee, args.license, args.ffmpeg, None, None, None)
    version = re.search(
        r"Dolby Encoding Engine version (\S+)", tools.help("dee_ddp_encoder")
    )
    fixture = {
        "dee_version": version.group(1) if version else None,
        "tools": {t: help_facts(tools, t) for t in TOOLS if tools.tool(t).is_file()},
        "rates": {},
        "delays": {},
    }
    print(f"DEE {fixture['dee_version']}")
    with tempfile.TemporaryDirectory(prefix="deezy-probe-") as tmp:
        probe = Prober(tools, Path(tmp), args.atmos_master, args.jobs)
        for tool, facts in fixture["tools"].items():
            facts["loudness_modes"] = probe.loudness_modes(tool)
            print(f"  {tool:22} loudness modes {facts['loudness_modes']}")
        fixture["rates"]["dee_ddp_encoder"] = probe.ddp()
        fixture["rates"]["dee_ac4_encoder"] = probe.ac4()
        fixture["rates"]["dee_ac4ims_encoder"] = probe.ims()
        aac = probe.aac()
        fixture["rates"]["dee_aac_encoder"] = {k: v["range"] for k, v in aac.items()}
        fixture["delays"]["aac_codec_delay_bands"] = {
            k: v["codec_delay_bands"] for k, v in aac.items()
        }
        fixture["delays"]["ac4_manifest_offset"] = probe.ac4_offsets()
        if args.atmos_master:
            fixture["rates"]["dee_ddpjoc_encoder"] = probe.joc()
            ajoc = probe.ajoc()
            fixture["delays"]["ac4ajoc_manifest_offset"] = ajoc.pop("manifest_offset")
            fixture["rates"]["dee_ac4ajoc_encoder"] = ajoc

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(fixture, indent=2) + "\n")
    print(
        f"wrote {args.out.relative_to(ROOT) if args.out.is_relative_to(ROOT) else args.out}"
    )
    for line in rejected_deezy_rates(fixture):
        print("  REJECTED:", line)


if __name__ == "__main__":
    main()
