# Temp Management

DeeZy organizes temporary artifacts in a deterministic per-input job folder under the
user's platform-specific application data directory by default (this uses
`platformdirs.user_data_dir()` under the hood). For example:

- Windows (typical): `%APPDATA%\DeeZy\deezy\<job-folder>`
- Linux (typical): `~/.local/share/deezy/<job-folder>`
- macOS (typical): `~/Library/Application Support/deezy/<job-folder>`

Each job gets its own short, deterministic folder (sanitized stem + short hash).
If you prefer a centralized base, pass `--temp-dir` to place per-input sub-folders under
your chosen location.

Commands

```bash
deezy temp info
deezy temp clean --max-age 24
deezy temp clean --dry-run
```

Options: `--temp-dir`, `--reuse-temp-files`, `--keep-temp`

Notes about reuse

- Temporary artifacts are codec-scoped and tracked in a metadata file per job folder
  (naming convention: `<output_stem>_metadata.json`). The metadata stores encoder-scoped
  signatures and the basename of the produced file; reuse checks look for the produced
  basename inside the same job folder.
- `--reuse-temp-files` implies `--keep-temp` so artifacts persist and can be reused by
  subsequent runs.

Path length and Windows UNC tips

- On Windows, very long input/output paths or an explicit `--temp-dir` with a long base
  can trigger problems when downstream tools (DEE) open JSON or temporary files.
  If you see errors opening generated JSON (especially with UNC paths like `\\?\UNC\...`),
  try one of the following:
  - Use a shorter `--temp-dir` base located on the same machine as the encoder (e.g. a
    short local path) so per-job folders remain under the Windows path length limits.
  - Use `--keep-temp` so you can inspect the produced temp folder and paths.
  - Run `deezy temp info` to inspect where DeeZy places job folders on your system.

The code creates short job-folder names to reduce path length pressure, but if you still
hit path-length limitations the explicit `--temp-dir` will be validated and may raise
an error; prefer a short base when providing an explicit temporary directory.
