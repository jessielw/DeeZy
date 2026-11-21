"""
Plans an encode: every decision and command line, before anything runs.

`plan_job` takes the probed source track, the options and the paths the job may
use, and returns a `JobPlan`. It reads no files and starts no processes, so a
plan can be printed, compared or tested without DEE. Options DEE can't honor
are refused here, before any work starts.
"""

from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Protocol

from deezy.config.manager import ConfigManager
from deezy.dee.commands import (
    DeeFiles,
    DeeTools,
    ac4ims_command,
    ddp_command,
    ddpjoc_command,
)
from deezy.dee.spec import FormatSpec, get_format
from deezy.delay import Delay, compensation
from deezy.enums.ac4 import Ac4Channels
from deezy.enums.atmos import AtmosMode, WarpMode
from deezy.enums.channel_count import ChannelCount
from deezy.enums.codec_format import CodecFormat
from deezy.enums.dd import DolbyDigitalChannels
from deezy.enums.ddp import DolbyDigitalPlusChannels
from deezy.enums.ddp_bluray import DolbyDigitalPlusBlurayChannels
from deezy.enums.shared import DDEncodingMode, DeeFPS, StereoDownmix, TrackType
from deezy.exceptions import (
    AutoChannelDetectionError,
    ChannelMixError,
    DependencyNotFoundError,
    InvalidAtmosInputError,
    InvalidExtensionError,
    UnsupportedDeeFeatureError,
)
from deezy.payloads.ac4 import Ac4Payload
from deezy.payloads.atmos import AtmosPayload
from deezy.payloads.dd import DDPayload
from deezy.payloads.ddp import DDPPayload
from deezy.payloads.shared import ChannelBitrates, CorePayload
from deezy.pipeline.transport import WavFile
from deezy.track_info.audio_track_info import AudioTrackInfo
from deezy.track_info.track_index import TrackIndex
from deezy.track_info.utils import parse_delay_from_file
from deezy.utils.logger import logger
from deezy.utils.paths import artifact_stem

# Blu-ray secondary audio data rates (kbps)
SECONDARY_BITRATES = (192, 256)
# the source layouts DEE takes as they are
DEE_INPUT_CHANNELS = (1, 2, 6, 8)

_PAN_50_TO_51 = "pan=5.1(side)|FL=c0|FR=c1|FC=c2|LFE=0*c0|SL=c3|SR=c4"
# ffmpeg's 7.1 has the backs in 5-6 and the sides in 7-8; DEE wants the reverse
_PAN_7_1 = "pan=7.1|c0=c0|c1=c1|c2=c2|c3=c3|c4=c6|c5=c7|c6=c4|c7=c5"
_DPLII = "aresample=matrix_encoding=dplii"
_RESAMPLE = "aresample=resampler=soxr:precision=28:cutoff=1:dither_scale=0"
DEE_SAMPLE_RATE = 48000


@dataclass(frozen=True, slots=True)
class FfmpegStep:
    argv: tuple[str, ...]
    # the WAV it writes
    output: Path
    # this step's entry in the temp-file reuse metadata
    reuse_id: str
    duration: float | None = None


@dataclass(frozen=True, slots=True)
class TruehddStep:
    """FFmpeg's TrueHD stream piped into truehdd, which writes a DAMF."""

    file_input: Path
    track_index: TrackIndex
    ffmpeg: Path
    truehdd: Path
    # None: truehdd passes no warp mode
    warp_mode: WarpMode | None
    output_dir: Path
    reuse_id: str
    duration: float | None = None

    @property
    def output(self) -> Path:
        return self.output_dir / "atmos_meta.atmos"

    @property
    def signature(self) -> str:
        warp = self.warp_mode.to_truehdd_cmd() if self.warp_mode else "none"
        return f"truehdd:{warp}"


@dataclass(frozen=True, slots=True)
class DeeStep:
    argv: tuple[str, ...]
    # inside the temp directory; the runner moves it to the plan's output
    output: Path
    # shown by the progress display, which can't read it from DEE
    custom_dialnorm: int = 0


