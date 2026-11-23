# Troubleshooting

Start with `deezy tools`. It shows the FFmpeg, DEE tools (and their license),
truehdd and dee_shim an encode would use, with each one's version and path, and
exits with 1 when an encode couldn't run.

## Common messages

- "Failed to detect required dependencies: ...": DeeZy found no FFmpeg or DEE
  tools. Give the path with `--ffmpeg` or `--dee`, or under `[dependencies]` in
  the config. See [Installation](installation.md).
- "truehdd is needed to decode a TrueHD Atmos source, and DeeZy didn't find
  it": give truehdd's path with `--truehdd` or under `[dependencies]`. Only a
  TrueHD Atmos source needs it.
- "Configured dependency path does not exist: ...": a path given on the command
  line or in the config is wrong.
- "DeeZy needs the DEE 6.7 command-line tools, but '...' reports ...": the DEE
  DeeZy found is another version, such as the single `dee` of DEE 5.2. Point
  `--dee` at the DEE 6.7 tools' folder, and see
  [Migrating from 1.x](migration.md).
- "License file does not exist" or "Provided license file does not enable this
  tool": the DEE tools found no license that covers them. See
  [DEE license](installation.md#dee-license).
- "... needs dee_shim (0.2.1 or newer)": the encode needs
  [dee_shim](dee-shim.md) (DD+ 7.1, `ddp-atmos --atmos-mode standard` or
  `bluray`, TrueHD `--drc none`). Give its path with `--dee-shim`, or choose a
  layout or mode DEE encodes alone.
- "Up-mixing is not supported.": the layout asked for has more channels than the
  source.
- "Bitrate ... is invalid for this configuration. Using the next closest allowed
  bitrate: ...": `deezy bitrates <format>` lists the rates DEE takes.
- "Output already exists: ...": the job is skipped. `--overwrite` replaces the
  file.
- "The output would overwrite its own source" or "... is also the output of ...
  in this run": give each job its own name with `--output`, or an
  `--output-template` that tells them apart.
- MediaInfo shows a 7.1 DD+ Atmos stream as plain Dolby Digital Plus: see
  [ddp-atmos](formats/ddp-atmos.md#mediainfo).

## Debugging

```bash
deezy encode ddp --dry-run input.mkv
deezy encode ddp --keep-logs input.mkv
deezy --log-level debug encode ddp input.mkv
deezy --log-to-file encode ddp --keep-temp --temp-dir "C:\debug" input.mkv
```

- `--dry-run` probes the source and prints the FFmpeg, truehdd and DEE commands
  without running them. `--print-commands` prints them as they start.
- `--keep-logs` writes everything the tools print to `<output>.log` beside the
  output.
- `--keep-temp` keeps the job's temp files to look at.

If it still fails, open an issue with a short reproduction and the
`--keep-logs` log.

## Windows long paths and UNC

If DEE or other tools fail to open temp files on Windows (especially with UNC
paths like `\\?\UNC\...`), check for path-length problems and use a short temp
base while debugging. Useful PowerShell checks:

```powershell
# Check that the path exists (normalize \?\ prefix first if present)
$p = '\\?\UNC\SHARE\very\long\path\file.wav'
$norm = if ($p -like '\\?\*') { $p -replace '^\\\\\?\\', '' } else { $p }
Test-Path $norm

# Show total path length
$norm.Length

# If a path is too long, run with a short temp dir for debugging:
deezy --config deezy-conf.toml --log-to-file encode ddp --keep-temp --temp-dir 'C:\short_tmp' input.mkv
```

Prefer a short local `--temp-dir` base (for example `C:\deezy_tmp`) when
processing files with long UNC or deep output paths. DeeZy already uses short
job folders, but a short base makes Windows path-length limits less likely.
