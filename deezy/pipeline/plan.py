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
    THD_APODISED_RATE,
    THD_ATMOS_ELEMENTS,
    DeeFiles,
    DeeTools,
    aac_command,
    ac4_command,
    ac4ajoc_command,
    ac4ims_command,
    check_atmos_options,
    ddp_command,
    ddpjoc_command,
    measure_command,
    thd_atmos_command,
    thd_command,
)
from deezy.dee.spec import FormatSpec, get_format
from deezy.delay import Delay, compensation
from deezy.enums.ac4 import Ac4ChannelBasedChannels, Ac4Channels
from deezy.enums.atmos import WarpMode
from deezy.enums.channel_count import ChannelCount
from deezy.enums.codec_format import CodecFormat
from deezy.enums.dd import DolbyDigitalChannels
from deezy.enums.ddp import DolbyDigitalPlusChannels
from deezy.enums.ddp_bluray import DolbyDigitalPlusBlurayChannels
from deezy.enums.shared import (
    DDEncodingMode,
    DeeFPS,
    PipeMode,
    StereoDownmix,
    TrackType,
)
from deezy.enums.thd import TrueHDChannels
from deezy.exceptions import (
    AutoChannelDetectionError,
    ChannelMixError,
    DependencyNotFoundError,
    InvalidAtmosInputError,
    InvalidExtensionError,
    PipeError,
    UnsupportedDeeFeatureError,
)
from deezy.payloads.aac import AacPayload
from deezy.payloads.ac4 import Ac4AtmosPayload, Ac4ChannelPayload, Ac4Payload
from deezy.payloads.atmos import AtmosPayload
from deezy.payloads.dd import DDPayload
from deezy.payloads.ddp import DDPPayload
from deezy.payloads.measure import MeasurePayload
from deezy.payloads.shared import ChannelBitrates, CorePayload
from deezy.payloads.thd import TrueHDAtmosPayload, TrueHDPayload
from deezy.pipeline.transport import NamedPipe, Transport, WavFile, expected_samples
from deezy.track_info.audio_track_info import AudioTrackInfo
from deezy.track_info.track_index import TrackIndex
from deezy.track_info.utils import parse_delay_from_file
from deezy.utils.logger import logger
from deezy.utils.paths import artifact_stem

# the payloads that take TrueHD Atmos or an Atmos master
AtmosInputPayload = (
    AtmosPayload | Ac4Payload | Ac4AtmosPayload | MeasurePayload | TrueHDAtmosPayload
)

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


@dataclass(frozen=True, slots=True)
class PipeStep:
    """
    FFmpeg streaming PCM into DEE through a named pipe. DEE starts first, since
    it creates the pipe, and the two then run at once.
    """

    ffmpeg_argv: tuple[str, ...]
    dee: DeeStep
    pipe: NamedPipe
    duration: float | None = None


Step = FfmpegStep | TruehddStep | DeeStep | PipeStep


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
    # the job's named pipe, on a platform where DeeZy can pipe PCM into DEE
    pipe_name: str | None = None


def plan_job(payload: CorePayload, info: AudioTrackInfo, ctx: PlanContext) -> JobPlan:
    """The plan for one encode. ``info`` is the probed source track."""
    if info.atmos_master:
        if isinstance(payload, DDPayload | DDPPayload):
            return _plan_dd_render(payload, info, ctx)
        if not isinstance(
            payload, AtmosPayload | Ac4Payload | Ac4AtmosPayload | TrueHDAtmosPayload
        ):
            raise InvalidAtmosInputError(
                f"{_format_name(payload)} can't encode an Atmos master yet: FFmpeg "
                "would mix its objects without their positions. Encode it with dd, "
                "ddp, ddp-atmos, thd-atmos, ac4-atmos or ac4-ims, or measure it "
                "with 'deezy measure'."
            )
    if isinstance(payload, DDPayload):
        return _plan_dd(payload, info, ctx)
    if isinstance(payload, DDPPayload):
        return _plan_ddp(payload, info, ctx)
    if isinstance(payload, AtmosPayload):
        return _plan_ddp_atmos(payload, info, ctx)
    if isinstance(payload, Ac4Payload):
        return _plan_ac4_ims(payload, info, ctx)
    if isinstance(payload, Ac4AtmosPayload):
        return _plan_ac4_atmos(payload, info, ctx)
    if isinstance(payload, AacPayload):
        return _plan_aac(payload, info, ctx)
    if isinstance(payload, Ac4ChannelPayload):
        return _plan_ac4(payload, info, ctx)
    if isinstance(payload, TrueHDPayload):
        return _plan_thd(payload, info, ctx)
    if isinstance(payload, TrueHDAtmosPayload):
        return _plan_thd_atmos(payload, info, ctx)
    raise TypeError(f"no plan for {type(payload).__name__}")


