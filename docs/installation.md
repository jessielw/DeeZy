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

The split encoders read their license from a `license.lic` beside them, so put your license in that folder. They also need `libmediainfo.dll` beside them, so copy the whole folder rather than just the executables. (Dolby Media Encoder only creates its license while a job is running and removes it afterwards, so it is not left in its own folder.)

Not available with the split encoders (DeeZy stops with a clear message rather than encode something different from what was asked): `--custom-dialnorm`, DD+ 7.1 (including Blu-ray DD+), Blu-ray Atmos, and AC-4 `--ims-legacy-presentation` and `--encoding-profile ims_music`. Metering is always ITU-R BS.1770-4, so `--metering-mode` is ignored.

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
