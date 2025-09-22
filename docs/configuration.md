# Configuration

DeeZy uses a TOML-based configuration file (`deezy-conf.toml`) to provide sensible defaults and reusable presets. CLI arguments always override config values.

Key sections

- `[dependencies]` — paths to external tools (ffmpeg, dee, truehdd)
- `[global_defaults]` — global behavior (keep_temp, working_dir, batching)
- `[default_bitrates]` — per-format default bitrates
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

[global_defaults]
keep_temp = false
max_parallel = 1
overwrite = false

[presets]
streaming_ddp = "encode ddp --channels surround --bitrate 448"
```

Per-source default bitrates are opt-in via `[default_source_bitrates.<codec>]` and allow pick-by-channel-count.
