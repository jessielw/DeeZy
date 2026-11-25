"""
Command lines for the DEE 6.7 encoders.

Options the tools do not offer raise `UnsupportedDeeFeatureError` rather than
being dropped, so an encode never comes out different from what was asked for.
Nothing here touches the disk.
"""

from dataclasses import dataclass, replace
from pathlib import Path

from deezy.bitrate import Bitrate, SubstreamBitrate
from deezy.dee.shim import MIN_SHIM_TEXT, DeeShim
from deezy.dee.tools import dee_tool
from deezy.delay import Delay
from deezy.enums.ac4 import Ac4EncodingProfile
from deezy.enums.atmos import AtmosMode
from deezy.enums.shared import (
    DDEncodingMode,
    DeeDRC,
    DeeFPS,
    LoudnessPreset,
    StereoDownmix,
)
from deezy.exceptions import UnsupportedDeeFeatureError
from deezy.payloads.aac import AacPayload
from deezy.payloads.ac4 import Ac4AtmosPayload, Ac4ChannelPayload, Ac4Payload
from deezy.payloads.atmos import AtmosPayload
from deezy.payloads.dd import DDPayload
from deezy.payloads.ddp import DDPPayload
from deezy.payloads.measure import MeasurePayload
from deezy.payloads.shared import LoudnessPayload
from deezy.payloads.thd import TrueHDAtmosPayload, TrueHDPayload
from deezy.utils.logger import logger
from deezy.utils.paths import long_path_str

DDP_TOOL = "dee_ddp_encoder"
DDP_JOC_TOOL = "dee_ddpjoc_encoder"
AC4_IMS_TOOL = "dee_ac4ims_encoder"
AC4_TOOL = "dee_ac4_encoder"
AC4_ATMOS_TOOL = "dee_ac4ajoc_encoder"
AAC_TOOL = "dee_aac_encoder"
MEASURE_TOOL = "dee_measure_loudness"
# how a refusal names the dee_shim DeeZy needs
NEEDS_SHIM = f"dee_shim ({MIN_SHIM_TEXT} or newer)"
# dee_shim opens the 7.1 of DEE's meter, which its CLI refuses
MEASURE_71_SHIM_ARGS = ("--layout", "7.1")
THD_TOOL = "dee_dthd_encoder"
# dee_shim's DD+ 7.1: an E-AC-3 5.1 independent substream plus a dependent one
# for the backs
DDP_71_SHIM_ARGS = ("--layout", "7.1/eac3")
# 7.0: dee_shim codes the 7.1 slots without the LFE, as E-AC-3 or (Blu-ray)
# an AC-3 core plus an E-AC-3 dependent substream. DEE has neither
DDP_70_SHIM_ARGS = ("--layout", "7.0/eac3")
BLURAY_70_SHIM_ARGS = ("--layout", "7.0")
# dee_shim's DD+ Atmos 7.1 backbones (DEE's own Blu-ray mode gives a 5.1.2
# one): an AC-3 core plus an E-AC-3 dependent substream, or E-AC-3 only.
# Streaming keeps DEE's 5.1
DDPJOC_SHIM_LAYOUTS = {
    AtmosMode.BLURAY: ("--layout", "7.1"),
    AtmosMode.STANDARD: ("--layout", "7.1/eac3"),
}


@dataclass(frozen=True, slots=True)
class DeeTools:
    """The folder of DEE tools, and a license to pass when they won't find one."""

    dee_dir: Path
    license: Path | None = None
    # runs the DD+ Atmos and TrueHD encoders, and DD+ 7.1, when DeeZy has it
    shim: DeeShim | None = None


def _through_shim(tools: DeeTools, argv: list[str], *shim_args: str) -> list[str]:
    """
    ``argv`` run through dee_shim, when DeeZy has it. With no options of its
    own the shim encodes what DEE does, byte for byte, and its DD+ Atmos and
    TrueHD encoders run faster on AMD Zen CPUs (it replaces a slow zero-fill).
    """
    return list(tools.shim.argv(argv, *shim_args)) if tools.shim else argv


@dataclass(frozen=True, slots=True)
class DeeFiles:
    """The files one DEE run reads and writes."""

    # a file, or DEE's name for a stream it reads (such as a named pipe)
    input: Path | str
    # where DEE encodes to, inside the job's temp directory
    output: Path
    temp_dir: Path
    # replaces the encoder's usual --input-format (raw PCM from a pipe)
    input_format: str | None = None


