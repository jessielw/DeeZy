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

## Split DEE encoders

Fully supported, including `--atmos-mode bluray` (the Blu-ray mode of the split Atmos encoder) and `--custom-dialnorm`. Streaming Atmos does not take 512 kbps, so DeeZy uses the nearest accepted rate (576) and says so. See [Installation](../installation.md#split-vs-single-dee).
