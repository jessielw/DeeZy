# Usage

Core commands

- `deezy encode <format>` — encode to dd, ddp, ddp-bluray, atmos, ac4
- `deezy info <file>` — analyze audio tracks
- `deezy find <glob>` — find files using glob patterns
- `deezy config` — manage configuration
- `deezy temp` — temp folder management

Global options

`--config`, `--log-level`, `--log-to-file`, `--no-progress-bars`, `--version`

Examples

```bash
# Encode to DDP (smart defaults)
deezy encode ddp input.mkv

# Use preset
deezy encode preset --name streaming_ddp input.mkv

# Batch encode
deezy --log-to-file encode ddp --max-parallel 4 *.mkv

# Inspect tracks
deezy info input.mkv
```

Track selection

Use `--track-index` with `N`, `a:N` or `s:N` (stream index) to pick which audio to encode. See the `Track Selection` section in the original README for details.

Temp management

```bash
deezy temp info
deezy temp clean --max-age 24
```
