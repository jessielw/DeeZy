# config

```
usage: DeeZy config [-h] {generate,info,validate,list-presets} ...

positional arguments:
  {generate,info,validate,list-presets}
    generate            Generate configuration file
    info                Show configuration information
    validate            Validate configuration file
    list-presets        List available presets

options:
  -h, --help            show this help message and exit
```

Examples

```bash
deezy config generate
deezy config info
deezy config validate my-config.toml
deezy config list-presets
```
