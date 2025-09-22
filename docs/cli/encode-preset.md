````markdown
# deezy encode preset

Encode using a named preset. The preset contains format and option defaults. Use `deezy config list-presets` to list available presets.

Example:

```
deezy encode preset MyPreset --output ./out
```

## Examples

- List available presets and encode using one:

```powershell
uv run python -m deezy config list-presets
uv run python -m deezy encode preset web-128 "C:\\media\\track1.wav"
```

- Use a preset and override bitrate:

```powershell
uv run python -m deezy encode preset web-128 "C:\\media\\track1.wav" --bitrate 128
````
