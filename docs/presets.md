# Presets

Presets are simple command strings in the config under `[presets]`.

Example

```toml
[presets]
streaming_ddp = "encode ddp --channels surround --bitrate 448"
```

Usage

```bash
deezy encode preset --name streaming_ddp input.mkv
deezy encode preset --name streaming_ddp --bitrate 640 input.mkv
```

Presets are validated and can be overridden by CLI flags.