Step = FfmpegStep | TruehddStep | DeeStep


@dataclass(frozen=True, slots=True)
class JobPlan:
    format: str
    source: Path
    output: Path
    temp_dir: Path
    steps: tuple[Step, ...]
    # the free space the temp directory needs (None: 110% of the source)
    free_space_needed: int | None = None
    # only name the output; run nothing
    preview: bool = False


class OutputNamer(Protocol):
    def generate_output_filename(
        self,
        delay_was_stripped: bool,
        delay_relative_to_video: int,
        suffix: str,
        output_channels: str,
        worker_id: str | None,
    ) -> Path: ...

    def render_output_template(
        self,
        template: str,
        suffix: str,
        output_channels: str,
        delay_was_stripped: bool,
        delay_relative_to_video: int,
        worker_id: str | None = None,
    ) -> Path: ...


@dataclass(frozen=True, slots=True)
class PlanContext:
    """What a plan may use besides the options and the source."""

    # names the output from the source's metadata
    namer: OutputNamer
    temp_dir: Path
    # passed to DEE when the tools won't find their own
    license: Path | None = None
    config: ConfigManager | None = None


def plan_job(payload: CorePayload, info: AudioTrackInfo, ctx: PlanContext) -> JobPlan:
    """The plan for one encode. ``info`` is the probed source track."""
    if isinstance(payload, DDPayload):
        return _plan_dd(payload, info, ctx)
    if isinstance(payload, DDPPayload):
        return _plan_ddp(payload, info, ctx)
    if isinstance(payload, AtmosPayload):
        return _plan_ddp_atmos(payload, info, ctx)
    if isinstance(payload, Ac4Payload):
        return _plan_ac4_ims(payload, info, ctx)
    raise TypeError(f"no plan for {type(payload).__name__}")


# --- shared decisions


def check_for_up_mixing(source_channels: int, desired_channels: int) -> None:
    if source_channels < desired_channels:
        raise ChannelMixError("Up-mixing is not supported.")


def auto_channels(source_channels: int, accepted: list[int]) -> int:
    """The source's layout if the codec takes it, else the largest one below it."""
    if source_channels in accepted:
        return source_channels
    lower = [x for x in accepted if x < source_channels]
    if lower:
        return int(max(lower))
    raise AutoChannelDetectionError(
        "Unable to determine automatic channel selection for input "
        f"{source_channels} with accepted channels {accepted}"
    )


def get_delay(payload: CorePayload) -> Delay:
    """The requested delay: ``--delay``, else one in the file name, else none."""
    text = payload.delay or parse_delay_from_file(Path(payload.file_input)) or "0ms"
    delay = Delay.parse(text)
    if delay.is_delay():
        logger.debug(f"Requested delay {delay.ms:g} ms ({delay.requested} samples).")
    return delay


def get_fps(fps: str | float | int | None) -> DeeFPS:
    """The video frame rate DEE writes as timecode, or not_indicated."""
    try:
        if fps is None:
            return DeeFPS.FPS_NOT_INDICATED
        if isinstance(fps, str):
            value = float(fps) if "." in fps else int(fps)
        elif isinstance(fps, float):
            value = int(fps) if fps.is_integer() else fps
        else:
            value = fps
        return DeeFPS(value)
    except (ValueError, TypeError):
        return DeeFPS.FPS_NOT_INDICATED


