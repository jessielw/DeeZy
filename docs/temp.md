# Temp Management

DeeZy organizes temporary artifacts under `%TEMP%/deezy/` by default. Each job gets its own folder.

Commands

```bash
deezy temp info
deezy temp clean --max-age 24
deezy temp clean --dry-run
```

Options: `--temp-dir`, `--reuse-temp-files`, `--keep-temp`

Notes about reuse

- Temporary artifacts are codec-scoped and tracked in a metadata file per input folder.
- `--reuse-temp-files` implies `--keep-temp` so artifacts persist.
