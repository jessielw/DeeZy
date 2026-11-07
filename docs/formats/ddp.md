# Dolby Digital Plus (DDP)

Enhanced quality with higher bitrates and advanced features.

Examples

```bash
deezy encode ddp input.mkv
deezy encode ddp --channels 6 --bitrate 448 input.mkv
deezy encode ddp --channels 8 --bitrate 768 input.mkv
```

Channel options: `0` (AUTO), `1` (MONO), `2` (STEREO), `6` (5.1), `8` (7.1 SURROUNDEX; single `dee` only, use [`ddp-bluray`](ddp-bluray.md) for 7.1 with the split encoders)

Key features: higher bitrates, advanced processing, smart defaults.

<!-- prettier-ignore -->
!!! tip
    For rare **5.0** sources, DeeZy can insert a silent **LFE** to produce a **5.1** output (uses the `5.1(side)` layout). This behavior is opt-in via `--upmix-50-to-51`.

    *Note: You should also pass `--channels 6`*.

## Loudness

By default DeeZy measures the loudness and writes the measured dialnorm. `--custom-dialnorm -27` skips measurement and writes that dialnorm instead (both DEE layouts). `--loudness-target` / `--peak-limit` measure and correct instead, exactly as for [DD](dd.md#loudness) (split DEE encoders only).

## Split-encoder-only options

```bash
# write a user data ID into the stream (-1 = none, the default)
deezy encode ddp --user-data 100 input.mkv

# Blu-ray secondary audio: 2.0 or 5.1 only, 192 or 256 kbps
deezy encode ddp --bluray-secondary --channels 6 --bitrate 256 input.mkv
```

`--bluray-secondary` picks the 192 or 256 kbps rate closest to `--bitrate` (192 by default) and needs `--channels 2` or `--channels 6` (or a source that resolves to one of those). `--loudness-target` works with it, `--user-data` does not. The single `dee` stops with a message if you use these.

## Split DEE encoders

- DD+ 7.1 for online media (`--channels 8`) is not available: the encoder would quietly produce 5.1. DeeZy stops with a message. Use `ddp-bluray` for 7.1, or `--channels 6`. A 7.1 source with no `--channels` resolves to 7.1 and stops the same way.
- `--metering-mode` is ignored (always 1770-4).

See [Installation](../installation.md#split-vs-single-dee).
