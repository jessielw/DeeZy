# Tips & Best Practices

Short, practical guidance to get the most out of DeeZy.

- Use presets for repeatable, shareable workflows. Put presets in your global config and reference them with `deezy encode preset --name <name>`.

- When running batch jobs, set `--max-parallel` to a conservative value (1-4) and use `--limit-ffmpeg` / `--limit-dee` to avoid saturating systems.

- Enable `--batch-summary-output` during testing to produce JSON results you can ingest into automation or QA pipelines.

- To debug encoding failures, run with `--dry-run` to see the commands DeeZy would run, `--keep-logs` to keep what the tools print, or `--keep-temp` to inspect intermediate files, and re-run with `--reuse-temp-files` where possible.

- For CI environments, use `--output-preview` to verify templates and paths without writing outputs.

- When converting many files, consider running jobs on a dedicated machine with isolated `--working-dir` to keep logs and batch-results tidy.

- Use `deezy find` and `deezy info` to validate inputs before running large batches.

- Keep `deezy-conf.toml` under version control for reproducible results across machines.

- If you rely on external executables (FFmpeg, DEE, truehdd, dee_shim), set full paths via `--ffmpeg` / `--dee` / `--truehdd` / `--dee-shim` in CI to avoid path resolution issues. `deezy tools` shows what DeeZy finds.
