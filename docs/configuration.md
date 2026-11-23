# Configuration

DeeZy uses a TOML-based configuration file (`deezy-conf.toml`) to provide sensible defaults and reusable presets. CLI arguments always override config values.

Key sections

- `[dependencies]` — paths to the tools: `ffmpeg`, `dee` (the DEE 6.7 tools'
  folder), `truehdd` and `dee_shim`
- `[global_defaults]` — defaults for the options of every command (see
  [below](#global-defaults)), and DeeZy's own settings such as `working_dir`
  and `max_logs`
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

## Global defaults

A `[global_defaults]` key is an option's name with `_` for `-`, and its value
is that option's default:

```toml
[global_defaults]
speech_threshold = 20       # --speech-threshold 20
drc_line_mode = "music_light"
lt_rt_center = "-1.5"
keep_temp = true            # --keep-temp
dialogue_intelligence = false
```

- A `--no-x` switch takes either name: `dialogue_intelligence = false` and
  `no_dialogue_intelligence = true` both turn dialogue intelligence off.
- A key applies to every command that has the option, so `drc_line_mode`
  changes `dd`, `ddp`, `ddp-bluray` and `ddp-atmos` and nothing else.
- The command line and a preset still win.
- A key that names no option, or a value the option refuses, is ignored with a
  warning.
- `bitrate` goes under `[default_bitrates]`, and the tools' paths under
  `[dependencies]`.

Per-source default bitrates are opt-in via `[default_source_bitrates.<codec>]` and allow pick-by-channel-count.

`deezy bitrates` shows the defaults a config changes beside DeeZy's own.

## Sections from DeeZy 1.x

DeeZy 2.0 renamed two formats, so two 1.x sections are ignored, with a warning:

- `[default_bitrates.atmos]` is now `[default_bitrates.ddp-atmos]`.
- 1.x's `[default_bitrates.ac4]` was immersive stereo, which is now
  `[default_bitrates.ac4-ims]`; `ac4` is now channel-based AC-4. DeeZy warns
  when an `ac4` section has immersive stereo keys.

The same goes for `[default_source_bitrates]`.
