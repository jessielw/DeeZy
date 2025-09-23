# Bitrate Guidelines

Summary of common defaults and accepted ranges (configurable via `deezy-conf.toml`):

| Format | Layout           | Default   | Range     |
| ------ | ---------------- | --------- | --------- |
| DD     | MONO             | 192 kbps  | 96-640    |
| DD     | Stereo           | 224 kbps  | 96-640    |
| DD     | 5.1              | 448 kbps  | 224-640   |
| DDP    | MONO             | 64 kbps   | 32-1024   |
| DDP    | Stereo           | 128 kbps  | 96-1024   |
| DDP    | 5.1              | 192 kbps  | 192-1024  |
| DDP    | 7.1              | 384 kbps  | 384-1024  |
| Atmos  | Streaming        | 448 kbps  | 384-1024  |
| Atmos  | BluRay           | 1280 kbps | 1152-1664 |
| AC-4   | Immersive stereo | 256 kbps  | 64-320    |

_Note: All defaults are configurable via the configuration system._