def _flag(value: bool) -> str:
    return "1" if value else "0"


def _options(options: dict[str, str]) -> str:
    """DEE's `key=value:key=value` option list."""
    return ":".join(f"{key}={value}" for key, value in options.items())


def ddp_command(
    tools: DeeTools,
    payload: DDPayload | DDPPayload,
    files: DeeFiles,
    *,
    downmix_mode_off: bool,
    bitrate: Bitrate,
    fps: DeeFPS,
    delay: Delay,
    dd_mode: DDEncodingMode,
    lfe: bool = True,
) -> list[str]:
    """
    A Dolby Digital or Dolby Digital Plus encode with dee_ddp_encoder. DD+ 7.1
    as E-AC-3 runs through dee_shim, which codes the 7.1 layout DEE's plain DD+
    mode doesn't have; everything else runs DEE as it is.

    Without ``lfe`` a 5.1 layout is coded as 5.0 (DEE's lfe_on=0), and 7.1 as
    7.0 through dee_shim. DEE's Blu-ray secondary mode keeps the LFE whatever
    lfe_on says, so it is not asked.
    """
    split_args = _split_args(
        tools,
        bitrate,
        extended=dd_mode in (DDEncodingMode.DDP71, DDEncodingMode.BLURAY),
        bluray=dd_mode is DDEncodingMode.BLURAY,
    )
    check_dd_options(payload, dd_mode, shim=tools.shim is not None)
    encoder = {
        "drc_profile_line": payload.drc_line_mode.to_dee_cmd(),
        "drc_profile_rf": payload.drc_rf_mode.to_dee_cmd(),
        "lfe_filter": _flag(payload.lfe_lowpass_filter),
        "surround_90deg_phase_shift": _flag(payload.surround_90_degree_phase_shift),
        "surround_3dB_attenuation": _flag(payload.surround_3db_attenuation),
        "preferred_downmix_mode": (
            StereoDownmix.NOT_INDICATED
            if downmix_mode_off
            else payload.preferred_downmix_mode
        ).to_dee_cmd(),
        "loro_cmix": payload.loro_center_mix_level,
        "loro_smix": payload.loro_surround_mix_level,
        "ltrt_cmix": payload.ltrt_center_mix_level,
        "ltrt_smix": payload.ltrt_surround_mix_level,
    }
    # the Blu-ray mode keeps the 7.1 layout of the input, so it is not given
    # an output layout at all
    is_bluray = dd_mode is DDEncodingMode.BLURAY
    mode = {
        DDEncodingMode.DD: "dd",
        DDEncodingMode.BLURAY: "bluray",
        DDEncodingMode.BLURAY_SECONDARY: "bluray_secondary",
    }.get(dd_mode, "ddp")
    user_data = int(getattr(payload, "user_data", -1))
    if user_data != -1:
        encoder["user_data"] = str(user_data)
    if not lfe and dd_mode in (DDEncodingMode.DD, DDEncodingMode.DDP):
        encoder["lfe_on"] = "0"

    # DeeZy's channel enums call "no downmix" 'off'; DEE calls it 'auto'
    channels = "off" if downmix_mode_off else payload.channels.to_dee_cmd()
    if channels == "off":
        channels = "auto"

    argv = [
        *_common_args(
            tools,
            DDP_TOOL,
            files,
            input_format="wav",
            temp_dir=True,
            bitrate=bitrate,
            fps=fps,
            delay=delay,
            payload=payload,
        ),
        *([] if is_bluray else ["-c", channels]),
        "-e",
        f"{mode}:{_options(encoder)}",
    ]
    if dd_mode is DDEncodingMode.DDP71:
        # the layout keeps -e ddp and its options, and the shim checks
        # --data-rate against its 7.1 list (7.0 takes the same rates)
        return _through_shim(
            tools, argv, *(DDP_71_SHIM_ARGS if lfe else DDP_70_SHIM_ARGS), *split_args
        )
    if is_bluray and (not lfe or split_args):
        if tools.shim is None:
            raise UnsupportedDeeFeatureError(
                f"Dolby Digital Plus Blu-ray 7.0 needs {NEEDS_SHIM}; "
                "DEE alone codes 7.1 only."
            )
        # the layout keeps -e bluray and its options
        layout = ("--layout", "7.1") if lfe else BLURAY_70_SHIM_ARGS
        return _through_shim(tools, argv, *layout, *split_args)
    return argv