def resolve_bitrate(
    config: ConfigManager | None,
    format_command: CodecFormat,
    payload_bitrate: int | None,
    payload_channels: Any,
    info: AudioTrackInfo,
    bitrate_obj: ChannelBitrates,
    source_audio_channels: int,
    auto_enum_value: Any,
    channel_resolver: Callable[[int], Any],
) -> int:
    """
    The data rate: the requested one, else the configured default for the
    source's or the output's layout, else DeeZy's default. A rate DEE doesn't
    take becomes the closest one it does.
    """
    if payload_bitrate:
        if not bitrate_obj.is_valid_bitrate(payload_bitrate):
            fixed = bitrate_obj.get_closest_bitrate(payload_bitrate)
            logger.warning(
                f"Bitrate {payload_bitrate} is invalid for this configuration. "
                f"Using the next closest allowed bitrate: {fixed}."
            )
            return fixed
        logger.debug(f"Using provided bitrate: {payload_bitrate}.")
        return payload_bitrate

    config_bitrate = None
    target_channels = None
    try:
        if config:
            source_bitrate = source_bitrate_from_config(
                config, format_command.value, source_audio_channels, info.thd_atmos
            )
            if source_bitrate:
                logger.debug(
                    f"Got source channel bitrate from config ({source_bitrate})"
                )
                config_bitrate = source_bitrate
            target_channels = payload_channels
            if auto_enum_value is not None and payload_channels == auto_enum_value:
                target_channels = channel_resolver(info.channels)
            if not config_bitrate:
                config_bitrate = config.get_default_bitrate(
                    format_command, target_channels
                )
    except Exception:
        logger.debug("Configured bitrate lookup failed; using the encoder default.")

    if config_bitrate is not None:
        if bitrate_obj.is_valid_bitrate(config_bitrate):
            logger.debug(
                f"No supplied bitrate, using config default {config_bitrate} for "
                f"{target_channels}."
            )
            return config_bitrate
        fixed = bitrate_obj.get_closest_bitrate(config_bitrate)
        logger.warning(
            f"Config bitrate {config_bitrate} is invalid for this configuration. "
            f"Using the next closest allowed bitrate: {fixed}."
        )
        return fixed

    logger.debug(f"No supplied bitrate, defaulting to {bitrate_obj.default}.")
    return bitrate_obj.default


def source_bitrate_from_config(
    config: ConfigManager, fmt: str, source_channels: int, thd_atmos: bool
) -> int | None:
    """The [default_source_bitrates] rate for the source's channel count, if set."""
    try:
        key = ChannelCount(int(source_channels)).to_config()
        section = config.config.get("default_source_bitrates")
        if not section:
            return None
        fmt_conf = section.get(fmt)
        if not fmt_conf:
            return None
        bitrate = None
        # AC-4 IMS may set a separate rate for TrueHD Atmos sources ('ch_6_atmos')
        if thd_atmos and fmt == str(CodecFormat.AC4_IMS):
            bitrate = fmt_conf.get(f"{key}_atmos")
        if bitrate is None:
            bitrate = fmt_conf.get(key)
        if bitrate is None or bitrate <= 0:
            return None
        return bitrate
    except Exception as e:
        logger.debug(f"Failed to get source bitrate from config: {e}")
        return None


def _output(
    payload: CorePayload,
    info: AudioTrackInfo,
    ctx: PlanContext,
    spec: FormatSpec,
    label: str,
    channels: str,
    delay: Delay,
) -> tuple[Path, bool]:
    """The output path, and whether only a preview of it was asked for."""
    if payload.file_output:
        output = Path(payload.file_output)
        if output.suffix not in spec.extensions:
            raise InvalidExtensionError(
                f"{label} output must end with the suffix "
                + " or ".join(f"'{ext}'" for ext in spec.extensions)
                + "."
            )
    elif payload.output_template:
        output = ctx.namer.render_output_template(
            template=str(payload.output_template),
            suffix=spec.extension,
            output_channels=channels,
            delay_was_stripped=delay.is_delay(),
            delay_relative_to_video=info.delay_relative_to_video,
            worker_id=payload.worker_id,
        )
        if payload.output_preview:
            return output, True
    else:
        output = ctx.namer.generate_output_filename(
            delay_was_stripped=delay.is_delay(),
            delay_relative_to_video=info.delay_relative_to_video,
            suffix=spec.extension,
            output_channels=channels,
            worker_id=payload.worker_id,
        )
    # an explicit --output wins over a batch output directory
    if payload.file_output is None and payload.batch_output_dir:
        output = Path(payload.batch_output_dir) / output.name
    logger.debug(f"Output path {output}.")
    return output, False


