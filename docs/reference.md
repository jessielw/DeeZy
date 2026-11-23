# Reference

This page collects reference material: CLI options, batch JSON schema, and filename template tokens.

Batch summary JSON (top-level keys)

- `batch_info`: timestamp, command, total_files, successful, failed, skipped, total_duration_seconds, max_parallel
- `results`: array of per-file objects with `input_file`, `output_file`, `status`, `start_time`, `end_time`, `duration_seconds`, `error`

Output template tokens

- `{title}`, `{year}`, `{stem}`, `{stem-cleaned}`, `{source}`, `{lang}`, `{channels}`, `{worker}`, `{delay}`, `{opt-delay}`

Every command's options are in the [CLI reference](cli/top-level.md), and `deezy <command> --help` prints them.