def ddpjoc_command(
    tools: DeeTools,
    payload: AtmosPayload,
    files: DeeFiles,
    *,
    bitrate: Bitrate,
    fps: DeeFPS,
    delay: Delay,
) -> list[str]:
    """
    A Dolby Digital Plus Atmos (JOC) encode with dee_ddpjoc_encoder. With
    dee_shim it codes the object metadata as the master has it, and it is the
    only way to a 7.1 backbone or to turn the surround phase shift off.
    """
    check_atmos_options(payload, shim=tools.shim is not None)
    encoder = {
        "preferred_downmix_mode": payload.preferred_downmix_mode.to_dee_cmd(),
        "loro_cmix": payload.loro_center_mix_level,
        "loro_smix": payload.loro_surround_mix_level,
        "ltrt_cmix": payload.ltrt_center_mix_level,
        "ltrt_smix": payload.ltrt_surround_mix_level,
        "drc_profile_line": payload.drc_line_mode.to_dee_cmd(),
        "drc_profile_rf": payload.drc_rf_mode.to_dee_cmd(),
    }
    argv = [
        *_common_args(
            tools,
            DDP_JOC_TOOL,
            files,
            input_format="atmos_mezz",
            bitrate=bitrate,
            fps=fps,
            delay=delay,
            payload=payload,
        ),
        "-e",
        _options(encoder),
    ]
    # the shim names DEE's mode in -e itself (bluray for both 7.1 layouts,
    # ddpjoc once it is given any option in streaming) and checks --data-rate
    # against the layout's list
    split_args = _split_args(
        tools,
        bitrate,
        extended=payload.atmos_mode in DDPJOC_SHIM_LAYOUTS,
        bluray=payload.atmos_mode is AtmosMode.BLURAY,
    )
    return _through_shim(tools, argv, *ddpjoc_shim_args(payload), *split_args)


def _split_args(
    tools: DeeTools, bitrate: Bitrate, *, extended: bool, bluray: bool
) -> tuple[str, ...]:
    if not isinstance(bitrate, SubstreamBitrate):
        return ()
    if tools.shim is None:
        raise UnsupportedDeeFeatureError(
            f"--bitrate {bitrate} needs {NEEDS_SHIM} and two output substreams. "
            "Give its path with --dee-shim for DD+ 7.0/7.1 or DD+ Atmos standard/bluray, "
            "or give one total bitrate."
        )
    if not extended:
        raise UnsupportedDeeFeatureError(
            f"--bitrate {bitrate} requires two output substreams. Use DD+ 7.0/7.1 "
            "or DD+ Atmos standard/bluray, or give one total bitrate."
        )
    bitrate.check_core(bluray=bluray)
    return ("--bitrate", str(bitrate))


def ddpjoc_shim_args(payload: AtmosPayload) -> tuple[str, ...]:
    """dee_shim's options for a DD+ Atmos encode."""
    args = list(DDPJOC_SHIM_LAYOUTS.get(payload.atmos_mode, ()))
    if not payload.surround_90_degree_phase_shift:
        args += ["--phase90", "off"]
    if payload.oamd_as_is:
        # DEE smooths the object positions it reads; a TrueHD Atmos decode
        # has been smoothed once already
        args += ["--oamd-as-is", "on"]
    return tuple(args)


def check_atmos_options(payload: AtmosPayload, *, shim: bool) -> None:
    """
    Refuse DD+ Atmos options that need dee_shim when DeeZy doesn't have it.
    ``--no-oamd-as-is`` is fine either way: DEE alone always smooths.
    """
    if shim:
        return
    if payload.atmos_mode in DDPJOC_SHIM_LAYOUTS:
        # DEE alone would hand back a 5.1.2 backbone for a 7.1 request
        raise UnsupportedDeeFeatureError(
            f"DD+ Atmos '--atmos-mode {payload.atmos_mode.value}' codes a 7.1 "
            f"backbone, which needs {NEEDS_SHIM}; DeeZy didn't find "
            "it or was told not to use it (--no-shim). DEE's own Blu-ray mode "
            "gives a 5.1.2 backbone. Give the shim's path with --dee-shim, or "
            "use '--atmos-mode streaming'."
        )
    if not payload.surround_90_degree_phase_shift:
        raise UnsupportedDeeFeatureError(
            f"--no-surround-90-deg-phase-shift for DD+ Atmos needs {NEEDS_SHIM}; "
            "DeeZy didn't find it or was told not to use it "
            "(--no-shim), and DEE's DD+ Atmos encoder always shifts the "
            "surrounds. Give the shim's path with --dee-shim, or drop the option."
        )