def _format_name(payload: CorePayload) -> str:
    names = {
        DDPayload: "dd",
        DDPPayload: "ddp",
        AacPayload: "aac",
        Ac4ChannelPayload: "ac4",
        TrueHDPayload: "thd",
    }
    return names.get(type(payload), type(payload).__name__)


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
    delay: Delay,
    spec: FormatSpec,
    dee_input_channels: int,
    dee_output_channels: int,
    *,
    mode: str | None = None,
    bitrate: int | None = None,
) -> Delay:
    """
    `delay`, less the samples DEE adds to this encode. ``mode`` and ``bitrate``
    are for an encoder whose delay depends on the rate.
    """
    channel_change = dee_input_channels != dee_output_channels
    delay = delay.compensated(
        compensation(spec, channel_change=channel_change, mode=mode, bitrate=bitrate)
    )
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
    transport: Transport,
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
        transport.ffmpeg_codec,
        *filters,
        "-map_metadata",
        "-1",
        *transport.ffmpeg_output(),
    )


def _filter_args(
    mix: str | None, resample: bool, rate: int = DEE_SAMPLE_RATE
) -> list[str]:
    """``-af`` with a channel mix, the resampler to ``rate``, or both."""
    chain = [f for f in (mix, _RESAMPLE if resample else None) if f]
    args = ["-af", ",".join(chain)] if chain else []
    if resample:
        args += ["-ar", str(rate)]
    return args


def _pcm_steps(
    payload: CorePayload,
    filters: list[str],
    transport: Transport,
    reuse_id: str,
    info: AudioTrackInfo,
    dee: DeeStep,
) -> tuple[Step, ...]:
    """FFmpeg's step and DEE's, or the one step that pipes one into the other."""
    argv = ffmpeg_argv(
        payload.ffmpeg_path,
        Path(payload.file_input),
        payload.track_index,
        filters,
        transport,
    )
    if isinstance(transport, NamedPipe):
        return (PipeStep(argv, dee, transport, duration=info.duration),)
    return (
        FfmpegStep(
            argv=argv, output=transport.path, reuse_id=reuse_id, duration=info.duration
        ),
        dee,
    )


def choose_transport(
    payload: CorePayload,
    ctx: PlanContext,
    wav: Path,
    channels: int,
    duration: float | None = None,
) -> Transport:
    """
    A named pipe for ``--pipe auto`` or ``always``, else the WAV at ``wav``.

    ``channels`` is what FFmpeg writes, and ``duration`` the source's length in
    milliseconds, which sets the pipe's sample count. ``auto`` falls back to the WAV
    where a pipe can't be used; ``always`` refuses there instead.
    """
    mode = getattr(payload, "pipe", PipeMode.NEVER)
    if mode is PipeMode.NEVER:
        return WavFile(wav)
    reason = None
    if ctx.pipe_name is None:
        reason = "DeeZy pipes PCM into DEE only on Windows"
    elif payload.reuse_temp_files:
        reason = "--reuse-temp-files needs the temp WAV, which a pipe doesn't write"
    if reason is None:
        return NamedPipe(str(ctx.pipe_name), channels, expected_samples(duration))
    if mode is PipeMode.ALWAYS:
        raise PipeError(f"--pipe always: {reason}. Use --pipe auto or never.")
    logger.debug(f"Writing a temp WAV for DEE: {reason}.")
    return WavFile(wav)


def dee_output_path(temp_dir: Path, output: Path) -> Path:
    """
    Where DEE encodes to: inside the temp directory, under a bounded name.

    DEE never writes to the destination, so it is only handed paths whose length
    DeeZy controls, and a failed encode leaves nothing at the destination.
    """
    return temp_dir / f"{artifact_stem(output)}{output.suffix}"


def _dee_files(ctx: PlanContext, dee_input: Path | Transport, output: Path) -> DeeFiles:
    """DEE's files. A transport also sets the input format, unless it's a WAV."""
    if isinstance(dee_input, NamedPipe):
        return DeeFiles(
            input=dee_input.dee_input,
            output=dee_output_path(ctx.temp_dir, output),
            temp_dir=ctx.temp_dir,
            input_format=dee_input.dee_input_format,
        )
    if isinstance(dee_input, WavFile):
        dee_input = dee_input.dee_input
    return DeeFiles(
        input=dee_input,
        output=dee_output_path(ctx.temp_dir, output),
        temp_dir=ctx.temp_dir,
    )


def _tools(payload: CorePayload, ctx: PlanContext) -> DeeTools:
    return DeeTools(Path(payload.dee_path), ctx.license, payload.dee_shim)


