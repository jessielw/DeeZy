"""
Command lines for the DEE 6.7 encoders.

Options the tools do not offer raise `UnsupportedDeeFeatureError` rather than
being dropped, so an encode never comes out different from what was asked for.
Nothing here touches the disk.
"""

from dataclasses import dataclass, replace
from pathlib import Path

from deezy.dee.tools import dee_tool
from deezy.delay import Delay
from deezy.enums.ac4 import Ac4EncodingProfile
from deezy.enums.shared import (
    DDEncodingMode,
    DeeDRC,
    DeeFPS,
    LoudnessPreset,
    MeteringMode,
    StereoDownmix,
)
from deezy.exceptions import UnsupportedDeeFeatureError
from deezy.payloads.aac import AacPayload
from deezy.payloads.ac4 import Ac4ChannelPayload, Ac4Payload
from deezy.payloads.atmos import AtmosPayload
from deezy.payloads.dd import DDPayload
from deezy.payloads.ddp import DDPPayload
from deezy.payloads.measure import MeasurePayload
from deezy.payloads.shared import LoudnessPayload
from deezy.payloads.thd import TrueHDPayload
from deezy.utils.logger import logger
from deezy.utils.paths import long_path_str

DDP_TOOL = "dee_ddp_encoder"
DDP_JOC_TOOL = "dee_ddpjoc_encoder"
AC4_IMS_TOOL = "dee_ac4ims_encoder"
AC4_TOOL = "dee_ac4_encoder"
AAC_TOOL = "dee_aac_encoder"
MEASURE_TOOL = "dee_measure_loudness"
THD_TOOL = "dee_dthd_encoder"


@dataclass(frozen=True, slots=True)
class DeeTools:
    """The folder of DEE tools, and a license to pass when they won't find one."""

    dee_dir: Path
    license: Path | None = None


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
    bitrate: int,
    fps: DeeFPS,
    delay: Delay,
    dd_mode: DDEncodingMode,
) -> list[str]:
    """A Dolby Digital or Dolby Digital Plus encode with dee_ddp_encoder."""
    check_dd_options(payload, dd_mode)
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

    # DeeZy's channel enums call "no downmix" 'off'; DEE calls it 'auto'
    channels = "off" if downmix_mode_off else payload.channels.to_dee_cmd()
    if channels == "off":
        channels = "auto"

    return [
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


def ddpjoc_command(
    tools: DeeTools,
    payload: AtmosPayload,
    files: DeeFiles,
    *,
    bitrate: int,
    fps: DeeFPS,
    delay: Delay,
) -> list[str]:
    """A Dolby Digital Plus Atmos (JOC) encode with dee_ddpjoc_encoder."""
    encoder = {
        "preferred_downmix_mode": payload.preferred_downmix_mode.to_dee_cmd(),
        "loro_cmix": payload.loro_center_mix_level,
        "loro_smix": payload.loro_surround_mix_level,
        "ltrt_cmix": payload.ltrt_center_mix_level,
        "ltrt_smix": payload.ltrt_surround_mix_level,
        "drc_profile_line": payload.drc_line_mode.to_dee_cmd(),
        "drc_profile_rf": payload.drc_rf_mode.to_dee_cmd(),
    }
    return [
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
    if payload.ims_legacy_presentation:
        # kept so older commands still run; DEE 6.7 has no such option
        logger.warning(
            "--ims-legacy-presentation is not available with the split DEE "
            "encoders and will be ignored."
        )
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
    tools: DeeTools, payload: MeasurePayload, files: DeeFiles, *, input_format: str
) -> list[str]:
    """
    A loudness measurement with dee_measure_loudness. ``files.output`` is the
    loudness manifest it writes. The tool has no --temp-dir, and the measured
    audio it could also write isn't needed.
    """
    return [
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


def check_thd_options(payload: TrueHDPayload) -> None:
    """Refuse what dee_dthd_encoder takes no value for."""
    if payload.drc is DeeDRC.NONE:
        raise UnsupportedDeeFeatureError(
            "The TrueHD encoder has no 'none' DRC profile; dee_shim adds one, "
            "which this DeeZy version doesn't drive yet. Use film_light, "
            "film_standard, music_light, music_standard or speech."
        )


def thd_command(
    tools: DeeTools,
    payload: TrueHDPayload,
    files: DeeFiles,
    *,
    fps: DeeFPS,
    delay: Delay,
) -> list[str]:
    """
    A channel-based TrueHD encode with dee_dthd_encoder. ``payload.channels``
    is the input's layout, which is the stream's top presentation; DEE derives
    the smaller ones from it, and each gets the payload's DRC.
    """
    check_thd_options(payload)
    top = payload.channels.value
    drc = payload.drc.to_dee_cmd()
    downmixes = []
    for channels in (6, 2):
        if channels < top:
            downmixes += ["--presentation", f"{channels}ch:drc_profile={drc}"]
    return [
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
        f"{payload.channels.to_dee_cmd()}:drc_profile={drc}",
        "--input-format",
        files.input_format or "wav",
        "-i",
        long_path_str(files.input) if isinstance(files.input, Path) else files.input,
        *downmixes,
        "-o",
        long_path_str(files.output),
        "--timecode-frame-rate",
        fps.to_dee_cmd(),
        *delay.dee_args(),
        "--loudness-management",
        loudness(payload),
    ]


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
    input_format: str,
    bitrate: int,
    fps: DeeFPS,
    delay: Delay,
    payload: LoudnessPayload,
    temp_dir: bool = False,
    loudness_arg: str | None = None,
) -> list[str]:
    """
    Options every encoder takes, in a stable order.

    ``temp_dir`` is for the encoders that have a ``--temp-dir`` option; the
    others manage their temp files themselves. ``loudness_arg`` replaces the
    usual ``--loudness-management`` value.
    """
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
        "--input-format",
        files.input_format or input_format,
        "-i",
        long_path_str(files.input) if isinstance(files.input, Path) else files.input,
        "-o",
        long_path_str(files.output),
        "--timecode-frame-rate",
        fps.to_dee_cmd(),
        *delay.dee_args(),
        "--data-rate",
        str(bitrate),
        "--loudness-management",
        loudness_arg or loudness(payload),
    ]


def check_dd_options(payload: DDPayload | DDPPayload, dd_mode: DDEncodingMode) -> None:
    """Refuse option combinations dee_ddp_encoder cannot honor."""
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
    if dd_mode is DDEncodingMode.DDP71:
        # only the Blu-ray encoder mode takes 7.1; the plain DD+ one would
        # quietly hand back a 5.1 stream for a 7.1 request
        raise UnsupportedDeeFeatureError(
            "Dolby Digital Plus 7.1 as E-AC-3 needs dee_shim, which this DeeZy "
            "version doesn't drive yet. Use 'ddp-bluray' for 7.1, or "
            "'--channels 6' for 5.1."
        )


def loudness(payload: LoudnessPayload) -> str:
    """The --loudness-management value."""
    # a custom dialnorm skips measurement and writes the value as-is. The
    # encoders' --help never lists 'skip'; DEE 6.7 takes it as skip:dialnorm=N
    custom = int(getattr(payload, "custom_dialnorm", 0) or 0)
    if custom != 0:
        return f"skip:dialnorm={custom}"
    # these encoders measure to ITU-R BS.1770-4 only
    if payload.metering_mode is not MeteringMode.MODE_1770_4:
        logger.info(
            f"Metering mode {payload.metering_mode} is not offered by the split "
            "DEE encoders, measuring with 1770-4."
        )
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