def ac4ims_command(
    tools: DeeTools,
    payload: Ac4Payload,
    files: DeeFiles,
    *,
    bitrate: int,
    fps: DeeFPS,
    delay: Delay,
    atmos_input: bool,
) -> list[str]:
    """An immersive stereo AC-4 encode with dee_ac4ims_encoder."""
    devices = {
        "drc_profile_flat_panel": payload.flat_panel_drc,
        "drc_profile_home_theatre": payload.home_theatre_drc,
        "drc_profile_portable_hp": payload.portable_headphones_drc,
        "drc_profile_portable_spkr": payload.portable_speakers_drc,
    }
    if payload.encoding_profile is Ac4EncodingProfile.IMS_MUSIC:
        # DEE refuses music mode unless every device profile is music_light
        # and dialogue intelligence is off (the DD+ profile is free)
        logger.info(
            "AC-4 music mode uses music_light DRC on every device and turns "
            "dialogue intelligence off."
        )
        devices = dict.fromkeys(devices, DeeDRC.MUSIC_LIGHT)
        payload = replace(payload, dialogue_intelligence=False)
    encoder = {
        "mode": payload.encoding_profile.to_dee_cmd(),
        "drc_profile_ddp": payload.ddp_drc.to_dee_cmd(),
        **{key: drc.to_dee_cmd() for key, drc in devices.items()},
    }
    return [
        *_common_args(
            tools,
            AC4_IMS_TOOL,
            files,
            input_format="atmos_mezz" if atmos_input else "wav",
            bitrate=bitrate,
            fps=fps,
            delay=delay,
            payload=payload,
        ),
        "-e",
        _options(encoder),
    ]


# dee_ac4_encoder's loudness targets (the DD+ encoder's go up to -8)
AC4_TARGETS = range(-31, -9)


def check_ac4_options(payload: Ac4ChannelPayload) -> None:
    """Refuse what dee_ac4_encoder doesn't take, before any work starts."""
    target = payload.loudness_target
    if payload.peak_limit is not None and target is None:
        raise UnsupportedDeeFeatureError("--peak-limit needs --loudness-target.")
    if target is not None and target not in AC4_TARGETS:
        raise UnsupportedDeeFeatureError(
            f"AC-4 takes loudness targets from -31 to -10 LKFS, not {target}."
        )
    if target is not None and payload.loudness_preset is not LoudnessPreset.MANUAL:
        raise UnsupportedDeeFeatureError(
            "--loudness-target needs the manual loudness settings, so it "
            "can't be combined with --loudness-preset."
        )
    devices = (
        payload.flat_panel_drc,
        payload.home_theatre_drc,
        payload.portable_headphones_drc,
        payload.portable_speakers_drc,
    )
    if DeeDRC.NONE in devices:
        raise UnsupportedDeeFeatureError(
            "The AC-4 encoder has no 'none' DRC profile; use film_light, "
            "film_standard, music_light, music_standard or speech."
        )
    if "-inf" in (payload.loro_center_mix_level, payload.ltrt_center_mix_level):
        raise UnsupportedDeeFeatureError(
            "AC-4 takes center downmix levels from -6 to +3 dB, not -inf."
        )


