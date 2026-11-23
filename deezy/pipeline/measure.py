"""One loudness measurement: probe the source, plan it, run it, report it."""

from deezy.payloads.measure import MeasurePayload
from deezy.pipeline.encode import probe
from deezy.pipeline.plan import JobPlan, plan_measure
from deezy.pipeline.run import run_measure
from deezy.pipeline.show import command_lines
from deezy.utils.logger import logger

# DEE's names for what it measured
LAYOUTS = {
    "mono": "1.0",
    "stereo": "2.0",
    "multichannel_5_1": "5.1",
    "multichannel_7_1": "7.1",
}
RENDERS = {"binaural": "Atmos, binaural render", "multichannel": "Atmos, 5.1 render"}


def plan(payload: MeasurePayload) -> JobPlan:
    """Probe the source and plan its measurement. Creates nothing."""
    info, ctx = probe(payload, "m")
    return plan_measure(payload, info, ctx)


def measure(payload: MeasurePayload) -> dict | None:
    """
    Measure one source track and return DEE's loudness manifest.

    A dry run prints the plan's command lines instead, runs nothing and
    returns None.
    """
    job = plan(payload)
    if payload.dry_run:
        for line in command_lines(job):
            print(line, flush=True)
        logger.info("Dry run: nothing was run.")
        return None
    return run_measure(job, payload)


def _number(value: object, unit: str) -> str:
    if not isinstance(value, int | float):
        return "n/a"
    return f"{value:.1f} {unit}"


def _peak(values: object, unit: str) -> str:
    if not isinstance(values, list) or not values:
        return "n/a"
    return _number(max(values), unit)


def _block(title: str, result: dict) -> list[str]:
    gating = result.get("integrated_loudness_gating")
    loudness = _number(result.get("integrated_loudness"), "LKFS")
    if gating:
        loudness += f" ({gating}-gated)"
    lines = [
        f"  {title}",
        f"    Integrated loudness  {loudness}",
    ]
    # DEE writes -1 when Dialogue Intelligence is off or a regulation preset
    # gates on level
    speech = result.get("integrated_speech_percentage")
    measured = not (isinstance(speech, int | float) and speech < 0)
    lines.append(
        f"    Speech               {_number(speech, '%') if measured else 'not measured'}"
    )
    return [
        *lines,
        f"    Loudness range       "
        f"{_number(result.get('integrated_loudness_range'), 'LU')}",
        f"    True peak            {_peak(result.get('true_peaks'), 'dBTP')}",
        f"    Sample peak          {_peak(result.get('sample_peaks'), 'dBFS')}",
    ]


def summary(manifest: dict) -> list[str]:
    """
    The lines that report a loudness manifest: one block per measured layout
    or Atmos render.
    """
    lines: list[str] = []
    for track in manifest.get("loudness_manifest", {}).get("tracks", []):
        for name, result in (track.get("channel_based_loudness") or {}).items():
            lines += _block(LAYOUTS.get(name, str(name)), result)
        for name, result in (track.get("atmos_loudness") or {}).items():
            lines += _block(RENDERS.get(name, str(name)), result)
    return lines
