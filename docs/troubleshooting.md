# Troubleshooting

Common issues

- "truehdd decoder not found": install truehdd or add to PATH (only required for Atmos)
- "Invalid bitrate for channel layout": check bitrate guidelines or let DeeZy pick a smart default
- "FFmpeg not found": install FFmpeg and add to PATH
- "DEE executable not found": provide `--dee` or set in config

Debug mode

```bash
deezy --log-level debug encode ddp input.mkv
deezy --log-to-file encode ddp --keep-temp --temp-dir "C:\debug\" input.mkv
```

If you continue to have trouble, collect `--log-to-file` output and open an issue with a short reproduction and log snippets.
