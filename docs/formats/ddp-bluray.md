# DDP BluRay

Specialized DDP encoding optimized for BluRay disc mastering.

Examples

```bash
deezy encode ddp-bluray input.mkv
deezy encode ddp-bluray --bitrate 1536 input.mkv
```

## Loudness

`--custom-dialnorm` is supported. `--loudness-target` (loudness correction) is not available for Blu-ray DD+.

## Split DEE encoders

Fully supported: 7.1 Blu-ray DD+ is the Blu-ray mode of the split DD+ encoder. Data rates 768, 1024, 1280, 1536 and 1664 kbps all work. `--metering-mode` is ignored (always 1770-4). See [Installation](../installation.md#split-vs-single-dee).
