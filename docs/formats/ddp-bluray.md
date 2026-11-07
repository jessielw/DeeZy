# DDP BluRay

Specialized DDP encoding optimized for BluRay disc mastering.

Examples

```bash
deezy encode ddp-bluray input.mkv
deezy encode ddp-bluray --bitrate 1536 input.mkv
```

## Loudness

`--custom-dialnorm` is supported. `--loudness-target` (loudness correction) is not available for Blu-ray DD+.

### Loudness presets

`--loudness-preset` measures to a broadcast regulation instead of the manual settings. Choices: `atsc_a85`, `ebu_r128`, `freetv_op59`, `arib_b32` (default `manual`). Split DEE encoders only.

```bash
deezy encode ddp-bluray --loudness-preset ebu_r128 input.mkv
```

A preset sets its own gating, so `--no-dialogue-intelligence` and `--speech-threshold` are ignored with it, and it can't be combined with `--loudness-target`. `--custom-dialnorm` still wins if given. The preset changes the measured dialnorm: on the same Atmos clip `manual` gave -18 and `ebu_r128` gave -13.

## Split DEE encoders

Fully supported: 7.1 Blu-ray DD+ is the Blu-ray mode of the split DD+ encoder. Data rates 768, 1024, 1280, 1536 and 1664 kbps all work. `--metering-mode` is ignored (always 1770-4). See [Installation](../installation.md#split-vs-single-dee).
