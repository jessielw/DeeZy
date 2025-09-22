# Batch & Retention

When `--batch-summary-output` is enabled, DeeZy writes a JSON summary per batch containing `batch_info` and `results` array.

`batch_info` includes: `timestamp`, `command`, `total_files`, `successful`, `failed`, `skipped`, `processing`, `total_duration_seconds`, `max_parallel`.

Each `results` entry includes: `input_file`, `output_file`, `log_file`, `status`, `file_id`, `start_time`, `end_time`, `duration_seconds`, `error`.

Retention

- `--max-logs` and `--max-batch-results` control how many files are kept in working dir.

A sample file is available at `example_json_flows/sample_batch_results.json` in the repository.
