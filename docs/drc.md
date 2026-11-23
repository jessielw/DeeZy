# Dynamic Range Compression (DRC)

The DRC profiles are `film_standard`, `film_light` (the default),
`music_standard`, `music_light`, `speech` and `none` (no compression).

| Format | Options |
| --- | --- |
| `dd`, `ddp`, `ddp-bluray`, `ddp-atmos` | `--drc-line-mode`, `--drc-rf-mode` |
| `ac4`, `ac4-atmos` | `--flat-panel-drc`, `--home-theatre-drc`, `--portable-headphones-drc`, `--portable-speakers-drc` |
| `ac4-ims` | the four AC-4 device options and `--ddp-drc` |
| `thd`, `thd-atmos` | `--drc`, for every presentation in the stream |

Channel-based AC-4 (`ac4`) has no `none` profile, and TrueHD's `none` needs
[dee_shim](dee-shim.md). AAC has no DRC options.

```bash
deezy encode ddp --drc-line-mode film_light --drc-rf-mode music_light input.mkv
deezy encode thd --drc music_light input.mkv
```
