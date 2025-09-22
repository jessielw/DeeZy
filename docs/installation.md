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
