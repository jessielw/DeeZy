# Configuration

DeeZy uses a TOML-based configuration file (`deezy-conf.toml`) to provide sensible defaults and reusable presets. CLI arguments always override config values.

Key sections

- `[dependencies]` — paths to the tools: `ffmpeg`, `dee` (the DEE 6.7 tools'
  folder), `truehdd` and `dee_shim`
- `[global_defaults]` — defaults for every encode (`keep_temp`, `keep_logs`,
  `no_shim`, `working_dir`, batching, ...)
- `[default_bitrates]` — default data rates, one section per format, such as
  `[default_bitrates.ddp-atmos]`
- `[presets]` — named command strings for common workflows

Quick commands

```bash
deezy config generate
deezy config info
deezy --config my-config.toml encode ddp input.mkv
```

Example snippets

```toml
[dependencies]
ffmpeg = ""
dee = ""
truehdd = ""
dee_shim = ""

[global_defaults]
keep_temp = false
max_parallel = 1
allow_sleep = false
overwrite = false

[presets]
streaming_ddp = "encode ddp --channels surround --bitrate 448"
```

Per-source default bitrates are opt-in via `[default_source_bitrates.<codec>]` and allow pick-by-channel-count.

`deezy bitrates` shows the defaults a config changes beside DeeZy's own.

## Sections from DeeZy 1.x

DeeZy 2.0 renamed two formats, so two 1.x sections are ignored, with a warning:

- `[default_bitrates.atmos]` is now `[default_bitrates.ddp-atmos]`.
- 1.x's `[default_bitrates.ac4]` was immersive stereo, which is now
  `[default_bitrates.ac4-ims]`; `ac4` is now channel-based AC-4. DeeZy warns
  when an `ac4` section has immersive stereo keys.

The same goes for `[default_source_bitrates]`.
