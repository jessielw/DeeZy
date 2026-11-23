# DeeZy

[![Build and Release](https://github.com/jessielw/DeeZy/actions/workflows/release.yml/badge.svg)](https://github.com/jessielw/DeeZy/actions/workflows/release.yml) [![Tests](https://github.com/jessielw/DeeZy/actions/workflows/test.yml/badge.svg)](https://github.com/jessielw/DeeZy/actions/workflows/test.yml) [![ruff](https://github.com/jessielw/DeeZy/actions/workflows/ruff.yml/badge.svg?branch=main)](https://github.com/jessielw/DeeZy/actions/workflows/ruff.yml) [![PyPI](https://github.com/jessielw/DeeZy/actions/workflows/publish-pypi.yml/badge.svg)](https://github.com/jessielw/DeeZy/actions/workflows/publish-pypi.yml) ![PyPI - Downloads](https://img.shields.io/pypi/dw/deezy) [![Docs](https://github.com/jessielw/DeeZy/actions/workflows/mkdocs-deploy.yml/badge.svg)](https://github.com/jessielw/DeeZy/actions/workflows/mkdocs-deploy.yml) [![Static Badge](<https://img.shields.io/badge/BuyMeACoffee-BuyMeACoffee?style=plastic&logo=BuyMeACoffee&labelColor=hsl(210%2C%2060%25%2C%2050%25)&color=hsl(210%2C%2060%25%2C%2050%25)>)](https://buymeacoffee.com/jessielwilz) [![Static Badge](<https://img.shields.io/badge/Ko--fi-F16061?style=plastic&logo=Ko-Fi&labelColor=hsl(210%2C%2060%25%2C%2050%25)&color=hsl(210%2C%2060%25%2C%2050%25)>)](https://ko-fi.com/jessielw)

DeeZy is a compact CLI for encoding and batch-processing audio with the Dolby Encoding Engine (DEE): Dolby Digital, Dolby Digital Plus (also for Blu-ray and with Dolby Atmos), Dolby TrueHD (also with Dolby Atmos), Dolby AC-4 (channel-based, immersive stereo and with Dolby Atmos) and AAC.

- PyPI: https://pypi.org/project/deezy/

### Requirements

DeeZy 2.0 needs FFmpeg and the **DEE 6.7** command-line tools. truehdd decodes TrueHD Atmos sources, and the optional dee_shim adds DD+ 7.1 and the 7.1 Atmos modes and speeds up DD+ Atmos and TrueHD encodes. The single `dee` of DEE 5.2, which DeeZy 1.x used, is no longer supported; see [Migrating from 1.x](docs/migration.md).

### Documentation

- Online: https://jessielw.github.io/DeeZy/
- Migrating from 1.x: [docs/migration.md](docs/migration.md)
- Changes: [CHANGELOG.md](CHANGELOG.md)

### Quick commands

- Show version: `deezy --version`
- Show the tools DeeZy finds: `deezy tools`
- Encode with smart defaults: `deezy encode ddp input.mkv`
- List a format's data rates: `deezy bitrates ddp`

### Notes

- Docs source: `docs/` — the MkDocs site contains installation, configuration, presets, and a full CLI reference.
- Project metadata and build configuration are in `pyproject.toml`.

### Support

Love DeeZy? Fuel the project with a coffee! Small donations keep development brewing — genuinely appreciated.

[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://buymeacoffee.com/jessielwilz)
[![Support me on Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/jessielw)
