# Output Filename Templates

Use `--output-template` to generate consistent output filenames when `--output` is not provided.

Example

```
deezy encode ddp --output-template "{title}_{year}_{stem}_{channels}_{delay}" input.mkv
```

Supported tokens: `{title}`, `{year}`, `{stem}`, `{source}`, `{lang}`, `{channels}`, `{worker}`, `{delay}`

Use `--output-preview` to render a template without running the job.
