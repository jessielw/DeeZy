````markdown
# deezy encode ac4

Uses the standard encode options. Run `deezy encode ac4 --help` locally for AC-4 specific options.

## Examples

- Encode AC-4 in streaming mode (basic):

```powershell
uv run python -m deezy encode ac4 "C:\\media\\song.wav" --bitrate 384
```

- Encode using preset options for AC-4 (if preset exists):

```powershell
uv run python -m deezy encode preset my-ac4-preset "C:\\media\\song.wav"
```
````
