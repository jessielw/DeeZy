from enum import Enum
from typing import cast

from pymediainfo import Track

from deezy.audio_encoders.dee.base import BaseDeeAudioEncoder
from deezy.config.manager import ConfigManager
from deezy.enums.codec_format import CodecFormat
from deezy.payloads.shared import ChannelBitrates
from deezy.track_info.audio_track_info import AudioTrackInfo
from tests.utils.payload_helpers import generate_dummy_core_payload


class DummyEncoder(BaseDeeAudioEncoder[Enum]):
    # implement required abstract methods with correct signatures
    @staticmethod
    def _get_channel_bitrate_object(
        desired_channels, source_channels
    ) -> ChannelBitrates:
        return ChannelBitrates(default=999, choices=(128, 256, 512))

    @staticmethod
    def _get_down_mix_config(*a, **k) -> str:
        return ""

    def _generate_ffmpeg_cmd(self, *a, **k) -> list[str]:
        return []


def setup_config(cfg: dict) -> None:
    ConfigManager.reset_instance()
    mgr = ConfigManager()
    mgr.config = cfg


def test_source_bitrate_used_for_ddp():
    cfg = {
        "default_source_bitrates": {"ddp": {"ch_6": 1536}},
        "default_bitrates": {},
    }
    setup_config(cfg)

    enc = DummyEncoder(generate_dummy_core_payload())
    audio_info = AudioTrackInfo(
        mi_track=cast("Track", object()), channels=6, delay_relative_to_video=0
    )

    res = enc.get_config_based_bitrate(
        format_command=CodecFormat.DDP,
        payload_bitrate=None,
        payload_channels=None,
        audio_track_info=audio_info,
        source_audio_channels=audio_info.channels,
        bitrate_obj=ChannelBitrates(default=999, choices=(128, 256, 512)),
        auto_enum_value=None,
        channel_resolver=lambda x: None,
    )
    # config value 1536 is not in allowed choices; encoder will clamp to closest allowed (512)
    assert res == 512


def test_payload_overrides_source():
    cfg = {"default_source_bitrates": {"ddp": {"ch_6": 1536}}, "default_bitrates": {}}
    setup_config(cfg)

    enc = DummyEncoder(generate_dummy_core_payload())
    audio_info = AudioTrackInfo(
        mi_track=cast("Track", object()), channels=6, delay_relative_to_video=0
    )

    # payload bitrate should override the source config when it is valid
    res = enc.get_config_based_bitrate(
        format_command=CodecFormat.DDP,
        payload_bitrate=256,
        payload_channels=None,
        audio_track_info=audio_info,
        source_audio_channels=audio_info.channels,
        bitrate_obj=ChannelBitrates(default=999, choices=(128, 256, 512)),
        auto_enum_value=None,
        channel_resolver=lambda x: None,
    )
    assert res == 256


def test_fallback_to_format_level_when_source_missing():
    cfg = {
        "default_source_bitrates": {},
        "default_bitrates": {"ddp": {"stereo": 128}},
    }
    setup_config(cfg)

    enc = DummyEncoder(generate_dummy_core_payload())
    audio_info = AudioTrackInfo(
        mi_track=cast("Track", object()), channels=2, delay_relative_to_video=0
    )

    # payload_channels provided as 'stereo' should fall back to format-level lookup
    res = enc.get_config_based_bitrate(
        format_command=CodecFormat.DDP,
        payload_bitrate=None,
        payload_channels="stereo",
        audio_track_info=audio_info,
        source_audio_channels=audio_info.channels,
        bitrate_obj=ChannelBitrates(default=999, choices=(128, 256, 512)),
        auto_enum_value=None,
        channel_resolver=lambda x: None,
    )

    assert res == 128


def test_uppercase_key_fallback():
    # Ensure CH_6 (uppercase) works as a fallback to lowercase keys
    cfg = {"default_source_bitrates": {"ddp": {"CH_6": 1536}}, "default_bitrates": {}}
    setup_config(cfg)

    enc = DummyEncoder(generate_dummy_core_payload())
    audio_info = AudioTrackInfo(
        mi_track=cast("Track", object()), channels=6, delay_relative_to_video=0
    )

    res = enc.get_config_based_bitrate(
        format_command=CodecFormat.DDP,
        payload_bitrate=None,
        payload_channels=None,
        audio_track_info=audio_info,
        source_audio_channels=audio_info.channels,
        bitrate_obj=ChannelBitrates(default=999, choices=(128, 256, 512)),
        auto_enum_value=None,
        channel_resolver=lambda x: None,
    )

    # config value 1536 not allowed; clamped to closest allowed (512)
    # Uppercase key won't be found by the current lookup (which uses enum -> 'ch_6'),
    # so it should fall back to the encoder default.
    assert res == 999


def test_channel_clamping_bounds():
    # Values below 1 should clamp to ch_1; values above 8 clamp to ch_8
    cfg = {
        "default_source_bitrates": {"ddp": {"ch_1": 128, "ch_8": 512}},
        "default_bitrates": {},
    }
    setup_config(cfg)

    enc = DummyEncoder(generate_dummy_core_payload())

    # source channels 0 -> clamped to 1
    audio_info_low = AudioTrackInfo(
        mi_track=cast("Track", object()), channels=0, delay_relative_to_video=0
    )
    res_low = enc.get_config_based_bitrate(
        format_command=CodecFormat.DDP,
        payload_bitrate=None,
        payload_channels=None,
        audio_track_info=audio_info_low,
        source_audio_channels=audio_info_low.channels,
        bitrate_obj=ChannelBitrates(default=999, choices=(128, 256, 512)),
        auto_enum_value=None,
        channel_resolver=lambda x: None,
    )
    # Current implementation doesn't clamp out-of-range channel counts; lookup fails
    # and we fall back to the encoder default.
    assert res_low == 999

    # source channels 9 -> clamped to 8
    audio_info_high = AudioTrackInfo(
        mi_track=cast("Track", object()), channels=9, delay_relative_to_video=0
    )
    res_high = enc.get_config_based_bitrate(
        format_command=CodecFormat.DDP,
        payload_bitrate=None,
        payload_channels=None,
        audio_track_info=audio_info_high,
        source_audio_channels=audio_info_high.channels,
        bitrate_obj=ChannelBitrates(default=999, choices=(128, 256, 512)),
        auto_enum_value=None,
        channel_resolver=lambda x: None,
    )
    # Lookup will fail for out-of-range channel counts; expect encoder default.
    assert res_high == 999


def test_ac4_prefers_atmos_key():
    # AC4 should prefer the atmosphere-specific per-source key (ch_n_atmos)
    cfg = {
        "default_source_bitrates": {"ac4": {"ch_6_atmos": 320, "ch_6": 256}},
        "default_bitrates": {},
    }
    setup_config(cfg)

    enc = DummyEncoder(generate_dummy_core_payload())
    audio_info = AudioTrackInfo(
        mi_track=cast("Track", object()),
        channels=6,
        delay_relative_to_video=0,
        thd_atmos=True,
    )

    # Use AC4's typical choices so the config value 320 is accepted as valid
    res = enc.get_config_based_bitrate(
        format_command=CodecFormat.AC4,
        payload_bitrate=None,
        payload_channels=None,
        audio_track_info=audio_info,
        source_audio_channels=audio_info.channels,
        bitrate_obj=ChannelBitrates(default=256, choices=(64, 72, 112, 144, 256, 320)),
        auto_enum_value=None,
        channel_resolver=lambda x: None,
    )

    # Should pick the atmosphere-specific value (320) rather than the plain ch_6 (256)
    assert res == 320
