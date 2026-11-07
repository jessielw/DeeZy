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

<!-- prettier-ignore -->
!!! tip
    For rare **5.0** sources, DeeZy can insert a silent **LFE** to produce a **5.1** output (uses the `5.1(side)` layout). This behavior is opt-in via `--upmix-50-to-51`.

    *Note: You should also pass `--channels 6`*.

Advanced options: `--track-index`, `--delay`, `--custom-dialnorm`, `--metering-mode`, `--no-dialogue-intelligence`, `--speech-threshold`

## Loudness

By default DeeZy measures the loudness and writes the measured dialnorm. `--custom-dialnorm -27` skips measurement and writes that dialnorm instead (works with both DEE layouts).

With the split DEE encoders only, `--loudness-target` measures **and corrects** the audio to a target instead:

```bash
deezy encode dd --loudness-target -24 input.mkv
deezy encode dd --loudness-target -27 --peak-limit -3 input.mkv
```

`--loudness-target` takes -31 to -8 (LKFS). `--peak-limit` (-12 to -0.1 dBTP) must be at least 6 dB above the target and defaults to the encoder's -2. Neither can be combined with `--custom-dialnorm`. The single `dee` stops with a message if you use them.

### Loudness presets

`--loudness-preset` measures to a broadcast regulation instead of the manual settings. Choices: `atsc_a85`, `ebu_r128`, `freetv_op59`, `arib_b32` (default `manual`). Split DEE encoders only.

```bash
deezy encode dd --loudness-preset ebu_r128 input.mkv
```

A preset sets its own gating, so `--no-dialogue-intelligence` and `--speech-threshold` are ignored with it, and it can't be combined with `--loudness-target`. `--custom-dialnorm` still wins if given. The preset changes the measured dialnorm: on the same Atmos clip `manual` gave -18 and `ebu_r128` gave -13.

## Split DEE encoders

`--metering-mode` is ignored (always 1770-4). Everything else works. See [Installation](../installation.md#split-vs-single-dee).
