# encode

Usage (captured):

```
usage: DeeZy encode [-h] {dd,ddp,ddp-bluray,atmos,ac4,preset} ...
```

Formats

- `dd` — Dolby Digital (see `../formats/dd.md`)
- `ddp` — Dolby Digital Plus (see `../formats/ddp.md`)
- `ddp-bluray` — DDP BluRay (see `../formats/ddp-bluray.md`)
- `atmos` — Dolby Atmos (see `../formats/atmos.md`)
- `ac4` — Dolby AC-4 (see `../formats/ac4.md`)
- `preset` — Encode using a preset defined in config (see `../presets.md`)

Run `deezy encode <format> --help` to see format-specific options.

## Examples

- Basic encode (auto-output path):

```powershell
uv run python -m deezy encode dd "C:\\media\\song.wav"
```

- Batch encode multiple files in a folder, limit concurrency and keep temp files for debugging:

```powershell
uv run python -m deezy encode ddp "C:\\media\\album\\" --max-parallel 2 --keep-temp --batch-summary-output
```

- Encode using an output template (preview without writing):

```powershell
uv run python -m deezy encode dd "C:\\media\\song.wav" --output-template "{title}_{delay}_{channels}.dd" --output-preview
```
