# DeeZy

DeeZy is a small, ergonomic CLI for encoding and batch-processing audio into common Dolby formats (DD, DDP, DDP-BluRay, Atmos, AC-4). The full user guide, examples, and a complete CLI reference have been moved to a searchable MkDocs site.

Documentation

- Online: https://jessielw.github.io/DeeZy/
- Local preview (PowerShell):

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install mkdocs mkdocs-material; mkdocs serve
```

Quick start

- Show version: `deezy --version`
- Encode a file with smart defaults: `deezy encode ddp input.mkv`

Development

- Project layout and build info are in `pyproject.toml`.
- Docs source lives in the `docs/` folder.

See the online docs for configuration, presets, and detailed CLI examples.
