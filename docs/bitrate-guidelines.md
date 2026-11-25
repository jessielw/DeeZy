# Bitrates

`deezy bitrates` lists, for each format and mode, every layout's default data
rate and every rate DEE takes for it, in kbps. Each format's page has the same
list.

```bash
deezy bitrates
deezy bitrates ddp ddp-atmos
```

- An integer `--bitrate` picks a total rate. One DEE doesn't take becomes the closest one it
  does, with a warning.
- `[default_bitrates]` in the [config](configuration.md) changes a default, and
  `deezy bitrates` shows it beside DeeZy's own.
  `[default_source_bitrates]` sets a default per source channel count.
- A layout marked "needs dee_shim" is encoded through [dee_shim](dee-shim.md).
- TrueHD (`thd`, `thd-atmos`) is lossless and has no data rate.

## Substream bitrates

```bash
deezy encode ddp-atmos --atmos-mode standard --bitrate 1024:512 input.mkv
```

This requests 1024 kbps for the independent stream and 512 kbps for the
dependent stream, or 1536 kbps total. With dee_shim, exact pairs work for
DD+ 7.0 and 7.1, DD+ Blu-ray 7.0 and 7.1, and the standard and Blu-ray
DD+ Atmos modes. Each E-AC-3 stream takes 32 to 1024 kbps. For Blu-ray the
first value is the AC-3 core rate, one of 224, 256, 320, 384, 448, 512, 576
or 640 kbps. A low rate can leave too little room for the source metadata.

Use the same option in presets. To make the example your default, set
`standard = "1024:512"` under `[default_bitrates.ddp-atmos]`. The other
keys that accept pairs are `bluray` in that section and `surroundex` under
`[default_bitrates.ddp]` and `[default_bitrates.ddp-bluray]`.