def ac4_command(
    tools: DeeTools,
    payload: Ac4ChannelPayload,
    files: DeeFiles,
    *,
    manifest: Path,
    bitrate: int,
    fps: DeeFPS,
    delay: Delay,
) -> list[str]:
    """
    A channel-based AC-4 encode with dee_ac4_encoder, which requires an output
    manifest (it holds the offset an MP4 muxer would put in the edit list).
    """
    check_ac4_options(payload)
    encoder = {
        "drc_profile_flat_panel": payload.flat_panel_drc.to_dee_cmd(),
        "drc_profile_home_theatre": payload.home_theatre_drc.to_dee_cmd(),
        "drc_profile_portable_hp": payload.portable_headphones_drc.to_dee_cmd(),
        "drc_profile_portable_spkr": payload.portable_speakers_drc.to_dee_cmd(),
        "preferred_downmix_mode": payload.preferred_downmix_mode.to_dee_cmd(),
        "loro_cmix": payload.loro_center_mix_level,
        "loro_smix": payload.loro_surround_mix_level,
        "ltrt_cmix": payload.ltrt_center_mix_level,
        "ltrt_smix": payload.ltrt_surround_mix_level,
    }
    return [
        *_common_args(
            tools,
            AC4_TOOL,
            files,
            input_format="wav",
            temp_dir=True,
            bitrate=bitrate,
            fps=fps,
            delay=delay,
            payload=payload,
        ),
        "--output-manifest",
        long_path_str(manifest),
        "-c",
        payload.channels.to_dee_cmd(),
        "-e",
        _options(encoder),
    ]


# Dolby's level for A/V content; level 4 is for music, podcasts and audiobooks
AC4_ATMOS_LEVEL = 3


def ac4ajoc_command(
    tools: DeeTools,
    payload: Ac4AtmosPayload,
    files: DeeFiles,
    *,
    manifest: Path,
    bitrate: int,
    fps: DeeFPS,
    delay: Delay,
) -> list[str]:
    """
    An AC-4 Atmos encode of a master with dee_ac4ajoc_encoder. Like
    dee_ac4_encoder it requires an output manifest; it reads the master's kind
    from the file, so it takes no --input-format.
    """
    devices = {
        "drc_profile_flat_panel": payload.flat_panel_drc.to_dee_cmd(),
        "drc_profile_home_theatre": payload.home_theatre_drc.to_dee_cmd(),
        "drc_profile_portable_hp": payload.portable_headphones_drc.to_dee_cmd(),
        "drc_profile_portable_spkr": payload.portable_speakers_drc.to_dee_cmd(),
    }
    return [
        *_common_args(
            tools,
            AC4_ATMOS_TOOL,
            files,
            input_format=None,
            bitrate=bitrate,
            fps=fps,
            delay=delay,
            payload=payload,
        ),
        "--level",
        str(AC4_ATMOS_LEVEL),
        "--output-manifest",
        long_path_str(manifest),
        "-e",
        _options(devices),
    ]


def aac_command(
    tools: DeeTools,
    payload: AacPayload,
    files: DeeFiles,
    *,
    bitrate: int,
    fps: DeeFPS,
    delay: Delay,
) -> list[str]:
    """An AAC encode with dee_aac_encoder. The output is always 2.0."""
    return [
        *_common_args(
            tools,
            AAC_TOOL,
            files,
            input_format="wav",
            temp_dir=True,
            bitrate=bitrate,
            fps=fps,
            delay=delay,
            payload=payload,
            loudness_arg=aac_loudness(payload),
        ),
        "-e",
        payload.aac_profile.to_dee_cmd(),
    ]


def measure_command(
    tools: DeeTools,
    payload: MeasurePayload,
    files: DeeFiles,
    *,
    input_format: str,
    layout_71: bool = False,
) -> list[str]:
    """
    A loudness measurement with dee_measure_loudness. ``files.output`` is the
    loudness manifest it writes. The tool has no --temp-dir, and the measured
    audio it could also write isn't needed.

    DEE's CLI takes 1.0, 2.0 and 5.1. With ``layout_71`` the input is 7.1 in
    DEE's order, measured through dee_shim, which opens the meter's 7.1.
    """
    if layout_71 and tools.shim is None:
        raise UnsupportedDeeFeatureError(
            f"Measuring 7.1 needs {NEEDS_SHIM}: DEE's meter has 7.1, but its "
            "CLI takes 1.0, 2.0 and 5.1 only. DeeZy didn't find dee_shim or "
            "was told not to use it (--no-shim); give its path with --dee-shim."
        )
    argv = [
        str(dee_tool(tools.dee_dir, MEASURE_TOOL)),
        # replaced with the active log level when the job is run
        "--loglevel",
        "info",
        "--progress",
        "1",
        *(["--license", str(tools.license)] if tools.license else []),
        "--overwrite",
        "1",
        "--input-format",
        files.input_format or input_format,
        "-i",
        long_path_str(files.input) if isinstance(files.input, Path) else files.input,
        "--output-manifest",
        long_path_str(files.output),
        "--loudness-management",
        loudness(payload),
    ]
    if layout_71 and tools.shim:
        return list(tools.shim.argv(argv, *MEASURE_71_SHIM_ARGS))
    return argv


