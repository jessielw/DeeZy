# Output Filename Templates

Use `--output-template` to generate consistent output filenames when `--output` is not provided.

Example

```
deezy encode ddp --output-template "{title}_{year}_{stem}_{channels}_{delay}" input.mkv
```

Supported tokens: `{title}`, `{year}`, `{stem}`, `{source}`, `{lang}`, `{channels}`, `{worker}`, `{delay}`, `{opt-delay}`

_`opt-delay` will return nothing if delay is equal to 0._

Use `--output-preview` to render a template without running the job.
