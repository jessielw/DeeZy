# deezy encode preset

Encode using a named preset. The preset contains format and option defaults. Use `deezy config list-presets` to list available presets.

Example:

```
deezy encode preset MyPreset --output ./out
```

## Examples

- List available presets and encode using one:

```bash
deezy config list-presets
deezy encode preset web-128 "C:\\media\\track1.wav"
```

- Use a preset and override bitrate:

```bash
deezy encode preset web-128 --bitrate 128 "C:\\media\\track1.wav"
```
