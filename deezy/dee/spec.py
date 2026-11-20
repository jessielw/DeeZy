"""
The formats DeeZy encodes with DEE 6.7, and what each encoder takes.

The accepted and automatic data rates and each tool's options come from
``data/dee_6_7_0.json``, which ``scripts/probe_dee.py`` writes by running the
encoders. DeeZy's own default rates stay here: Dolby's automatic rates are half
of them or less, and following those would lower every default without warning.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from importlib import resources
import json
from typing import Any

from deezy.payloads.shared import ChannelBitrates

FIXTURE = "dee_6_7_0.json"

# DEE encodes at 48 kHz, and every delay here is in samples at that rate
SAMPLE_RATE = 48000
# DD, DD+ and DD+ JOC start this many samples late
DDP_DELAY_SAMPLES = 256
# and this many more when DEE changes the channel count (7.1 to 5.1, 2.0 to 1.0)
CHANNEL_CHANGE_SAMPLES = 32

# dee_shim's DD+ 7.1 as E-AC-3; DEE alone has no such mode, so the probe has no
# list for it
_SHIM_DDP_71_RATES = (384, 448, 504, 576, 640, 704, 768, 832, 896, 960, 1008, 1024)


@cache
def fixture() -> Mapping[str, Any]:
    """The probe's record of DEE 6.7.0, as packaged with DeeZy."""
    data = resources.files("deezy.dee") / "data" / FIXTURE
    return json.loads(data.read_text(encoding="utf-8"))


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """One DEE 6.7 executable, as the probe found it."""

    name: str
    has_temp_dir: bool
    has_input_format: bool
    # what the tool uses when --start and --loudness-management are left out
    start_default: str
    loudness_default: str
    # the --loudness-management modes it accepts; 'skip:dialnorm' is the skip
    # that writes a given dialnorm
    loudness_modes: frozenset[str]

    @property
    def single_pass(self) -> bool:
        """Whether a skip mode lets the tool encode without buffering the PCM."""
        return bool(self.loudness_modes & {"skip", "skip:dialnorm"})


@dataclass(frozen=True, slots=True)
class LayoutSpec:
    rates: ChannelBitrates
    # DEE alone can't encode this layout; dee_shim can
    needs_shim: bool = False


@dataclass(frozen=True, slots=True)
class ModeSpec:
    # the encoder's -e mode, or '' for a tool that takes none
    dee_mode: str
    layouts: Mapping[str, LayoutSpec]


@dataclass(frozen=True, slots=True)
class FormatSpec:
    name: str
    tool: ToolSpec
    # by DeeZy's name for the mode; the first is the default
    modes: Mapping[str, ModeSpec]
    # accepted output suffixes; the first is the default
    extensions: tuple[str, ...]
    # samples at 48 kHz that DEE starts the encode late by
    delay_samples: int
    # and the extra samples when DEE itself changes the channel count
    channel_change_samples: int

    @property
    def extension(self) -> str:
        return self.extensions[0]

    def mode(self, name: str | None = None) -> ModeSpec:
        if name is None:
            return next(iter(self.modes.values()))
        try:
            return self.modes[name]
        except KeyError:
            raise KeyError(f"{self.name} has no mode {name!r}") from None

    def layout(self, layout: str, mode: str | None = None) -> LayoutSpec:
        layouts = self.mode(mode).layouts
        try:
            return layouts[layout]
        except KeyError:
            raise KeyError(
                f"{self.name} has no {layout} layout"
                + (f" in mode {mode!r}" if mode else "")
            ) from None

    def rates(self, layout: str, mode: str | None = None) -> ChannelBitrates:
        return self.layout(layout, mode).rates


@cache
def tool(name: str) -> ToolSpec:
    node = fixture()["tools"][name]
    return ToolSpec(
        name=name,
        has_temp_dir=node["has_temp_dir"],
        has_input_format=node["has_input_format"],
        start_default=node["start_default"],
        loudness_default=node["loudness_default"],
        # the probe tried 'skip:dialnorm=-31'; the value is not part of the mode
        loudness_modes=frozenset(
            mode.split("=")[0]
            for mode, accepted in node["loudness_modes"].items()
            if accepted
        ),
    )


