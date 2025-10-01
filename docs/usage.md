# Usage

### Core commands

- `deezy encode <format>` — encode to dd, ddp, ddp-bluray, atmos, ac4
- `deezy info <file>` — analyze audio tracks
- `deezy find <glob>` — find files using glob patterns
- `deezy config` — manage configuration
- `deezy temp` — temp folder management

### Global options

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

### Track selection

Use `--track-index` with `N`, `a:N` or `s:N` (stream index) to pick which audio to encode. See the `Track Selection` section in the original README for details.

Temp management

```bash
deezy temp info
deezy temp clean --max-age 24
```

### Notes on temp directories

Deezy creates per-job temporary directories under the configured temp base. By default
`--keep-temp` is false and each run uses a short unique per-run directory so concurrent
runs of the same file/track won't collide and can be removed automatically. When `--keep-temp`
is enabled, Deezy uses a stable per-track directory (useful for inspection or caching) but
this directory may be shared between runs of the same track and is not automatically removed.