def check_thd_options(
    payload: TrueHDPayload | TrueHDAtmosPayload, *, shim: bool = False
) -> None:
    """
    Refuse what dee_dthd_encoder takes no value for. ``shim`` is whether
    DeeZy has dee_shim, which adds alternate layouts and DRC 'none'.
    """
    if isinstance(payload, TrueHDPayload) and payload.layout and not shim:
        raise UnsupportedDeeFeatureError(
            f"TrueHD --layout {payload.layout} needs {NEEDS_SHIM}. "
            "Give its path with --dee-shim if it isn't found automatically."
        )
    if payload.drc is DeeDRC.NONE and not shim:
        raise UnsupportedDeeFeatureError(
            f"TrueHD DRC 'none' needs {NEEDS_SHIM}; DeeZy didn't "
            "find it or was told not to use it (--no-shim), and the TrueHD "
            "encoder has no 'none' profile of its own. Give the shim's path with "
            "--dee-shim, or use film_light, film_standard, music_light, "
            "music_standard or speech."
        )


def _dthd_command(
    tools: DeeTools,
    payload: TrueHDPayload | TrueHDAtmosPayload,
    files: DeeFiles,
    *,
    top: str,
    input_format: str,
    downmixes: tuple[str, ...],
    fps: DeeFPS,
    delay: Delay,
    top_options: dict[str, str] | None = None,
    shim_args: tuple[str, ...] = (),
) -> list[str]:
    """
    A dee_dthd_encoder command line. The input feeds the ``top`` presentation;
    each of ``downmixes`` is one DEE derives from it. Each presentation's DRC
    is set on its own, so every one of them is given the payload's.
    ``shim_args`` are dee_shim's options, used only when DeeZy has it.
    """
    check_thd_options(payload, shim=tools.shim is not None)
    shim_args = tuple(shim_args)
    native_drc = payload.drc
    if payload.drc is DeeDRC.NONE:
        # the shim sets every presentation's DRC to none; DEE still needs one
        # of its own profiles to parse the command line
        shim_args = ("--drc", "none", *shim_args)
        native_drc = DeeDRC.FILM_LIGHT
    drc = {"drc_profile": native_drc.to_dee_cmd()}
    below = []
    for name in downmixes:
        below += ["--presentation", f"{name}:{_options(drc)}"]
    argv = [
        str(dee_tool(tools.dee_dir, THD_TOOL)),
        # replaced with the active log level when the job is run
        "--loglevel",
        "info",
        "--progress",
        "1",
        *(["--license", str(tools.license)] if tools.license else []),
        # DEE only ever writes into the job's own temp directory
        "--overwrite",
        "1",
        "--temp-dir",
        long_path_str(files.temp_dir),
        # the input options belong to the --presentation before them
        "--presentation",
        f"{top}:{_options({**drc, **(top_options or {})})}",
        "--input-format",
        files.input_format or input_format,
        "-i",
        long_path_str(files.input) if isinstance(files.input, Path) else files.input,
        *below,
        "-o",
        long_path_str(files.output),
        "--timecode-frame-rate",
        fps.to_dee_cmd(),
        *delay.dee_args(),
        "--loudness-management",
        loudness(payload),
    ]
    return _through_shim(tools, argv, *shim_args)


# DEE apodises 96 kHz input (and no other rate DeeZy encodes), a filter that
# changes the coded samples
THD_APODISED_RATE = 96000