def _probed(default: int, *path: str) -> LayoutSpec:
    """The rates the probe found DEE accepts, with DeeZy's default."""
    node = fixture()["rates"]
    for key in path:
        node = node[key]
    rates = ChannelBitrates(
        default=default, choices=tuple(node["rates"]), dee_auto=node["auto"]
    )
    if default not in rates.choices:
        raise ValueError(f"default {default} is not a rate DEE takes for {path}")
    return LayoutSpec(rates)


def _ddp(mode: str, defaults: Mapping[str, int]) -> ModeSpec:
    """A dee_ddp_encoder mode, with DeeZy's default rate for each layout."""
    return ModeSpec(
        mode,
        {
            layout: _probed(default, "dee_ddp_encoder", mode, layout)
            for layout, default in defaults.items()
        },
    )


@cache
def formats() -> Mapping[str, FormatSpec]:
    ddp_tool = tool("dee_ddp_encoder")
    ddp_exts = (".ec3", ".eac3")
    ddp_mode = _ddp("ddp", {"1.0": 64, "2.0": 128, "5.1": 192})
    table = (
        FormatSpec(
            "dd",
            ddp_tool,
            {"dd": _ddp("dd", {"1.0": 192, "2.0": 224, "5.1": 448})},
            (".ac3",),
            DDP_DELAY_SAMPLES,
            CHANNEL_CHANGE_SAMPLES,
        ),
        FormatSpec(
            "ddp",
            ddp_tool,
            {
                "ddp": ModeSpec(
                    "ddp",
                    {
                        **ddp_mode.layouts,
                        "7.1": LayoutSpec(
                            ChannelBitrates(default=384, choices=_SHIM_DDP_71_RATES),
                            needs_shim=True,
                        ),
                    },
                )
            },
            ddp_exts,
            DDP_DELAY_SAMPLES,
            CHANNEL_CHANGE_SAMPLES,
        ),
        FormatSpec(
            "ddp-bluray",
            ddp_tool,
            {
                "bluray": _ddp("bluray", {"7.1": 1280}),
                "bluray_secondary": _ddp("bluray_secondary", {"2.0": 192, "5.1": 192}),
            },
            ddp_exts,
            DDP_DELAY_SAMPLES,
            CHANNEL_CHANGE_SAMPLES,
        ),
        FormatSpec(
            "ddp-atmos",
            tool("dee_ddpjoc_encoder"),
            {
                "streaming": ModeSpec(
                    "ddpjoc",
                    {"atmos": _probed(448, "dee_ddpjoc_encoder", "ddpjoc")},
                ),
                # DEE's own Blu-ray mode gives a 5.1.2 bed; dee_shim gives 7.1
                "bluray": ModeSpec(
                    "bluray",
                    {
                        "atmos": LayoutSpec(
                            _probed(1280, "dee_ddpjoc_encoder", "bluray").rates,
                            needs_shim=True,
                        )
                    },
                ),
            },
            ddp_exts,
            DDP_DELAY_SAMPLES,
            # an Atmos master's channel count is not DEE's to change
            0,
        ),
        FormatSpec(
            "ac4-ims",
            tool("dee_ac4ims_encoder"),
            # the -e mode= option picks general or music, so the tool has no mode
            {"ims": ModeSpec("", {"2.0": _probed(256, "dee_ac4ims_encoder")})},
            (".ac4",),
            # unmeasured: no AC-4 decoder here, so DeeZy keeps 1.5.0's value
            DDP_DELAY_SAMPLES,
            0,
        ),
    )
    return {spec.name: spec for spec in table}


def get_format(name: str) -> FormatSpec:
    try:
        return formats()[name]
    except KeyError:
        raise KeyError(f"no DEE format {name!r}") from None
