import pytest

from deezy.payloads.shared import ChannelBitrates

bitrates = ChannelBitrates(default=384, choices=(192, 256, 320, 384, 448, 512, 640))


@pytest.mark.parametrize(
    "target,expected",
    [
        (191, 192),  # below min, should get min
        (192, 192),  # exact match
        (200, 256),  # between 192 and 256, should get 256
        (384, 384),  # exact match
        (385, 448),  # between 384 and 448, should get 448
        (700, 640),  # above max, should get max (closest lower)
        (512, 512),  # exact match
        (513, 640),  # between 512 and 640, should get 640
    ],
)
def test_get_closest_bitrate(target, expected):
    result = bitrates.get_closest_bitrate(target)
    print(f"Target: {target}, Expected: {expected}, Got: {result}")
    assert result == expected, f"Target {target}: expected {expected}, got {result}"