def _compensate(
    delay: Delay, spec: FormatSpec, dee_input_channels: int, dee_output_channels: int
) -> Delay:
    """`delay`, less the samples DEE adds to this encode."""
    channel_change = dee_input_channels != dee_output_channels
    delay = delay.compensated(compensation(spec, channel_change=channel_change))
    if channel_change:
        logger.debug(
            f"DEE changes {dee_input_channels} channels to {dee_output_channels}, "
            f"compensating {delay.compensation} samples."
        )
    return delay


def ffmpeg_argv(
    ffmpeg: Path,
    file_input: Path,
    track_index: TrackIndex,
    filters: list[str],
    wav: WavFile,
) -> tuple[str, ...]:
    """FFmpeg decoding the track to 32-bit PCM for DEE. AC-3 DRC is off."""
    return (
        str(ffmpeg),
        "-y",
        "-drc_scale",
        "0",
        "-hide_banner",
        # the processor puts the verbosity level after this
        "-v",
        "-i",
        str(Path(file_input)),
        "-map",
        f"0:a:{track_index.index}"
        if track_index.track_type is TrackType.AUDIO
        else f"0:{track_index.index}",
        "-c",
        "pcm_s32le",
        *filters,
        "-map_metadata",
        "-1",
        *wav.ffmpeg_output(),
    )


def _filter_args(mix: str | None, resample: bool) -> list[str]:
    """``-af`` with a channel mix, the 48 kHz resampler, or both."""
    chain = [f for f in (mix, _RESAMPLE if resample else None) if f]
    args = ["-af", ",".join(chain)] if chain else []
    if resample:
        args += ["-ar", str(DEE_SAMPLE_RATE)]
    return args


def _ffmpeg_step(
    payload: CorePayload,
    filters: list[str],
    wav: WavFile,
    reuse_id: str,
    info: AudioTrackInfo,
) -> FfmpegStep:
    return FfmpegStep(
        argv=ffmpeg_argv(
            payload.ffmpeg_path,
            Path(payload.file_input),
            payload.track_index,
            filters,
            wav,
        ),
        output=wav.path,
        reuse_id=reuse_id,
        duration=info.duration,
    )


def dee_output_path(temp_dir: Path, output: Path) -> Path:
    """
    Where DEE encodes to: inside the temp directory, under a bounded name.

    DEE never writes to the destination, so it is only handed paths whose length
    DeeZy controls, and a failed encode leaves nothing at the destination.
    """
    return temp_dir / f"{artifact_stem(output)}{output.suffix}"


def _dee_files(ctx: PlanContext, dee_input: Path, output: Path) -> DeeFiles:
    return DeeFiles(
        input=dee_input,
        output=dee_output_path(ctx.temp_dir, output),
        temp_dir=ctx.temp_dir,
    )


def _tools(payload: CorePayload, ctx: PlanContext) -> DeeTools:
    return DeeTools(Path(payload.dee_path), ctx.license)


def _truehdd_step(
    payload: AtmosPayload | Ac4Payload,
    info: AudioTrackInfo,
    ctx: PlanContext,
    reuse_id: str,
) -> TruehddStep:
    if not payload.truehdd_path:
        raise DependencyNotFoundError(
            "Failed to locate truehdd, this is required for TrueHD Atmos work flows"
        )
    return TruehddStep(
        file_input=Path(payload.file_input),
        track_index=payload.track_index,
        ffmpeg=payload.ffmpeg_path,
        truehdd=payload.truehdd_path,
        warp_mode=payload.thd_warp_mode,
        output_dir=ctx.temp_dir,
        reuse_id=reuse_id,
        duration=info.duration,
    )


# --- Dolby Digital


def dd_channel_resolver(source_channels: int) -> DolbyDigitalChannels:
    """The DD layout AUTO picks for the config lookup."""
    if source_channels == 1:
        return DolbyDigitalChannels.MONO
    if 1 < source_channels < 6:
        return DolbyDigitalChannels.STEREO
    return DolbyDigitalChannels.SURROUND


