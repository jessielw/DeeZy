# info

Usage (captured):

```
usage: DeeZy info [-h] INPUT [INPUT ...]

positional arguments:
  INPUT       Input file paths or directories

options:
  -h, --help  show this help message and exit
```

Examples

```bash
deezy info input.mkv
deezy info *.mkv
```

## Examples

- Inspect a single file:

```powershell
uv run python -m deezy info "C:\\media\\song.wav"
```

- Inspect multiple files:

```powershell
uv run python -m deezy info "C:\\media\\album\\*"
```
