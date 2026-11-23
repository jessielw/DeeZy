# Bitrates

`deezy bitrates` lists, for each format and mode, every layout's default data
rate and every rate DEE takes for it, in kbps. Each format's page has the same
list.

```bash
deezy bitrates
deezy bitrates ddp ddp-atmos
```

- `--bitrate` picks a rate. One DEE doesn't take becomes the closest one it
  does, with a warning.
- `[default_bitrates]` in the [config](configuration.md) changes a default, and
  `deezy bitrates` shows it beside DeeZy's own.
  `[default_source_bitrates]` sets a default per source channel count.
- A layout marked "needs dee_shim" is encoded through [dee_shim](dee-shim.md).
- TrueHD (`thd`, `thd-atmos`) is lossless and has no data rate.