def _plan_dd(payload: DDPayload, info: AudioTrackInfo, ctx: PlanContext) -> JobPlan:
    spec = get_format("dd")
    source_channels = info.channels
    channels = payload.channels
    stereo_mix = payload.stereo_mix

    # a 5.0 source the user wants up-mixed to 5.1
    upmix_50 = (
        payload.upmix_50_to_51
        and channels in (DolbyDigitalChannels.AUTO, DolbyDigitalChannels.SURROUND)
        and source_channels == 5
    )
    desired = DolbyDigitalChannels.SURROUND if upmix_50 else channels
    if desired is DolbyDigitalChannels.AUTO:
        desired = dd_channel_resolver(source_channels)
    bitrate = resolve_bitrate(
        ctx.config,
        CodecFormat.DD,
        payload.bitrate,
        channels,
        info,
        desired.get_bitrate_obj(),
        source_channels,
        DolbyDigitalChannels.AUTO,
        dd_channel_resolver,
    )

    if channels is not DolbyDigitalChannels.AUTO and not upmix_50:
        check_for_up_mixing(source_channels, channels.value)
    elif channels is DolbyDigitalChannels.AUTO:
        channels = DolbyDigitalChannels(
            auto_channels(source_channels, DolbyDigitalChannels.get_values_list())
        )
        logger.info(f"No supplied channels, defaulting to {channels}.")

    delay = get_delay(payload)
    fps = get_fps(info.fps)
    output, preview = _output(payload, info, ctx, spec, "DD", str(channels), delay)

    # DEE takes the source's own layout, not the AUTO choice made from it
    dee_allowed_input = source_channels in DEE_INPUT_CHANNELS
    dplii = (
        channels is DolbyDigitalChannels.STEREO and stereo_mix is StereoDownmix.DPLII
    )
    # DEE leaves the layout alone ('off') when it is the source's, when FFmpeg
    # makes the DPL II mix (DD has none), or when DEE can't take the source
    downmix_off = channels.value == source_channels or dplii or not dee_allowed_input
    ffmpeg_down_mix = None
    if (
        (downmix_off and not dee_allowed_input)
        or (downmix_off and dplii)
        or (
            upmix_50
            and source_channels == 5
            and channels is DolbyDigitalChannels.SURROUND
            and payload.upmix_50_to_51
        )
    ):
        ffmpeg_down_mix = channels.value
    delay = _compensate(delay, spec, ffmpeg_down_mix or source_channels, channels.value)

    wav = WavFile(ctx.temp_dir / f"{artifact_stem(output)}.{CodecFormat.DD}.wav")
    resample = not info.sample_rate or info.sample_rate != DEE_SAMPLE_RATE
    if dplii:
        filters = _filter_args(_DPLII, resample)
    elif upmix_50:
        # the pan writes the 5.1 layout itself, so no -ac
        filters = _filter_args(_PAN_50_TO_51, resample)
    else:
        filters = _filter_args(None, resample)
    if (ffmpeg_down_mix and not upmix_50) or stereo_mix is StereoDownmix.DPLII:
        filters += ["-ac", f"{ffmpeg_down_mix}"]
    ffmpeg = _ffmpeg_step(payload, filters, wav, str(CodecFormat.DD), info)

    files = _dee_files(ctx, wav.dee_input, output)
    dee_argv = ddp_command(
        _tools(payload, ctx),
        replace(payload, channels=channels),
        files,
        downmix_mode_off=(ffmpeg_down_mix == 2 and stereo_mix is StereoDownmix.DPLII)
        or upmix_50,
        bitrate=bitrate,
        fps=fps,
        delay=delay,
        dd_mode=DDEncodingMode.DD,
    )
    return JobPlan(
        format=spec.name,
        source=Path(payload.file_input),
        output=output,
        temp_dir=ctx.temp_dir,
        steps=(ffmpeg, DeeStep(tuple(dee_argv), files.output, payload.custom_dialnorm)),
        free_space_needed=info.recommended_free_space,
        preview=preview,
    )


# --- Dolby Digital Plus and DD+ Blu-ray


