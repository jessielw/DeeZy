# temp

DeeZy temporary folder management commands.

Usage (captured):

```
usage: DeeZy temp [-h] {clean,info} ...

positional arguments:
  {clean,info}
    clean       Clean DeeZy temp folders
    info        Show temp folder information

options:
  -h, --help    show this help message and exit
```

Examples

```bash
deezy temp info
deezy temp clean --max-age 24
```

## Examples

- Show temp folder information:

```powershell
uv run python -m deezy temp info
```

- Clean temp folders older than 48 hours:

```powershell
uv run python -m deezy temp clean --max-age 48
```
