# find

```text {.scrollable-code-block}
usage: DeeZy find [-h] [-n] INPUT [INPUT ...]

positional arguments:
  INPUT       Input file paths or directories

options:
  -h, --help  show this help message and exit
  -n, --name  Only display names instead of full paths.
```

Examples

```bash
deezy find "**/*.mkv"
deezy find -n "**/*.mkv"
```

## Examples

- Find audio files in a folder (full paths):

```powershell
deezy find "C:\\media\\album\\"
```

- Only show filenames (no full path):

```powershell
deezy find -n "C:\\media\\album\\"
```