def ddp_auto_layouts() -> list[int]:
    """
    The DD+ layouts AUTO may pick: those DEE encodes without dee_shim.

    DD+ 7.1 needs dee_shim, which DeeZy doesn't drive yet, so AUTO encodes a
    7.1 source as 5.1 rather than refusing it.
    """
    spec = get_format("ddp")
    return [
        value
        for value in DolbyDigitalPlusChannels.get_values_list()
        if not spec.layout(str(DolbyDigitalPlusChannels(value))).needs_shim
    ]


def ddp_channel_resolver(source_channels: int) -> DolbyDigitalPlusChannels:
    """The DD+ layout AUTO picks, also for the config lookup."""
    if source_channels == 1:
        return DolbyDigitalPlusChannels.MONO
    if 1 < source_channels < 6:
        return DolbyDigitalPlusChannels.STEREO
    if source_channels == 6 or 8 not in ddp_auto_layouts():
        return DolbyDigitalPlusChannels.SURROUND
    return DolbyDigitalPlusChannels.SURROUNDEX


def secondary_bitrate(requested: int | None) -> int:
    """Blu-ray secondary audio only allows 192 or 256 kbps."""
    choices = SECONDARY_BITRATES
    if requested is None:
        return choices[0]
    closest = min(choices, key=lambda rate: abs(rate - requested))
    if closest != requested:
        logger.warning(
            f"Blu-ray secondary audio only allows {choices[0]} or {choices[1]} "
            f"kbps, using {closest}."
        )
    return closest


def _ddp_mode(
    channels: DolbyDigitalPlusChannels | DolbyDigitalPlusBlurayChannels,
    bluray_secondary: bool,
) -> DDEncodingMode:
    if bluray_secondary:
        if channels not in (
            DolbyDigitalPlusChannels.STEREO,
            DolbyDigitalPlusChannels.SURROUND,
        ):
            raise ChannelMixError(
                "Blu-ray secondary audio is only available as 2.0 or 5.1."
            )
        return DDEncodingMode.BLURAY_SECONDARY
    if isinstance(channels, DolbyDigitalPlusBlurayChannels):
        return DDEncodingMode.BLURAY
    if channels.value == 8:
        return DDEncodingMode.DDP71
    return DDEncodingMode.DDP


