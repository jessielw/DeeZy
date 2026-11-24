from pathlib import Path
import xml.etree.ElementTree as ET

from pymediainfo import MediaInfo, Track
import pytest

from deezy.pipeline.plan import ffmpeg_argv
from deezy.pipeline.transport import WavFile
from deezy.track_info.mediainfo import MediainfoParser
from deezy.track_info.track_index import TrackIndex


def track_with(*fields: tuple[str, str]) -> Track:
    element = ET.Element("track", type="Audio")
    for name, value in fields:
        ET.SubElement(element, name).text = value
    return Track(element)


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        (["48000"], 48000),
        ([" / 48000 / 48000", " / 48.0 kHz / 48.0 kHz"], 48000),
        (["Unknown", " / 48.0 kHz / 48.0 kHz"], 48000),
        (["96000 / 48000"], 96000),
        (["Unknown", "44.1 kHz"], 44100),
        (["Unknown"], None),
        ([], None),
    ],
)
def test_sample_rate_from_raw_or_display_values(values, expected):
    track = track_with(*[("Sampling_rate", value) for value in values])
    assert MediainfoParser._sample_rate(track) == expected


@pytest.mark.parametrize(
    ("counts", "features", "reported", "bed"),
    [
        (["8 / 8 / 6"], "XLL X", 8, True),
        (["Object Based / 8 / 6"], "XLL X", 8, True),
        (["12", "12 channels / 8 channels / 6 channels"], "XLL X", 12, True),
        (["8 / 6"], "XLL", 8, False),
        (["6 / 6"], "XLL X", 6, False),
    ],
)
def test_dtsx_bed_and_source_report(counts, features, reported, bed):
    track = track_with(
        ("Format", "DTS"),
        ("Format_AdditionalFeatures", features),
        *[("Channel_s_", n) for n in counts],
    )
    parser = object.__new__(MediainfoParser)
    parser.file_input = Path("in.mkv")
    parser.mi_audio_obj = track
    parser.mi_obj = MediaInfo("<File/>")
    parser.mi_obj.tracks.append(track)
    parser.damf = None
    info = parser.get_audio_track_info()
    assert parser.get_channels(track) == reported
    assert info.channels == (8 if bed else reported)
    assert info.dtsx_bed_71 is bed
    for index, stream in [(TrackIndex.audio(1), "a:1"), (TrackIndex.stream(2), "2")]:
        argv = ffmpeg_argv(
            Path("ffmpeg"),
            Path("in.mkv"),
            index,
            [],
            WavFile(Path("out.wav")),
            dtsx_bed_71=info.dtsx_bed_71,
        )
        input_args = argv[: argv.index("-i")]
        assert (f"-downmix:{stream}" in input_args) is bed
        assert argv[argv.index("-map") + 1] == f"0:{stream}"