def thd_command(
    tools: DeeTools,
    payload: TrueHDPayload,
    files: DeeFiles,
    *,
    fps: DeeFPS,
    delay: Delay,
    sample_rate: int = 48000,
) -> list[str]:
    """
    A channel-based TrueHD encode with dee_dthd_encoder. ``payload.channels``
    is the input's layout, which is the stream's top presentation; DEE derives
    the smaller ones from it. ``sample_rate`` is the rate DEE encodes; at
    96 kHz dee_shim turns DEE's apodizing filter off unless asked not to.
    """
    top = payload.channels.value
    apodise_off = sample_rate == THD_APODISED_RATE and payload.as_is
    shim_args = ("--layout", payload.layout) if payload.layout else ()
    if apodise_off:
        shim_args += ("--apodise", "off")
    return _dthd_command(
        tools,
        payload,
        files,
        top=payload.channels.to_dee_cmd(),
        top_options={"surround_3dB_attenuation": "1"}
        if payload.surround_3db_attenuation and top in (6, 8)
        else None,
        input_format="wav",
        downmixes=tuple(f"{channels}ch" for channels in (6, 2) if channels < top),
        fps=fps,
        delay=delay,
        shim_args=shim_args,
    )


# D7: Dolby's default is 12 elements; more keep more of the master's detail.
# DeeZy's default is the most DEE codes (and the most truehdd decodes)
THD_ATMOS_ELEMENTS = 16
THD_ATMOS_ELEMENT_CHOICES = (12, 14, 16)


def thd_atmos_command(
    tools: DeeTools,
    payload: TrueHDAtmosPayload,
    files: DeeFiles,
    *,
    fps: DeeFPS,
    delay: Delay,
    fits: bool = False,
) -> list[str]:
    """
    A TrueHD Atmos encode of a master with dee_dthd_encoder. The stream also
    carries the 7.1, 5.1 and 2.0 presentations DEE renders from it.

    Legacy authoring is off unless asked for (D7). Dolby's default is on, and
    then the stream carries no warp mode.

    The stream codes the master into ``payload.atmos_elements`` elements
    (--atmos-elements). ``fits`` is whether the master has no more elements
    than that.
    Then dee_shim codes it as it is, unless asked not to: one element per bed
    channel or object, the object metadata as authored and the audio without
    noise shaping, so the stream decodes to the master sample for sample.
    """
    as_is = fits and payload.as_is
    return _dthd_command(
        tools,
        payload,
        files,
        top="atmos",
        top_options={
            "number_of_elements": str(payload.atmos_elements),
            "legacy_authoring": _flag(payload.legacy_authoring),
        },
        input_format="atmos_mezz",
        downmixes=("8ch", "6ch", "2ch"),
        fps=fps,
        delay=delay,
        shim_args=("--oamd-as-is", "on", "--as-is", "on") if as_is else (),
    )


def aac_loudness(payload: AacPayload) -> str:
    """
    dee_aac_encoder's --loudness-management value.

    AAC carries no loudness metadata and the encoder has no measure-only mode,
    so DeeZy leaves the audio as it is (skip) unless a target or a regulation
    asks for it to be corrected.
    """
    target = payload.loudness_target
    peak = payload.peak_limit
    preset = payload.loudness_preset
    if peak is not None and target is None:
        raise UnsupportedDeeFeatureError("--peak-limit needs --loudness-target.")
    if preset is not LoudnessPreset.MANUAL:
        if target is not None:
            raise UnsupportedDeeFeatureError(
                "--loudness-target needs the manual loudness settings, so it "
                "can't be combined with --loudness-preset."
            )
        logger.info(
            f"AAC carries no loudness metadata, so --loudness-preset corrects "
            f"the audio to {preset.to_dee_cmd()}."
        )
        return "measure_and_correct:" + _options({"preset": preset.to_dee_cmd()})
    if target is None:
        return "skip"
    options = {
        "preset": "manual",
        "dialogue_intelligence": _flag(payload.dialogue_intelligence),
        "speech_threshold": str(payload.speech_threshold),
        "loudness_target": str(target),
    }
    if peak is not None:
        options["peak_limit_db"] = f"{peak:g}"
    return "measure_and_correct:" + _options(options)