def _plan_ddp(payload: DDPPayload, info: AudioTrackInfo, ctx: PlanContext) -> JobPlan:
    bluray = isinstance(payload.channels, DolbyDigitalPlusBlurayChannels)
    format_command = CodecFormat.DDP_BLURAY if bluray else CodecFormat.DDP
    spec = get_format(str(format_command))
    source_channels = info.channels
    channels = payload.channels

    # a 5.0 source the user wants up-mixed to 5.1
    upmix_50 = (
        payload.upmix_50_to_51
        and channels is DolbyDigitalPlusChannels.SURROUND
        and source_channels == 5
    )
    if isinstance(channels, DolbyDigitalPlusBlurayChannels):
        bitrate_obj = DolbyDigitalPlusBlurayChannels.SURROUNDEX.get_bitrate_obj()
    elif channels is DolbyDigitalPlusChannels.AUTO:
        bitrate_obj = ddp_channel_resolver(source_channels).get_bitrate_obj()
    else:
        bitrate_obj = channels.get_bitrate_obj()
    bitrate = resolve_bitrate(
        ctx.config,
        format_command,
        payload.bitrate,
        channels,
        info,
        bitrate_obj,
        source_channels,
        DolbyDigitalPlusChannels.AUTO,
        ddp_channel_resolver,
    )

    if channels != DolbyDigitalPlusChannels.AUTO and not upmix_50:
        check_for_up_mixing(source_channels, channels.value)
    elif channels is DolbyDigitalPlusChannels.AUTO:
        accepted = ddp_auto_layouts()
        channels = DolbyDigitalPlusChannels(auto_channels(source_channels, accepted))
        logger.info(f"No supplied channels, defaulting to {channels}.")
        if source_channels == 8 and 8 not in accepted:
            logger.info(
                "Dolby Digital Plus 7.1 needs dee_shim, which this DeeZy version "
                "doesn't drive yet, so the 7.1 source is encoded as 5.1."
            )

    delay = get_delay(payload)
    fps = get_fps(info.fps)
    output, preview = _output(payload, info, ctx, spec, "DDP", str(channels), delay)

    # DEE takes the source's own layout, not the AUTO choice made from it
    dee_allowed_input = source_channels in DEE_INPUT_CHANNELS
    # DEE leaves the layout alone ('off') for 7.1, when it is the source's, or
    # when DEE can't take the source
    if isinstance(channels, DolbyDigitalPlusBlurayChannels):
        downmix_off = True
    else:
        downmix_off = (
            channels.value == source_channels
            or not dee_allowed_input
            or channels is DolbyDigitalPlusChannels.SURROUNDEX
        )
    ffmpeg_down_mix = None
    if (downmix_off and not dee_allowed_input) or upmix_50:
        ffmpeg_down_mix = channels.value
    output_channels = 8 if bluray else channels.value
    delay = _compensate(
        delay, spec, ffmpeg_down_mix or source_channels, output_channels
    )

    wav = WavFile(ctx.temp_dir / f"{artifact_stem(output)}.{format_command}.wav")
    resample = not info.sample_rate or info.sample_rate != DEE_SAMPLE_RATE
    if bluray or channels == DolbyDigitalPlusChannels.SURROUNDEX:
        filters = _filter_args(_PAN_7_1, resample)
    elif upmix_50:
        # the pan writes the 5.1 layout itself, so no -ac
        filters = _filter_args(_PAN_50_TO_51, resample)
    else:
        filters = _filter_args(None, resample)
    if ffmpeg_down_mix and not upmix_50:
        filters += ["-ac", f"{ffmpeg_down_mix}"]
    ffmpeg = _ffmpeg_step(payload, filters, wav, str(format_command), info)

    files = _dee_files(ctx, wav.dee_input, output)
    dee_argv = ddp_command(
        _tools(payload, ctx),
        replace(payload, channels=channels),
        files,
        downmix_mode_off=False,
        bitrate=secondary_bitrate(payload.bitrate)
        if payload.bluray_secondary
        else bitrate,
        fps=fps,
        delay=delay,
        dd_mode=_ddp_mode(channels, payload.bluray_secondary),
    )
    return JobPlan(
        format=spec.name,
        source=Path(payload.file_input),
        output=output,
        temp_dir=ctx.temp_dir,
        steps=(ffmpeg, DeeStep(tuple(dee_argv), files.output, payload.custom_dialnorm)),
        free_space_needed=info.recommended_free_space,
        preview=preview,
    )


# --- Dolby Digital Plus Atmos


def require_supported_atmos_mode(atmos_mode: AtmosMode) -> None:
    """Refuse an Atmos mode DeeZy can't encode yet, before any work starts."""
    if get_format("ddp-atmos").layout("atmos", mode=atmos_mode.value).needs_shim:
        # dee_ddpjoc_encoder's own Blu-ray mode gives a 5.1.2 bed; the 7.1 bed
        # needs dee_shim (--layout 7.1)
        raise UnsupportedDeeFeatureError(
            "DD+ Atmos for Blu-ray needs a 7.1 bed, which DEE 6.7 only encodes "
            "through dee_shim. This DeeZy version doesn't drive dee_shim yet; use "
            "'--atmos-mode streaming'."
        )


def _atmos_input(
    payload: AtmosPayload | Ac4Payload,
    info: AudioTrackInfo,
    ctx: PlanContext,
    reuse_id: str,
) -> tuple[TruehddStep | None, Path | None]:
    """The truehdd step and the DAMF it writes, or the ADM BWF as it is."""
    if info.thd_atmos:
        step = _truehdd_step(payload, info, ctx, reuse_id)
        return step, step.output
    if info.adm_atmos_wav:
        logger.info("Using ADM BWF input")
        return None, Path(payload.file_input)
    return None, None