def _truehdd_step(
    payload: AtmosInputPayload,
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
    # DPL II is a stereo mix FFmpeg makes. A DD stream of any other layout can
    # only carry the preferred-downmix flag, and AC-3 has no DPL II one (DEE
    # refuses ltrt-pl2 for DD), so it gets Lt/Rt, the matrix-surround flag
    if stereo_mix is StereoDownmix.DPLII and not dplii:
        logger.info(
            "DD has no DPL II downmix flag, so the stream is marked Lt/Rt "
            "preferred. A DPL II mix needs --channels 2."
        )
        payload = replace(payload, preferred_downmix_mode=StereoDownmix.LTRT)
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
    # what FFmpeg hands DEE
    dee_input_channels = ffmpeg_down_mix or source_channels
    delay = _compensate(delay, spec, dee_input_channels, channels.value)

    transport = choose_transport(
        payload,
        ctx,
        ctx.temp_dir / f"{artifact_stem(output)}.{CodecFormat.DD}.wav",
        dee_input_channels,
        info.duration,
    )
    resample = not info.sample_rate or info.sample_rate != DEE_SAMPLE_RATE
    if dplii:
        filters = _filter_args(_DPLII, resample)
    elif upmix_50:
        # the pan writes the 5.1 layout itself, so no -ac
        filters = _filter_args(_PAN_50_TO_51, resample)
    else:
        filters = _filter_args(None, resample)
    # a DPL II request on a non-stereo output has no FFmpeg mix, so no -ac
    if ffmpeg_down_mix and not upmix_50:
        filters += ["-ac", f"{ffmpeg_down_mix}"]

    files = _dee_files(ctx, transport, output)
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
    dee = DeeStep(tuple(dee_argv), files.output, payload.custom_dialnorm)
    return JobPlan(
        format=spec.name,
        source=Path(payload.file_input),
        output=output,
        temp_dir=ctx.temp_dir,
        steps=_pcm_steps(payload, filters, transport, str(CodecFormat.DD), info, dee),
        free_space_needed=info.recommended_free_space,
        preview=preview,
    )


# --- Dolby Digital Plus and DD+ Blu-ray


def ddp_auto_layouts(shim: bool = False) -> list[int]:
    """
    The DD+ layouts AUTO may pick: those DEE encodes alone, and with ``shim``
    (DeeZy has dee_shim) also those that need it, which is 7.1.

    Without dee_shim, AUTO encodes a 7.1 source as 5.1 rather than refusing it.
    """
    spec = get_format("ddp")
    return [
        value
        for value in DolbyDigitalPlusChannels.get_values_list()
        if shim or not spec.layout(str(DolbyDigitalPlusChannels(value))).needs_shim
    ]


def ddp_channel_resolver(
    source_channels: int, shim: bool = False
) -> DolbyDigitalPlusChannels:
    """The DD+ layout AUTO picks, also for the config lookup."""
    if source_channels == 1:
        return DolbyDigitalPlusChannels.MONO
    if 1 < source_channels < 6:
        return DolbyDigitalPlusChannels.STEREO
    if source_channels < 8 or 8 not in ddp_auto_layouts(shim):
        return DolbyDigitalPlusChannels.SURROUND
    return DolbyDigitalPlusChannels.SURROUNDEX


def secondary_bitrate(requested: int | None, layout: str) -> int:
    """
    The Blu-ray secondary audio rate: the requested one if DEE takes it for
    ``layout`` ('2.0' or '5.1'), else the next allowed one up. DeeZy's default
    is 192 kbps.
    """
    rates = get_format("ddp-bluray").rates(layout, mode="bluray_secondary")
    if requested is None:
        return rates.default
    if rates.is_valid_bitrate(requested):
        return requested
    closest = rates.get_closest_bitrate(requested)
    logger.warning(
        f"Blu-ray secondary audio {layout} takes "
        f"{', '.join(str(rate) for rate in rates.choices)} kbps, using {closest}."
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
    # AUTO may pick 7.1 with dee_shim; Blu-ray secondary audio stops at 5.1
    shim_71 = payload.dee_shim is not None and not payload.bluray_secondary

    def resolver(count: int) -> DolbyDigitalPlusChannels:
        return ddp_channel_resolver(count, shim_71)

    # a 5.0 source the user wants up-mixed to 5.1
    upmix_50 = (
        payload.upmix_50_to_51
        and channels is DolbyDigitalPlusChannels.SURROUND
        and source_channels == 5
    )
    if isinstance(channels, DolbyDigitalPlusBlurayChannels):
        bitrate_obj = DolbyDigitalPlusBlurayChannels.SURROUNDEX.get_bitrate_obj()
    elif channels is DolbyDigitalPlusChannels.AUTO:
        bitrate_obj = resolver(source_channels).get_bitrate_obj()
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
        resolver,
    )

    if channels != DolbyDigitalPlusChannels.AUTO and not upmix_50:
        check_for_up_mixing(source_channels, channels.value)
    elif channels is DolbyDigitalPlusChannels.AUTO:
        accepted = ddp_auto_layouts(shim_71)
        channels = DolbyDigitalPlusChannels(auto_channels(source_channels, accepted))
        logger.info(f"No supplied channels, defaulting to {channels}.")
        if source_channels == 8 and 8 not in accepted and not payload.bluray_secondary:
            logger.info(
                "Dolby Digital Plus 7.1 needs dee_shim, which DeeZy didn't find or "
                "was told not to use (--no-shim), so the 7.1 source is encoded as 5.1."
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
    # what FFmpeg hands DEE
    dee_input_channels = ffmpeg_down_mix or source_channels
    delay = _compensate(delay, spec, dee_input_channels, output_channels)

    transport = choose_transport(
        payload,
        ctx,
        ctx.temp_dir / f"{artifact_stem(output)}.{format_command}.wav",
        dee_input_channels,
        info.duration,
    )
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

    # refuses a secondary layout other than 2.0 or 5.1
    dd_mode = _ddp_mode(channels, payload.bluray_secondary)
    if payload.bluray_secondary:
        bitrate = secondary_bitrate(payload.bitrate, str(channels))
    files = _dee_files(ctx, transport, output)
    dee_argv = ddp_command(
        _tools(payload, ctx),
        replace(payload, channels=channels),
        files,
        downmix_mode_off=False,
        bitrate=bitrate,
        fps=fps,
        delay=delay,
        dd_mode=dd_mode,
    )
    dee = DeeStep(tuple(dee_argv), files.output, payload.custom_dialnorm)
    return JobPlan(
        format=spec.name,
        source=Path(payload.file_input),
        output=output,
        temp_dir=ctx.temp_dir,
        steps=_pcm_steps(payload, filters, transport, str(format_command), info, dee),
        free_space_needed=info.recommended_free_space,
        preview=preview,
    )


# --- DD and DD+ rendered from an Atmos master

# the layout DEE renders a master to when none is asked for, and the one its
# delay is counted from: a 2.0 or 1.0 render adds the 32 samples of a downmix
MASTER_RENDER_CHANNELS = 6


def _plan_dd_render(
    payload: DDPayload | DDPPayload, info: AudioTrackInfo, ctx: PlanContext
) -> JobPlan:
    """
    DD or DD+ from a DAMF or ADM BWF master, which DEE renders to the layout
    asked for (1.0, 2.0 or 5.1). No FFmpeg step: the master goes to DEE as it
    is. A TrueHD Atmos stream is not a master here; FFmpeg decodes its 7.1
    presentation as for any other source.
    """
    dd = isinstance(payload, DDPayload)
    format_command = CodecFormat.DD if dd else CodecFormat.DDP
    name = str(format_command)
    if isinstance(payload.channels, DolbyDigitalPlusBlurayChannels):
        raise InvalidAtmosInputError(
            "ddp-bluray can't encode an Atmos master: DEE's Blu-ray 7.1 mode "
            "doesn't take one. Encode it as 5.1 with ddp, or with ddp-atmos."
        )
    spec = get_format(name)
    layouts = DolbyDigitalChannels if dd else DolbyDigitalPlusChannels
    surround = layouts.SURROUND
    channels = payload.channels
    if channels.value == 8:
        raise ChannelMixError(
            "DEE renders an Atmos master to 5.1 at most for DD+; use --channels 6, "
            "or ddp-atmos to keep the objects."
        )
    kind = "DAMF" if info.damf_atmos else "ADM BWF"
    if channels.value == 0:
        channels = surround
        logger.info(f"No supplied channels, defaulting to {channels}.")
    logger.info(f"DEE renders the {kind} master to {channels}.")
    stereo = channels.value == 2

    stereo_mix = payload.preferred_downmix_mode
    if stereo and stereo_mix in (StereoDownmix.LTRT, StereoDownmix.DPLII):
        # DEE renders a master's 2.0 itself; a downmix mode changes no byte of it
        raise UnsupportedDeeFeatureError(
            f"--stereo-down-mix {stereo_mix.value} can't apply to a 2.0 render of an "
            "Atmos master: DEE renders the 2.0 itself and takes no downmix mode "
            "for it. Leave it at loro, or encode 5.1."
        )
    if dd and stereo_mix is StereoDownmix.DPLII and not stereo:
        # as for PCM: AC-3 has no DPL II flag (DEE refuses ltrt-pl2 for DD)
        logger.info(
            "DD has no DPL II downmix flag, so the stream is marked Lt/Rt preferred."
        )
        payload = replace(payload, preferred_downmix_mode=StereoDownmix.LTRT)
    if payload.pipe is PipeMode.ALWAYS:
        logger.info("--pipe always: the master goes to DEE as it is, with no PCM.")

    bluray_secondary = bool(getattr(payload, "bluray_secondary", False))
    if dd:
        dd_mode = DDEncodingMode.DD
    else:
        # refuses a secondary layout other than 2.0 or 5.1
        dd_mode = _ddp_mode(channels, bluray_secondary)
    if bluray_secondary:
        bitrate = secondary_bitrate(payload.bitrate, str(channels))
    else:
        bitrate = resolve_bitrate(
            ctx.config,
            format_command,
            payload.bitrate,
            payload.channels,
            info,
            channels.get_bitrate_obj(),
            info.channels,
            layouts.AUTO,
            lambda _source: surround,
        )

    delay = get_delay(payload)
    fps = get_fps(info.fps)
    label = "DD" if dd else "DDP"
    output, preview = _output(payload, info, ctx, spec, label, str(channels), delay)
    delay = _compensate(delay, spec, MASTER_RENDER_CHANNELS, channels.value)

    files = replace(
        _dee_files(ctx, Path(payload.file_input), output), input_format="atmos_mezz"
    )
    dee_argv = ddp_command(
        _tools(payload, ctx),
        replace(payload, channels=channels),
        files,
        downmix_mode_off=False,
        bitrate=bitrate,
        fps=fps,
        delay=delay,
        dd_mode=dd_mode,
    )
    return JobPlan(
        format=spec.name,
        source=Path(payload.file_input),
        output=output,
        temp_dir=ctx.temp_dir,
        steps=(DeeStep(tuple(dee_argv), files.output, payload.custom_dialnorm),),
        free_space_needed=info.recommended_free_space,
        preview=preview,
    )


# --- Dolby Digital Plus Atmos


def _atmos_input(
    payload: AtmosInputPayload,
    info: AudioTrackInfo,
    ctx: PlanContext,
    reuse_id: str,
) -> tuple[TruehddStep | None, Path | None]:
    """The truehdd step and the DAMF it writes, or the master as it is."""
    if info.thd_atmos:
        step = _truehdd_step(payload, info, ctx, reuse_id)
        return step, step.output
    if info.atmos_master:
        kind = "DAMF" if info.damf_atmos else "ADM BWF"
        logger.info(f"Using the {kind} master as it is")
        if payload.thd_warp_mode is not None:
            logger.warning(
                "--thd-warp-mode applies to TrueHD Atmos only; DEE renders the "
                "master with the warp mode it was authored with."
            )
        return None, Path(payload.file_input)
    return None, None


def _plan_ddp_atmos(
    payload: AtmosPayload, info: AudioTrackInfo, ctx: PlanContext
) -> JobPlan:
    spec = get_format("ddp-atmos")
    # before any work, and before the rate lookup warns about a rate
    check_atmos_options(payload, shim=payload.dee_shim is not None)
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
    if not info.atmos_master:
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


# --- channel-based AC-4

# the layouts dee_ac4_encoder reads; FFmpeg converts any other one first
AC4_INPUT_CHANNELS = (2, 6, 8)


def ac4_channel_resolver(source_channels: int) -> Ac4ChannelBasedChannels:
    """The AC-4 layout AUTO picks, also for the config lookup."""
    if source_channels < 6:
        return Ac4ChannelBasedChannels.STEREO
    return Ac4ChannelBasedChannels.SURROUND


def _plan_ac4(
    payload: Ac4ChannelPayload, info: AudioTrackInfo, ctx: PlanContext
) -> JobPlan:
    spec = get_format("ac4")
    # D2: 1.x's 'ac4' was immersive stereo, so an old preset lands here
    logger.info(
        "'ac4' is channel-based AC-4 (2.0 or 5.1) since DeeZy 2.0; immersive "
        "stereo is 'ac4-ims'."
    )
    source_channels = info.channels
    channels = payload.channels
    bitrate_obj = (
        ac4_channel_resolver(source_channels).get_bitrate_obj()
        if channels is Ac4ChannelBasedChannels.AUTO
        else channels.get_bitrate_obj()
    )
    bitrate = resolve_bitrate(
        ctx.config,
        CodecFormat.AC4,
        payload.bitrate,
        channels,
        info,
        bitrate_obj,
        source_channels,
        Ac4ChannelBasedChannels.AUTO,
        ac4_channel_resolver,
    )

    if channels is Ac4ChannelBasedChannels.AUTO:
        channels = ac4_channel_resolver(source_channels)
        logger.info(f"No supplied channels, defaulting to {channels}.")
    elif source_channels != 1:
        check_for_up_mixing(source_channels, channels.value)
    if source_channels == 1:
        if channels is not Ac4ChannelBasedChannels.STEREO:
            raise ChannelMixError("Up-mixing is not supported.")
        logger.info(
            "AC-4 has no 1.0 layout, so the mono source is encoded as 2.0 with "
            "the same signal in both channels."
        )

    delay = get_delay(payload)
    fps = get_fps(info.fps)
    output, preview = _output(payload, info, ctx, spec, "AC-4", str(channels), delay)

    ffmpeg_down_mix = None if source_channels in AC4_INPUT_CHANNELS else channels.value
    dee_input_channels = ffmpeg_down_mix or source_channels
    delay = _compensate(delay, spec, dee_input_channels, channels.value)

    transport = choose_transport(
        payload,
        ctx,
        ctx.temp_dir / f"{artifact_stem(output)}.{CodecFormat.AC4}.wav",
        dee_input_channels,
        info.duration,
    )
    resample = not info.sample_rate or info.sample_rate != DEE_SAMPLE_RATE
    filters = _filter_args(_PAN_7_1 if source_channels == 8 else None, resample)
    if ffmpeg_down_mix:
        filters += ["-ac", str(ffmpeg_down_mix)]

    files = _dee_files(ctx, transport, output)
    dee_argv = ac4_command(
        _tools(payload, ctx),
        replace(payload, channels=channels),
        files,
        manifest=ctx.temp_dir / f"{artifact_stem(output)}.manifest.json",
        bitrate=bitrate,
        fps=fps,
        delay=delay,
    )
    dee = DeeStep(tuple(dee_argv), files.output)
    return JobPlan(
        format=spec.name,
        source=Path(payload.file_input),
        output=output,
        temp_dir=ctx.temp_dir,
        steps=_pcm_steps(payload, filters, transport, str(CodecFormat.AC4), info, dee),
        free_space_needed=info.recommended_free_space,
        preview=preview,
    )


# --- AC-4 immersive stereo


def _plan_ac4_ims(
    payload: Ac4Payload, info: AudioTrackInfo, ctx: PlanContext
) -> JobPlan:
    spec = get_format("ac4-ims")
    if info.atmos:
        logger.debug("Input track is Atmos")
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
        # channel-based input, at least 6 channels (checked above). It keeps
        # the WAV: dee_ac4ims_encoder has no --temp-dir and no skip mode, so
        # it would buffer piped PCM somewhere DeeZy doesn't choose
        wav = WavFile(
            ctx.temp_dir / f"{artifact_stem(output)}.{CodecFormat.AC4_IMS}.wav"
        )
        resample = bool(info.sample_rate and info.sample_rate != DEE_SAMPLE_RATE)
        filters = _filter_args(_PAN_7_1 if info.channels == 8 else None, resample)
        # dee_ac4ims_encoder takes 5.1
        if info.channels != 6:
            filters += ["-ac", "6"]
        argv = ffmpeg_argv(
            payload.ffmpeg_path,
            Path(payload.file_input),
            payload.track_index,
            filters,
            wav,
        )
        steps.append(
            FfmpegStep(argv, wav.path, str(CodecFormat.AC4_IMS), info.duration)
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
        atmos_input=info.atmos,
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


# --- AC-4 Atmos

# DeeZy's config key and layout name for AC-4 Atmos, which has no channel layout
AC4_ATMOS = "atmos"


def _plan_ac4_atmos(
    payload: Ac4AtmosPayload, info: AudioTrackInfo, ctx: PlanContext
) -> JobPlan:
    spec = get_format("ac4-atmos")
    if not info.atmos:
        raise InvalidAtmosInputError(
            "ac4-atmos encodes TrueHD Atmos or an Atmos master (DAMF or ADM BWF). "
            "Encode channel-based audio with 'ac4'."
        )
    bitrate = resolve_bitrate(
        ctx.config,
        CodecFormat.AC4_ATMOS,
        payload.bitrate,
        AC4_ATMOS,
        info,
        spec.rates(AC4_ATMOS),
        info.channels,
        None,
        lambda _source: AC4_ATMOS,
    )

    delay = get_delay(payload).compensated(compensation(spec))
    fps = get_fps(info.fps)
    output, preview = _output(payload, info, ctx, spec, "AC-4", "Atmos", delay)

    truehdd, dee_input = _atmos_input(payload, info, ctx, str(CodecFormat.AC4_ATMOS))
    if dee_input is None:
        raise InvalidAtmosInputError("Cannot process input, not a valid Atmos format")

    files = _dee_files(ctx, dee_input, output)
    dee_argv = ac4ajoc_command(
        _tools(payload, ctx),
        payload,
        files,
        manifest=ctx.temp_dir / f"{artifact_stem(output)}.manifest.json",
        bitrate=bitrate,
        fps=fps,
        delay=delay,
    )
    steps: tuple[Step, ...] = (DeeStep(tuple(dee_argv), files.output),)
    return JobPlan(
        format=spec.name,
        source=Path(payload.file_input),
        output=output,
        temp_dir=ctx.temp_dir,
        steps=(truehdd, *steps) if truehdd else steps,
        free_space_needed=info.recommended_free_space,
        preview=preview,
    )


# --- AAC


def _plan_aac(payload: AacPayload, info: AudioTrackInfo, ctx: PlanContext) -> JobPlan:
    spec = get_format("aac")
    profile = payload.aac_profile
    source_channels = info.channels
    bitrate = resolve_bitrate(
        ctx.config,
        CodecFormat.AAC,
        payload.bitrate,
        profile,
        info,
        profile.get_bitrate_obj(),
        source_channels,
        None,
        lambda _source: profile,
    )

    delay = get_delay(payload)
    fps = get_fps(info.fps)
    output, preview = _output(payload, info, ctx, spec, "AAC", "2.0", delay)

    # dee_aac_encoder takes 1.0, 2.0, 5.1 and 7.1 and always encodes 2.0;
    # FFmpeg downmixes any other layout to 2.0 first
    ffmpeg_down_mix = None if source_channels in DEE_INPUT_CHANNELS else 2
    dee_input_channels = ffmpeg_down_mix or source_channels
    delay = _compensate(
        delay, spec, dee_input_channels, 2, mode=profile.value, bitrate=bitrate
    )

    transport = choose_transport(
        payload,
        ctx,
        ctx.temp_dir / f"{artifact_stem(output)}.{CodecFormat.AAC}.wav",
        dee_input_channels,
        info.duration,
    )
    resample = not info.sample_rate or info.sample_rate != DEE_SAMPLE_RATE
    filters = _filter_args(_PAN_7_1 if source_channels == 8 else None, resample)
    if ffmpeg_down_mix:
        filters += ["-ac", str(ffmpeg_down_mix)]

    files = _dee_files(ctx, transport, output)
    dee_argv = aac_command(
        _tools(payload, ctx), payload, files, bitrate=bitrate, fps=fps, delay=delay
    )
    dee = DeeStep(tuple(dee_argv), files.output)
    return JobPlan(
        format=spec.name,
        source=Path(payload.file_input),
        output=output,
        temp_dir=ctx.temp_dir,
        steps=_pcm_steps(payload, filters, transport, str(CodecFormat.AAC), info, dee),
        free_space_needed=info.recommended_free_space,
        preview=preview,
    )


# --- channel-based TrueHD

# FFmpeg's conversions that keep each source channel as it is and add silent
# ones (a back centre, which TrueHD has no slot for, is split between the
# surrounds)
_MONO_TO_STEREO = "pan=stereo|c0=c0|c1=c0"
_PAD_TO_51 = "aformat=channel_layouts=5.1|5.1(side)"
_PAD_TO_71 = "aformat=channel_layouts=7.1"
THD_SAMPLE_RATES = (48000, 96000)


def thd_channel_resolver(source_channels: int) -> TrueHDChannels:
    """The TrueHD layout AUTO picks: the smallest that holds every channel."""
    if source_channels <= 2:
        return TrueHDChannels.STEREO
    if source_channels <= 6:
        return TrueHDChannels.SURROUND
    return TrueHDChannels.SURROUNDEX


def thd_sample_rate(source_rate: int | None) -> int:
    """The rate DEE encodes: 96 kHz for a source above 48 kHz, else 48 kHz."""
    return 96000 if source_rate and source_rate > 48000 else 48000


def _thd_mix(
    source_channels: int, channels: TrueHDChannels
) -> tuple[str | None, int | None]:
    """The ``-af`` channel filter and the ``-ac`` count that give DEE ``channels``."""
    if channels is TrueHDChannels.SURROUNDEX:
        # DEE's 7.1 has the sides before the backs
        if source_channels == 8:
            return _PAN_7_1, None
        return f"{_PAD_TO_71},{_PAN_7_1}", None
    if source_channels == channels.value:
        return None, None
    if source_channels < channels.value:
        return (_MONO_TO_STEREO if source_channels == 1 else _PAD_TO_51), None
    # a downmix the user asked for
    return None, channels.value


def _plan_thd(
    payload: TrueHDPayload, info: AudioTrackInfo, ctx: PlanContext
) -> JobPlan:
    spec = get_format("thd")
    source_channels = info.channels
    fits = thd_channel_resolver(source_channels)
    channels = payload.channels
    if channels is TrueHDChannels.AUTO:
        channels = fits
        logger.info(f"No supplied channels, defaulting to {channels}.")
    elif channels.value > fits.value:
        raise ChannelMixError("Up-mixing is not supported.")
    if source_channels == 1:
        logger.info(
            "TrueHD has no 1.0 layout, so the mono source is encoded as 2.0 with "
            "the source unchanged in both channels."
        )
    elif source_channels < channels.value:
        logger.info(
            f"TrueHD has no {source_channels}-channel layout, so the source is "
            f"encoded as {channels} with silent channels added. Every channel is "
            "kept as it is, except a back centre, which is split between the "
            "surrounds."
        )

    rate = thd_sample_rate(info.sample_rate)
    shim = payload.dee_shim is not None
    if rate == THD_APODISED_RATE and not (shim and payload.as_is):
        # through dee_shim the filter is off, and the stream decodes exactly
        logger.info(
            "DEE applies its apodizing filter to a 96 kHz TrueHD encode, so the "
            "audio is filtered, not bit-exact"
            + ("." if shim else "; through dee_shim DeeZy turns it off.")
        )

    delay = get_delay(payload).compensated(compensation(spec))
    fps = get_fps(info.fps)
    output, preview = _output(payload, info, ctx, spec, "TrueHD", str(channels), delay)

    # dee_dthd_encoder reads WAV only
    wav = WavFile(ctx.temp_dir / f"{artifact_stem(output)}.{CodecFormat.THD}.wav")
    mix, down_mix = _thd_mix(source_channels, channels)
    filters = _filter_args(mix, info.sample_rate != rate, rate)
    if down_mix:
        filters += ["-ac", str(down_mix)]

    files = _dee_files(ctx, wav, output)
    dee_argv = thd_command(
        _tools(payload, ctx),
        replace(payload, channels=channels),
        files,
        fps=fps,
        delay=delay,
        sample_rate=rate,
    )
    dee = DeeStep(tuple(dee_argv), files.output, payload.custom_dialnorm)
    return JobPlan(
        format=spec.name,
        source=Path(payload.file_input),
        output=output,
        temp_dir=ctx.temp_dir,
        steps=_pcm_steps(payload, filters, wav, str(CodecFormat.THD), info, dee),
        free_space_needed=info.recommended_free_space,
        preview=preview,
    )


# --- TrueHD Atmos


def thd_atmos_fits(payload: TrueHDAtmosPayload, info: AudioTrackInfo) -> bool:
    """
    Whether dee_shim may code the master as it is: it has no more elements
    than the stream codes. truehdd's decode of TrueHD Atmos always fits; a
    DAMF master's elements are its CAF channels, an ADM BWF master's its WAV
    channels.
    """
    if info.thd_atmos:
        return True
    if not info.atmos_master:
        return False
    if info.channels > THD_ATMOS_ELEMENTS:
        if payload.dee_shim is not None and payload.as_is:
            logger.info(
                f"The master has {info.channels} elements, more than the "
                f"{THD_ATMOS_ELEMENTS} TrueHD Atmos codes, so DEE clusters it as "
                "usual and the stream doesn't decode to it sample for sample."
            )
        return False
    return True


def _plan_thd_atmos(
    payload: TrueHDAtmosPayload, info: AudioTrackInfo, ctx: PlanContext
) -> JobPlan:
    spec = get_format("thd-atmos")
    if not info.atmos:
        raise InvalidAtmosInputError(
            "thd-atmos encodes TrueHD Atmos or an Atmos master (DAMF or ADM BWF). "
            "Encode channel-based audio with 'thd'."
        )
    if payload.legacy_authoring:
        logger.info(
            "Legacy authoring: the stream suits older disc-authoring tools and "
            "carries no warp mode."
        )
        if info.thd_atmos and payload.thd_warp_mode is not None:
            logger.warning(
                "With --legacy-authoring the stream reports no warp mode, "
                "whatever --thd-warp-mode sets."
            )

    delay = get_delay(payload).compensated(compensation(spec))
    fps = get_fps(info.fps)
    # named by its largest channel-based presentation
    output, preview = _output(payload, info, ctx, spec, "TrueHD", "7.1", delay)

    truehdd, dee_input = _atmos_input(payload, info, ctx, str(CodecFormat.THD_ATMOS))
    if dee_input is None:
        raise InvalidAtmosInputError("Cannot process input, not a valid Atmos format")

    files = _dee_files(ctx, dee_input, output)
    dee_argv = thd_atmos_command(
        _tools(payload, ctx),
        payload,
        files,
        fps=fps,
        delay=delay,
        fits=thd_atmos_fits(payload, info),
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


# --- loudness measurement

# the layouts dee_measure_loudness reads; FFmpeg pads 3 to 5 channels to 5.1
MEASURE_INPUT_CHANNELS = (1, 2, 6)
MEASURE = "measure"


def measure_output(payload: MeasurePayload) -> Path | None:
    """Where the manifest is saved: --output, a file in --output-dir, or nowhere."""
    if payload.file_output:
        return payload.file_output
    if payload.output_dir is None:
        return None
    source = Path(payload.file_input)
    track = payload.track_index
    label = (
        ""
        if track == TrackIndex(TrackType.AUDIO, 0)
        else f".{track.track_type.value}{track.index}"
    )
    return payload.output_dir / f"{source.stem}{label}.loudness.json"


def plan_measure(
    payload: MeasurePayload, info: AudioTrackInfo, ctx: PlanContext
) -> JobPlan:
    """
    The plan for one loudness measurement.

    Its output is where the manifest ends up: the saved file, or DEE's own in
    the temp directory when it isn't kept.
    """
    manifest = ctx.temp_dir / "loudness.json"
    tools = _tools(payload, ctx)
    steps: tuple[Step, ...]
    if info.atmos:
        logger.info(
            "Measuring the Atmos program: DEE reports its binaural and 5.1 renders."
        )
        truehdd, dee_input = _atmos_input(payload, info, ctx, MEASURE)
        if dee_input is None:
            raise InvalidAtmosInputError(
                "Cannot process input, not a valid Atmos format"
            )
        files = DeeFiles(input=dee_input, output=manifest, temp_dir=ctx.temp_dir)
        dee = DeeStep(
            tuple(measure_command(tools, payload, files, input_format="atmos_mezz")),
            manifest,
        )
        steps = (truehdd, dee) if truehdd else (dee,)
    else:
        channels = info.channels
        if channels > max(MEASURE_INPUT_CHANNELS):
            raise UnsupportedDeeFeatureError(
                f"DEE measures 1.0, 2.0 and 5.1 (and Atmos), not {channels} "
                "channels. A downmix to 5.1 would change the loudness, so DeeZy "
                "doesn't measure one."
            )
        dee_channels = channels if channels in MEASURE_INPUT_CHANNELS else 6
        transport = choose_transport(
            payload, ctx, ctx.temp_dir / "measure.wav", dee_channels, info.duration
        )
        resample = not info.sample_rate or info.sample_rate != DEE_SAMPLE_RATE
        filters = _filter_args(None, resample)
        if dee_channels != channels:
            logger.info(
                f"DEE measures 1.0, 2.0 and 5.1, so the {channels}-channel source "
                "is measured as 5.1 with silent channels added, which leave its "
                "loudness as it is."
            )
            filters += ["-ac", str(dee_channels)]
        files = replace(_dee_files(ctx, transport, manifest), output=manifest)
        dee = DeeStep(
            tuple(measure_command(tools, payload, files, input_format="wav")), manifest
        )
        steps = _pcm_steps(payload, filters, transport, MEASURE, info, dee)
    return JobPlan(
        format=MEASURE,
        source=Path(payload.file_input),
        output=measure_output(payload) or manifest,
        temp_dir=ctx.temp_dir,
        steps=steps,
        free_space_needed=info.recommended_free_space,
    )
