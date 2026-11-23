# Installation

DeeZy needs FFmpeg and the DEE 6.7 command-line tools. truehdd is needed for the
Atmos formats, and [dee_shim](dee-shim.md) is optional.

## DeeZy

Download an executable from the releases page, or install the Python package:

```powershell
pipx install deezy
```

The executable comes in two builds:

- Bundled: the executable has a `bundle/` folder beside it, so it unpacks once.
  Best for a PATH install or for calling DeeZy from other programs.
- Standalone: a single executable that unpacks on demand, which can mean every
  run.

For a development install from a checkout, use `pipx install --editable .`.

## Tools

| Tool | Needed for |
| --- | --- |
| FFmpeg | every encode |
| DEE 6.7 command-line tools | every encode |
| truehdd | `ddp-atmos`, `thd-atmos`, `ac4-atmos` and `ac4-ims`; it decodes TrueHD Atmos sources. DeeZy is tested with truehdd 0.6.3 |
| dee_shim 0.2.1 or newer | optional; see [dee_shim](dee-shim.md) |

DEE 6.7 is a folder of command-line tools, one per job (`dee_ddp_encoder`,
`dee_ddpjoc_encoder`, `dee_dthd_encoder`, `dee_ac4_encoder`,
`dee_ac4ims_encoder`, `dee_ac4ajoc_encoder`, `dee_aac_encoder`,
`dee_measure_loudness` and others). Keep the folder whole: the tools need the
`mediainfo.dll` beside them. DeeZy refuses any other DEE version, including the
single `dee` executable of DEE 5.2 that DeeZy 1.x used.

## Where DeeZy finds the tools

For each tool DeeZy takes, in order:

1. the path given with `--ffmpeg`, `--dee`, `--truehdd` or `--dee-shim`;
2. the path under `[dependencies]` in the [config](configuration.md);
3. the `apps` folder beside DeeZy;
4. PATH.

On Windows DeeZy also finds the DEE tools of an installed Dolby Media Encoder.
`--dee` takes the tools' folder, or the path of one of them. The portable
layout is:

```
deezy.exe
└── apps/
    ├── ffmpeg/ffmpeg.exe
    ├── dee/            # the DEE 6.7 tools, with mediainfo.dll
    ├── truehdd/truehdd.exe
    └── dee_shim/dee_shim.exe   # optional
```

## DEE license

The DEE tools look for a `license.lic` beside themselves. When there isn't one,
DeeZy passes them a Dolby Media Encoder license: `dme_license.lic` beside the
tools, or `license.lic` in `%APPDATA%\Dolby Media Encoder`. The license must
cover DEE 6.7.

## Check the setup

`deezy tools` shows the FFmpeg, DEE tools, truehdd and dee_shim an encode would
use, with each one's version and path, and the license the DEE tools get. It
exits with 1 when an encode couldn't run.

```bash
deezy tools
```