def _plan_ddp_atmos(
    payload: AtmosPayload, info: AudioTrackInfo, ctx: PlanContext
) -> JobPlan:
    spec = get_format("ddp-atmos")
    require_supported_atmos_mode(payload.atmos_mode)
    bitrate = resolve_bitrate(
        ctx.config,
        CodecFormat.DDP_ATMOS,
        payload.bitrate,
        payload.atmos_mode,
        info,
        payload.atmos_mode.get_bitrate_obj(),
        info.channels,
        None,
        lambda _source: payload.atmos_mode,
    )
    check_for_up_mixing(info.channels, payload.atmos_mode.get_channels())

    delay = get_delay(payload).compensated(compensation(spec))
    fps = get_fps(info.fps)
    output, preview = _output(
        payload, info, ctx, spec, "DDP", payload.atmos_mode.get_str_channels(), delay
    )

    truehdd, dee_input = _atmos_input(payload, info, ctx, str(CodecFormat.DDP_ATMOS))
    if dee_input is None:
        raise InvalidAtmosInputError("Cannot process input, not a valid Atmos format")

    files = _dee_files(ctx, dee_input, output)
    dee_argv = ddpjoc_command(
        _tools(payload, ctx), payload, files, bitrate=bitrate, fps=fps, delay=delay
    )
    steps: tuple[Step, ...] = (
        DeeStep(tuple(dee_argv), files.output, payload.custom_dialnorm),
    )
    return JobPlan(
        format=spec.name,
        source=Path(payload.file_input),
        output=output,
        temp_dir=ctx.temp_dir,
        steps=(truehdd, *steps) if truehdd else steps,
        free_space_needed=info.recommended_free_space,
        preview=preview,
    )


# --- AC-4 immersive stereo


def _plan_ac4_ims(
    payload: Ac4Payload, info: AudioTrackInfo, ctx: PlanContext
) -> JobPlan:
    spec = get_format("ac4-ims")
    if info.thd_atmos:
        logger.debug("Input track is TrueHD Atmos")
    elif info.channels < 6:
        raise ChannelMixError(
            "AC-4 needs a source of at least 6 channels or TrueHD Atmos (the track "
            f"has {info.channels})."
        )
    bitrate = resolve_bitrate(
        ctx.config,
        CodecFormat.AC4_IMS,
        payload.bitrate,
        Ac4Channels.IMMERSIVE_STEREO,
        info,
        Ac4Channels.IMMERSIVE_STEREO.get_bitrate_obj(),
        info.channels,
        None,
        lambda _source: Ac4Channels.IMMERSIVE_STEREO,
    )

    delay = get_delay(payload).compensated(compensation(spec))
    fps = get_fps(info.fps)
    output, preview = _output(payload, info, ctx, spec, "AC-4", "2.0", delay)

    truehdd, dee_input = _atmos_input(payload, info, ctx, str(CodecFormat.AC4_IMS))
    steps: list[Step] = [truehdd] if truehdd else []
    if dee_input is None:
        # channel-based input, at least 6 channels (checked above)
        wav = WavFile(
            ctx.temp_dir / f"{artifact_stem(output)}.{CodecFormat.AC4_IMS}.wav"
        )
        resample = bool(info.sample_rate and info.sample_rate != DEE_SAMPLE_RATE)
        filters = _filter_args(_PAN_7_1 if info.channels == 8 else None, resample)
        # dee_ac4ims_encoder takes 5.1
        if info.channels != 6:
            filters += ["-ac", "6"]
        steps.append(
            _ffmpeg_step(payload, filters, wav, str(CodecFormat.AC4_IMS), info)
        )
        dee_input = wav.dee_input

    files = _dee_files(ctx, dee_input, output)
    dee_argv = ac4ims_command(
        _tools(payload, ctx),
        payload,
        files,
        bitrate=bitrate,
        fps=fps,
        delay=delay,
        atmos_input=bool(info.adm_atmos_wav or info.thd_atmos),
    )
    steps.append(DeeStep(tuple(dee_argv), files.output))
    return JobPlan(
        format=spec.name,
        source=Path(payload.file_input),
        output=output,
        temp_dir=ctx.temp_dir,
        steps=tuple(steps),
        free_space_needed=info.recommended_free_space,
        preview=preview,
    )
