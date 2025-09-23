# Dolby Digital Plus (DDP)

Enhanced quality with higher bitrates and advanced features.

Examples

```bash
deezy encode ddp input.mkv
deezy encode ddp --channels 6 --bitrate 448 input.mkv
deezy encode ddp --channels 8 --bitrate 768 input.mkv
```

Channel options: `0` (AUTO), `1` (MONO), `2` (STEREO), `6` (5.1), `8` (7.1 SURROUNDEX)

Key features: higher bitrates, advanced processing, smart defaults.

<!-- prettier-ignore -->
!!! tip
    For rare **5.0** sources, DeeZy can insert a silent **LFE** to produce a **5.1** output (uses the `5.1(side)` layout). This behavior is opt-in via `--upmix-50-to-51`.

    *Note: You should also pass `--channels 6`*.
