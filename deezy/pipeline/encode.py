"""One encode: probe the source, plan the job, run the plan."""

from pathlib import Path

from deezy.config.manager import ConfigManager, get_config_manager
from deezy.dee.tools import find_license
from deezy.payloads.shared import CorePayload
from deezy.pipeline.plan import JobPlan, PlanContext, plan_job
from deezy.pipeline.run import check_input_file, run_plan, temp_dir_path
from deezy.pipeline.show import command_lines
from deezy.track_info.mediainfo import MediainfoParser
from deezy.utils.logger import logger


def _config() -> ConfigManager | None:
    try:
        return get_config_manager()
    except Exception:
        logger.debug("No configuration available; using the encoder defaults.")
        return None


def plan(payload: CorePayload) -> JobPlan:
    """Probe the source and plan its encode. Creates nothing."""
    file_input = Path(payload.file_input)
    check_input_file(file_input)
    namer = MediainfoParser(file_input, payload.track_index)
    info = namer.get_audio_track_info()
    ctx = PlanContext(
        namer=namer,
        temp_dir=temp_dir_path(
            file_input,
            payload.temp_dir,
            track_label=f"t{payload.track_index.index}",
            keep_temp=payload.keep_temp,
        ),
        license=find_license(Path(payload.dee_path)),
        config=_config(),
    )
    return plan_job(payload, info, ctx)


def encode(payload: CorePayload) -> Path:
    """
    Encode one source track and return the output path.

    A dry run prints the plan's command lines instead and runs nothing.
    """
    job = plan(payload)
    if payload.dry_run and not job.preview:
        for line in command_lines(job):
            print(line, flush=True)
        logger.info(f"Dry run: nothing was run. The output would be {job.output}")
        return job.output
    return run_plan(job, payload)
