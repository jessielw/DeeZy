from pathlib import Path

from deezy.track_info.utils import clean_title


def test_current_sample_outputs():
    samples = [
        ("01 [jpn] DELAY 0ms.ac3", "01"),
        ("01 - Main Title [eng] DELAY 12ms.eac3", "01 Main Title"),
        ("Track_03 (eng) 48kHz 5.1.flac", "Track 03"),
        ("07 - Surround Mix [eng] 7.1ch.dts", "07 Surround Mix"),
        ("02_dual mono (jpn) 48kHz.flac", "02 dual"),
        ("03 - Multichannel [eng] 5ch.eac3", "03 Multichannel"),
        ("04 - Stereo (eng) 2.0.mp3", "04"),
        ("05 - Main Title (mono) 48kHz.wav", "05 Main Title"),
    ]

    for inp, expected in samples:
        assert clean_title(Path(inp).stem) == expected
