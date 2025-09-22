# Dolby AC-4

Next-generation AC-4 codec with advanced features and flexibility.

Examples

```bash
deezy encode ac4 input.mkv
deezy encode ac4 --encoding-profile ims_music --bitrate 512 input.mkv
deezy encode ac4 --ims-legacy-presentation --bitrate 448 input.mkv
```

Key points

- Minimum channels: 6 (5.1) or higher
- TrueHD Atmos sources automatically retain immersive object metadata when converted to AC-4
- AC-4 supports multiple independent DRC profiles for various playback scenarios

Common options

- `--encoding-profile` (`ims`, `ims_music`)
- `--ims-legacy-presentation`
- `--bitrate`
- DRC options: `--ddp-drc`, `--flat-panel-drc`, `--home-theatre-drc`, `--portable-headphones-drc`, `--portable-speakers-drc`
