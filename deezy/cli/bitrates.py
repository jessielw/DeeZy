"""`deezy bitrates`: the data rates each format and mode takes, and the default for each layout."""

from collections.abc import Iterable, Sequence
import textwrap

from deezy.config.manager import ConfigManager
from deezy.dee.spec import formats
from deezy.payloads.shared import ChannelBitrates

# the option that picks a mode, for the formats that have several
_MODE_OPTIONS = {
    "ddp-bluray": {"bluray_secondary": "--bluray-secondary"},
    "ddp-atmos": {
        mode: f"--atmos-mode {mode}" for mode in ("streaming", "standard", "bluray")
    },
    "aac": {mode: f"--aac-profile {mode}" for mode in ("aaclc", "heaac", "heaacv2")},
}
# the [default_bitrates.<format>] key of a channel layout
_LAYOUT_KEYS = {"1.0": "mono", "2.0": "stereo", "5.1": "surround", "7.1": "surroundex"}
WIDTH = 88


def config_key(fmt: str, mode: str, layout: str) -> str | None:
    """
    The [default_bitrates.<fmt>] key DeeZy reads for a layout, or None where
    it reads none (Blu-ray secondary audio keeps its own default).
    """
    if fmt == "ddp-bluray" and mode == "bluray_secondary":
        return None
    if fmt in ("ddp-atmos", "aac"):
        return mode
    if fmt == "ac4-ims":
        return "immersive_stereo"
    if fmt == "ac4-atmos":
        return "atmos"
    return _LAYOUT_KEYS.get(layout)


def rate_text(rates: Sequence[int]) -> str:
    """The rates, each run of three or more whole kbps as one range: '32, 40' or '448-2048'."""
    runs: list[list[int]] = []
    for rate in rates:
        if runs and rate == runs[-1][1] + 1:
            runs[-1][1] = rate
        else:
            runs.append([rate, rate])
    parts: list[str] = []
    for low, high in runs:
        if high - low >= 2:
            parts.append(f"{low}-{high}")
        else:
            parts.extend(str(rate) for rate in range(low, high + 1))
    return ", ".join(parts)


def _default_text(
    fmt: str, mode: str, layout: str, rates: ChannelBitrates, config
) -> str:
    """The default DeeZy uses for a layout, saying where a config changes it."""
    key = config_key(fmt, mode, layout)
    configured = None
    if config is not None and key is not None:
        try:
            configured = config.get_default_bitrate(fmt, key)
        except Exception:
            configured = None
    builtin = rates.default
    if not configured or configured == builtin:
        return f"default {builtin}"
    if rates.is_valid_bitrate(configured):
        return f"default {configured} (config; DeeZy's is {builtin})"
    # as when encoding: a rate DEE doesn't take becomes the closest one it does
    nearest = rates.get_closest_bitrate(configured)
    return f"default {nearest} (config asks {configured}; DeeZy's is {builtin})"


def bitrate_lines(
    names: Iterable[str] | None = None, config: ConfigManager | None = None
) -> list[str]:
    """
    For each format in ``names`` (every format when empty), each mode with the
    option that picks it, and each layout's default and rates (kbps).
    """
    table = formats()
    lines: list[str] = []
    for name in names or table:
        spec = table[name]
        if lines:
            lines.append("")
        for index, (mode_name, mode) in enumerate(spec.modes.items()):
            option = _MODE_OPTIONS.get(name, {}).get(mode_name)
            title = name if option is None else f"{name} {option}"
            if len(spec.modes) > 1 and index == 0:
                title += " (default)"
            if all(layout.rates is None for layout in mode.layouts.values()):
                lines.append(f"{title}: lossless, no data rate")
                continue
            lines.append(title)
            for layout_name, layout in mode.layouts.items():
                rates = layout.rates
                if rates is None:
                    continue
                head = f"  {layout_name:<5} " + _default_text(
                    name, mode_name, layout_name, rates, config
                )
                if layout.needs_shim:
                    head += ", needs dee_shim"
                lines.extend(
                    textwrap.wrap(
                        rate_text(rates.choices),
                        width=WIDTH,
                        initial_indent=f"{head}: ",
                        subsequent_indent=" " * 8,
                        break_on_hyphens=False,
                    )
                )
    return lines
