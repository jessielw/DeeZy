# Dolby Atmos

Professional Atmos encoding for immersive audio.

Examples

```bash
deezy encode atmos input.mkv
deezy encode atmos --atmos-mode bluray --bitrate 768 input.mkv
```

Options: `--atmos-mode` (`streaming` or `bluray`), `--thd-warp-mode`, `--bed-conform`

## Split DEE encoders

`--atmos-mode bluray` and `--custom-dialnorm` are not available with the split DEE encoders; DeeZy stops with a message. Streaming mode is supported. See [Installation](../installation.md).
