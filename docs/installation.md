# Installation

DeeZy is distributed as a portable executable and via PyPI. Pick the option that fits your workflow.

Bundled vs Standalone

- Bundled: the executable is accompanied by a `bundle/` folder beside the executable. This reduces repeated unpacking and is ideal for PATH installations or embedding in other programs.
- Standalone: a single executable that unpacks on demand. Simpler distribution but may unpack each run.

Options

1. System PATH (recommended): Install or place `ffmpeg`, `dee` (Dolby Encoding Engine), and optionally `truehdd` on your system PATH.

2. Portable structure: create an `apps` folder beside the DeeZy executable with the expected tools:

```
deezy.exe
└── apps/
    ├── ffmpeg/ (ffmpeg.exe)
    ├── dee/ (dee.exe)
    └── truehdd/ (truehdd.exe)  # only for Atmos/AC-4 decoding
```

DEE can be either of two layouts, and DeeZy picks the right one from what it finds:

- **Single `dee`** (`dee.exe`): the classic Dolby Encoding Engine. Everything is supported.
- **Split encoders**: newer releases (including the copy bundled with Dolby Media Encoder) ship one executable per codec (`dee_ddp_encoder`, `dee_ddpjoc_encoder`, `dee_ac4ims_encoder`, ...) in a folder.

For the split layout, point `--dee` (or `dee` under `[dependencies]` in the config) at the **folder**, or put the encoders in `apps/dee/` or on your `PATH`. On Windows an installed Dolby Media Encoder is found automatically. A single `dee` always takes priority when both are present.

### Split encoder license

The split encoders look for a `license.lic` beside themselves. If there isn't one, DeeZy looks for a Dolby Media Encoder license and passes it automatically (`dme_license.lic` beside the encoders, or `license.lic` in `%APPDATA%\Dolby Media Encoder`). Otherwise put your license in the encoder folder as `license.lic`. The encoders also need `libmediainfo.dll` beside them, so copy the whole folder rather than just the executables.

### Split vs. single `dee`

Everything DeeZy offers works with both layouts except the items below. DeeZy never silently drops an option: where the split encoders can't do something it stops with a clear message, or (for the metering mode and `--ims-legacy-presentation`) says so in the log.

| Option | Single `dee` | Split encoders |
| --- | --- | --- |
| `--custom-dialnorm` (DD, DD+, Atmos) | Yes | Yes |
| DD+ 7.1 for Blu-ray (`ddp-bluray`) | Yes | Yes |
| Blu-ray Atmos (`--atmos-mode bluray`) | Yes | Yes |
| AC-4 `--encoding-profile ims_music` | Yes | Yes |
| DD+ 7.1 for online media (`ddp --channels 8`) | Yes | **No**, use `ddp-bluray` (or `--channels 6` for 5.1) |
| `--metering-mode` other than 1770-4 | Yes | **No**, always measured with ITU-R BS.1770-4 (noted in the log). Use `--loudness-preset` for regulation-based measuring |
| AC-4 `--ims-legacy-presentation` | Yes | **No**, ignored with a warning |
| `--loudness-target` / `--peak-limit` (DD, DD+) | No | Yes |
| `--loudness-preset` (all formats) | No | Yes |
| `--user-data` (DD+) | No | Yes |
| `--bluray-secondary` (DD+) | No | Yes |

The options marked "No" for the single `dee` stop with a message when used with it.

Data rates also differ slightly, so DeeZy adjusts a requested rate to the nearest one the split encoder accepts (and says so): AC-4 takes 64, 96, 128, 144, 256 and 320 kbps, and streaming Atmos does not take 512 kbps.

3. Install via pipx (Python-based install to get the `deezy` CLI shim):

```powershell
pipx install deezy
```

Development install (editable):

```powershell
pipx install --editable .
# or
pipx install --spec .
```

Dependencies

- FFmpeg: required for audio extraction and processing
- DEE: Dolby Encoding Engine required for encoding flows
- TrueHDD: required only for TrueHD Atmos decoding
