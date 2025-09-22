# Examples & Workflows

Movie encoding

```bash
deezy config generate
deezy info "Movie.Name.2023.UHD.mkv"
deezy encode preset --name bluray_atmos "Movie.Name.2023.UHD.mkv"
```

Batch TV series

```bash
deezy find "TV.Series.S01**/*.mkv"
deezy encode preset --name streaming_ddp "TV.Series.S01**/*.mkv"
```

Quality control and debugging

```bash
deezy --log-to-file encode ddp --keep-temp input.mkv
deezy temp clean --dry-run
```
