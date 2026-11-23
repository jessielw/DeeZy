# Migrating from DeeZy 1.x

DeeZy 2.0 runs only the DEE 6.7 command-line tools. The single `dee` of DEE 5.2
and other DEE versions are refused. See [Installation](installation.md), and
check the setup with `deezy tools`.

The changes most likely to affect your commands, presets and config come first.

## 1. Renamed formats, and what `ac4` means now

| 1.x | 2.0 |
| --- | --- |
| `atmos` | `ddp-atmos` |
| `ac4` (immersive stereo) | `ac4-ims` |
| | `ac4`: channel-based AC-4, 2.0 or 5.1 |

- A 1.x `atmos` command or preset fails: `atmos` is no longer a format.
- A 1.x `ac4` command still runs, but it now makes channel-based AC-4 instead
  of immersive stereo. DeeZy logs a notice each time `ac4` runs. Change `ac4` to
  `ac4-ims` to keep 1.x's output. Options only immersive stereo takes, such as
  `--encoding-profile`, make an `ac4` command fail.
- In the config, `[default_bitrates.atmos]` is now
  `[default_bitrates.ddp-atmos]`, and 1.x's `[default_bitrates.ac4]` is now
  `[default_bitrates.ac4-ims]`. DeeZy ignores the 1.x sections and warns about
  them. The same goes for `[default_source_bitrates]`.

## 2. Surround 3 dB attenuation is off by default

DeeZy 1.x lowered the surround channels of `dd`, `ddp` and `ddp-bluray` by
3 dB. DeeZy 2.0 follows DEE's default and leaves them alone. `--surround-3db`
turns the attenuation on and gives 1.x's output. `--no-surround-3db` still
parses and asks for what is now the default.

## 3. Warp mode for a TrueHD Atmos stream that has none

DeeZy 1.x gave such a stream the `normal` warp mode when it decoded it with
truehdd. DeeZy 2.0 gives it none, so DEE renders it as `warping`, its own
default. This changes `ddp-atmos`, `ac4-atmos` and `ac4-ims` encodes of such a
stream; `thd-atmos` audio doesn't change. `--thd-warp-mode normal` gives 1.x's
output. A stream that has a warp mode keeps it.

## 4. Loudness and data rate defaults

These are unchanged: DEE measures the loudness and writes the measured dialnorm
(`measure_only`), and DeeZy keeps its own default rates, which are higher than
DEE's automatic ones. What changed:

- The rates each format takes are DEE 6.7's, listed by `deezy bitrates`. A
  rate DEE doesn't take becomes the closest one it does, with a warning.
- `--metering-mode` is gone: DEE 6.7 measures with ITU-R BS.1770-4 only. Remove
  it from commands and presets.
- The new `aac` format leaves the loudness as it is by default, because DEE's
  AAC encoder can't only measure it.

## 5. `--bed-conform` is gone

It changed no DEE output. Remove it from commands and presets; DeeZy refuses
it.

## 6. `[global_defaults]` keys now apply

DeeZy 1.x ignored the option keys under `[global_defaults]`, such as
`speech_threshold`, `drc_line_mode`, `stereo_down_mix`, `track_index` and
`keep_temp`. DeeZy 2.0 makes each the default of its option (see
[Configuration](configuration.md#global-defaults)). A config made by 1.x's
`deezy config generate` has `speech_threshold = 20`, which now applies: DeeZy's
own default is 15. Delete the line or set it to 15 to keep 1.x's output. A key
that names no option, such as `metering_mode`, is ignored with a warning.

## Other removed options

- `--ims-legacy-presentation` (1.5.0 already ignored it).
- `--metering-mode` (see 4).

## Layouts

- A 5.0 source to `dd` or `ddp` is coded as 5.0; 1.x downmixed it to 2.0.
  `--upmix-50-to-51` still gives 5.1 with a silent LFE.
- A 7.0 source: `ddp` codes 7.0 through [dee_shim](dee-shim.md), else 5.0;
  `ddp-bluray` codes 7.0 through dee_shim, else 7.1 with a silent LFE (1.x
  refused it).
- DD+ 7.1 (`ddp --channels 8`) works through dee_shim, at 384 to 1792 kbps.
  With `--channels 0`, an 8-channel source gets 7.1 when DeeZy has dee_shim,
  else 5.1 with a notice.

## ddp-atmos

- `--atmos-mode bluray` now codes a 7.1 backbone with an AC-3 core (1152 to
  1664 kbps) and needs dee_shim. DEE's own Blu-ray mode, which 1.x used, gives a
  5.1.2 backbone.
- `--atmos-mode standard` is new: a 7.1 backbone as E-AC-3, 448 to 2048 kbps,
  1152 by default. It needs dee_shim.
- Through dee_shim, every ddp-atmos encode codes the master's object metadata as
  it is. `--no-oamd-as-is` gives plain DEE's output.
- `--no-surround-90-deg-phase-shift` now works for ddp-atmos, through dee_shim.

## Blu-ray secondary audio

`ddp --bluray-secondary` takes 96 to 256 kbps for 2.0 and 160 to 256 kbps for
5.1 (1.5.0 took 192 or 256). A rate it doesn't take becomes the closest one.

## Output names and files

- The automatic name of a single input has no `_f1`.
- An output template drops an empty `[]` or `()` left by a field with no value,
  so `{title} [{lang}]` with no language gives `title.ec3`.
- `{stem-cleaned}` works; 1.x wrote the token into the name as it was.
- DeeZy refuses an output that is a source of the run or another job's output,
  even with `--overwrite`, and refuses `--output` with several inputs.
- An interrupted or failed encode leaves no partial output.
- `--delay` also takes frames at a frame rate, as in `--delay=-3@23.976`.

## Temp files and checks

- On Windows, FFmpeg's audio for `dd`, `ddp`, `ddp-bluray`, `ac4` and `aac`
  goes straight into DEE through a pipe by default (`--pipe auto`).
  `--pipe never` writes the temp WAV, as 1.x did.
- `--reuse-temp-files` doesn't reuse 1.x's Atmos and AC-4 temp folders.
- DeeZy checks a job's options before it extracts or encodes anything, so a
  refused option fails at once.
- With `--config FILE`, DeeZy no longer also reads the config it would find on
  its own.

## New in 2.0

- Formats: `thd`, `thd-atmos`, channel-based `ac4`, `ac4-atmos` and `aac`. See
  [encode](cli/encode.md).
- Atmos masters (DAMF and ADM BWF) as sources for the Atmos formats, and for
  `dd` and `ddp`, which DEE renders.
- Commands: `deezy measure`, `deezy bitrates` and `deezy tools`.
- Options: `--dry-run`, `--print-commands`, `--keep-logs`, `--disable-lfe`,
  `--surround-3db`, `--pipe`, `--dee-shim` and `--no-shim`, and for TrueHD
  Atmos `--atmos-elements` and `--legacy-authoring`.
- [dee_shim](dee-shim.md) support: DD+ 7.1, the 7.1 Atmos modes, TrueHD
  `--drc none`, and faster DD+ Atmos and TrueHD encodes on AMD CPUs.
