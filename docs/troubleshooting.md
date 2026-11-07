# Troubleshooting

Common issues

- "truehdd decoder not found": install truehdd or add to PATH (only required for Atmos)
- "Invalid bitrate for channel layout": check bitrate guidelines or let DeeZy pick a smart default
- "FFmpeg not found": install FFmpeg and add to PATH
- "DEE executable not found": provide `--dee` or set in config. For the split DEE encoders this is the folder containing `dee_ddp_encoder`
- "License file does not exist" / "Provided license file does not enable this tool" (split DEE): DeeZy uses a `license.lic` beside the encoders, else a Dolby Media Encoder license (`dme_license.lic` beside them, or `%APPDATA%\Dolby Media Encoder\license.lic`). The license must cover the DEE release in use
- "... is not available with the split DEE encoders": that option needs the single `dee` executable (see the comparison table in Installation)
- "... requires the split DEE encoders": `--loudness-target`, `--peak-limit`, `--loudness-preset`, `--user-data` and `--bluray-secondary` only exist in the split encoders
- "Dolby Digital Plus 7.1 for online media is not available": a 7.1 source with no `--channels` resolves to 7.1. Pass `--channels 6`, or use `ddp-bluray` for 7.1 with the split encoders

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
deezy --config deezy-conf.toml --log-to-file encode ddp --keep-temp --temp-dir 'C:\short_tmp' input.mkv
```

Recommendation: prefer a short local `--temp-dir` base (for example `C:\deezy_tmp`) when
processing files with long UNC or deep output paths. DeeZy already uses short deterministic
job folders by default, but an explicit short base reduces the chance of hitting Windows
path-length limits.
