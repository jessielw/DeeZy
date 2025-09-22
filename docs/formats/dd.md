# Dolby Digital (DD)

Perfect for legacy compatibility and smaller file sizes.

Examples

```bash
deezy encode dd input.mkv
deezy encode dd --channels 6 --bitrate 448 input.mkv
deezy encode dd --output "output.ac3" --keep-temp input.mkv
```

Channel options: `0` (AUTO), `1` (MONO), `2` (STEREO), `6` (5.1 SURROUND)

Common options: `--bitrate`, `--drc-line-mode`, `--stereo-down-mix`

Advanced options: `--track-index`, `--delay`, `--custom-dialnorm`, `--metering-mode`, `--no-dialogue-intelligence`, `--speech-threshold`
