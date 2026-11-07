# Dolby Atmos

Professional Atmos encoding for immersive audio.

Examples

```bash
deezy encode atmos input.mkv
deezy encode atmos --atmos-mode bluray --bitrate 768 input.mkv
```

Options: `--atmos-mode` (`streaming` or `bluray`), `--thd-warp-mode`, `--bed-conform`

## Loudness

`--custom-dialnorm` is supported (writes that dialnorm instead of measuring), in both streaming and Blu-ray mode.

### Loudness presets

`--loudness-preset` measures to a broadcast regulation instead of the manual settings. Choices: `atsc_a85`, `ebu_r128`, `freetv_op59`, `arib_b32` (default `manual`). Split DEE encoders only.

```bash
deezy encode atmos --loudness-preset ebu_r128 input.mkv
```

A preset sets its own gating, so `--no-dialogue-intelligence` and `--speech-threshold` are ignored with it, and it can't be combined with `--loudness-target`. `--custom-dialnorm` still wins if given. The preset changes the measured dialnorm: on the same Atmos clip `manual` gave -18 and `ebu_r128` gave -13.

## Split DEE encoders

Fully supported, including `--atmos-mode bluray` (the Blu-ray mode of the split Atmos encoder) and `--custom-dialnorm`. Streaming Atmos does not take 512 kbps, so DeeZy uses the nearest accepted rate (576) and says so. See [Installation](../installation.md#split-vs-single-dee).
