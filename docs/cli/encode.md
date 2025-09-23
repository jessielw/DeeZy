# encode

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

```bash
deezy encode dd "C:\\media\\song.wav"
```

- Batch encode multiple files in a folder, limit concurrency and keep temp files for debugging:

```bash
deezy encode ddp --max-parallel 2 --keep-temp --batch-summary-output "C:\\media\\album\\*.mkv"
```

- Encode using an output template (preview without writing):

```bash
deezy encode dd --output-template "{title}_{delay}_{channels}.dd" --output-preview "C:\\media\\album\\*.mkv"
```