def _common_args(
    tools: DeeTools,
    tool: str,
    files: DeeFiles,
    *,
    input_format: str | None,
    bitrate: Bitrate,
    fps: DeeFPS,
    delay: Delay,
    payload: LoudnessPayload,
    temp_dir: bool = False,
    loudness_arg: str | None = None,
) -> list[str]:
    """
    Options every encoder takes, in a stable order.

    ``input_format`` is None for an encoder with no ``--input-format`` option,
    which tells its inputs apart itself. ``temp_dir`` is for the encoders that
    have a ``--temp-dir`` option; the others manage their temp files
    themselves. ``loudness_arg`` replaces the usual ``--loudness-management``
    value.
    """
    input_format = files.input_format or input_format
    return [
        str(dee_tool(tools.dee_dir, tool)),
        # replaced with the active log level when the job is run
        "--loglevel",
        "info",
        "--progress",
        "1",
        *(["--license", str(tools.license)] if tools.license else []),
        # DEE only ever writes into the job's own temp directory
        "--overwrite",
        "1",
        *(["--temp-dir", long_path_str(files.temp_dir)] if temp_dir else []),
        *(["--input-format", input_format] if input_format else []),
        "-i",
        long_path_str(files.input) if isinstance(files.input, Path) else files.input,
        "-o",
        long_path_str(files.output),
        "--timecode-frame-rate",
        fps.to_dee_cmd(),
        *delay.dee_args(),
        *(["--data-rate", str(bitrate)] if isinstance(bitrate, int) else []),
        "--loudness-management",
        loudness_arg or loudness(payload),
    ]


def check_dd_options(
    payload: DDPayload | DDPPayload, dd_mode: DDEncodingMode, *, shim: bool = False
) -> None:
    """
    Refuse option combinations dee_ddp_encoder cannot honor. ``shim`` is
    whether DeeZy has dee_shim, which DD+ 7.1 as E-AC-3 needs.
    """
    target = getattr(payload, "loudness_target", None)
    peak = getattr(payload, "peak_limit", None)
    if peak is not None and target is None:
        raise UnsupportedDeeFeatureError("--peak-limit needs --loudness-target.")
    if target is not None:
        if int(getattr(payload, "custom_dialnorm", 0) or 0) != 0:
            raise UnsupportedDeeFeatureError(
                "--loudness-target measures and corrects the loudness, so it "
                "can't be combined with --custom-dialnorm."
            )
        if dd_mode is DDEncodingMode.BLURAY:
            raise UnsupportedDeeFeatureError(
                "--loudness-target is not available for Blu-ray (7.1) DD+."
            )
        if getattr(payload, "loudness_preset", LoudnessPreset.MANUAL) is not (
            LoudnessPreset.MANUAL
        ):
            raise UnsupportedDeeFeatureError(
                "--loudness-target needs the manual loudness settings, so it "
                "can't be combined with --loudness-preset."
            )
    if int(getattr(payload, "user_data", -1)) != -1 and dd_mode not in (
        DDEncodingMode.DDP,
        DDEncodingMode.DDP71,
    ):
        raise UnsupportedDeeFeatureError(
            "--user-data is only available for plain Dolby Digital Plus."
        )
    if dd_mode is DDEncodingMode.DDP71 and not shim:
        # DEE alone takes 7.1 only in its Blu-ray mode; the plain DD+ one would
        # quietly hand back a 5.1 stream for a 7.1 request
        raise UnsupportedDeeFeatureError(
            f"Dolby Digital Plus 7.1 as E-AC-3 needs {NEEDS_SHIM}, "
            "which DeeZy didn't find or was told not to use (--no-shim). Give its "
            "path with --dee-shim, or use 'ddp-bluray' for 7.1 or '--channels 6' "
            "for 5.1."
        )


def loudness(payload: LoudnessPayload) -> str:
    """The --loudness-management value."""
    # a custom dialnorm skips measurement and writes the value as-is. The
    # encoders' --help never lists 'skip'; DEE 6.7 takes it as skip:dialnorm=N
    custom = int(getattr(payload, "custom_dialnorm", 0) or 0)
    if custom != 0:
        return f"skip:dialnorm={custom}"
    preset = getattr(payload, "loudness_preset", LoudnessPreset.MANUAL)
    if preset is not LoudnessPreset.MANUAL:
        # a regulation sets its own gating, so the manual options don't apply
        return "measure_only:" + _options({"preset": preset.to_dee_cmd()})
    options = {
        "preset": "manual",
        "dialogue_intelligence": _flag(payload.dialogue_intelligence),
        "speech_threshold": str(payload.speech_threshold),
    }
    target = getattr(payload, "loudness_target", None)
    if target is None:
        return "measure_only:" + _options(options)
    options["loudness_target"] = str(target)
    peak = getattr(payload, "peak_limit", None)
    if peak is not None:
        options["peak_limit_db"] = f"{peak:g}"
    return "measure_and_correct:" + _options(options)
