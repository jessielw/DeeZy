# Track Selection

DeeZy supports flexible track selection using FFmpeg-style notation.

Syntax

`N` — audio track N
`a:N` — explicit audio track
`s:N` — stream index N (any track type)

Examples

```bash
deezy encode ddp --track-index 0 input.mkv
deezy encode ddp --track-index a:1 input.mkv
deezy encode ddp --track-index s:2 input.mkv
```

Notes

- Use `s:N` when matching FFmpeg stream numbering is important.
- DeeZy validates `s:N` selects an audio stream and errors if not.
