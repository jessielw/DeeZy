import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import oslex2

from deezy.utils.utils import WORKING_DIRECTORY


class BatchResult:
    """Represents the result of processing a single file."""

    def __init__(
        self,
        input_file: Path,
        file_id: str,
        start_time: float | None = None,
        log_file: Path | None = None,
    ) -> None:
        self.input_file = input_file
        self.file_id = file_id
        self.start_time = start_time or time.time()
        self.end_time: float | None = None
        self.output_file: Path | None = None
        self.status: str = "processing"
        self.error: str | None = None
        self.log_file: Path | None = log_file

    def mark_success(self, output_file: Path):
        """Mark this result as successful."""
        self.end_time = time.time()
        self.output_file = output_file
        self.status = "success"

    def mark_failure(self, error: str):
        """Mark this result as failed."""
        self.end_time = time.time()
        self.error = error
        self.status = "failed"

    def mark_skipped(self, reason: str):
        """Mark this result as skipped (not processed due to existing output or other checks)."""
        self.end_time = time.time()
        self.error = reason
        self.status = "skipped"

    @property
    def duration_seconds(self) -> float | None:
        """Get processing duration in seconds."""
        if self.end_time:
            return round(self.end_time - self.start_time, 2)
        return None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "input_file": str(self.input_file),
            "output_file": str(self.output_file) if self.output_file else None,
            "log_file": str(self.log_file) if self.log_file else None,
            "status": self.status,
            "file_id": self.file_id,
            "start_time": datetime.fromtimestamp(
                self.start_time, timezone.utc
            ).isoformat(),
            "end_time": datetime.fromtimestamp(self.end_time, timezone.utc).isoformat()
            if self.end_time
            else None,
            "duration_seconds": self.duration_seconds,
            "error": self.error,
        }


class BatchResultsManager:
    """Manages batch processing results and generates summary reports."""

    def __init__(
        self,
        command_args: list[str],
        total_files: int,
        max_parallel: int,
        output_dir: Path | None = None,
    ) -> None:
        self.command_args = command_args
        self.total_files = total_files
        self.max_parallel = max_parallel
        self.start_time = time.time()
        self.results: list[BatchResult] = []
        self.output_dir = output_dir or WORKING_DIRECTORY

        # ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _reconstruct_command(self) -> str:
        """Reconstruct command with proper quoting for spaces."""
        # use oslex2.join for proper cross-platform quoting
        return oslex2.join(["deezy"] + self.command_args)

    def add_result(self, result: BatchResult):
        """Add a batch result."""
        self.results.append(result)

    def create_result(
        self, input_file: Path, file_id: str, log_file: Path | None = None
    ) -> BatchResult:
        """Create and add a new batch result. Optionally attach a log file path."""
        result = BatchResult(input_file, file_id, log_file=log_file)
        self.add_result(result)
        return result

    def get_summary_stats(self) -> dict[str, Any]:
        """Get summary statistics."""
        successful = [r for r in self.results if r.status == "success"]
        failed = [r for r in self.results if r.status == "failed"]
        skipped = [r for r in self.results if r.status == "skipped"]

        total_duration = None
        if self.results and all(r.end_time for r in self.results):
            total_duration = round(time.time() - self.start_time, 2)

        return {
            "total_files": self.total_files,
            "successful": len(successful),
            "failed": len(failed),
            "skipped": len(skipped),
            "processing": len([r for r in self.results if r.status == "processing"]),
            "total_duration_seconds": total_duration,
            "max_parallel": self.max_parallel,
        }

    def generate_filename(self) -> str:
        """Generate a unique filename for this batch."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"deezy-batch-{timestamp}.json"

    def save_results(self) -> Path:
        """Save batch results to JSON file."""
        filename = self.generate_filename()
        output_file = self.output_dir / filename

        batch_data = {
            "batch_info": {
                "timestamp": datetime.fromtimestamp(
                    self.start_time, timezone.utc
                ).isoformat(),
                "command": self._reconstruct_command(),
                **self.get_summary_stats(),
            },
            "results": [result.to_dict() for result in self.results],
        }

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(batch_data, f, indent=2, ensure_ascii=False)

        return output_file
