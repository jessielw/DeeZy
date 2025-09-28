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

Windows long-path / UNC diagnostics

If DEE or other tools fail to open generated JSON or temp files on Windows (especially
when using UNC paths with `\\?\UNC\...`), check for path-length problems and use a
short temporary base while debugging. Useful PowerShell checks:

```powershell
# Check that the path exists (normalize \?\ prefix first if present)
$p = '\\?\UNC\SHARE\very\long\path\file.ddp.json'
$norm = if ($p -like '\\?\*') { $p -replace '^\\\\\?\\', '' } else { $p }
Test-Path $norm

# Show total path length
$norm.Length

# If a path is too long, run with a short temp dir for debugging:
deezy encode ddp --keep-temp --temp-dir 'C:\short_tmp' --log-to-file --config deezy-conf.toml encode ddp input.mkv
```

Recommendation: prefer a short local `--temp-dir` base (for example `C:\deezy_tmp`) when
processing files with long UNC or deep output paths. DeeZy already uses short deterministic
job folders by default, but an explicit short base reduces the chance of hitting Windows
path-length limits.
