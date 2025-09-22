````markdown
# DeeZy CLI (Top-level)

Captured top-level help (for documentation):

```
usage: DeeZy [-h] [--version] [--config CONFIG_FILE]
             [--log-level {critical,error,warning,info,debug}] [--log-to-file] [--no-progress-bars]  
             {encode,find,info,config,temp} ...

positional arguments:
  {encode,find,info,config,temp}
    encode              Encode management
    find                Find management
    info                Info management
    config              Configuration management
    temp                Temporary folder management

options:
  -h, --help            show this help message and exit
  --version             show program's version number and exit
  --config CONFIG_FILE  Path to configuration file (default: deezy-conf.toml beside executable)      
  --log-level {critical,error,warning,info,debug}
                        Sets the log level (defaults to INFO).
  --log-to-file         Write log to file (defaults to input path with suffix of .log).
  --no-progress-bars    Disables progress bars on level INFO (disabled for DEBUG or higher).
```

Use the subcommand pages for per-command flags and examples.

````


## Examples (Quick)

- Encode a single file to Dolby Digital (DD):

```powershell
uv run python -m deezy encode dd "C:\media\song.wav"
```

- Encode a folder in parallel with 3 workers and write a batch summary JSON:

```powershell
uv run python -m deezy encode ddp "C:\media\album\" --max-parallel 3 --batch-summary-output --batch-output-dir "C:\out\batch"
```

- Use a preset named "web-128":

```powershell
uv run python -m deezy encode preset web-128 "C:\media\track1.wav"
```
