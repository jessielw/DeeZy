"""Reading a DAMF master: its header, its CAF audio, and the probe built on them."""

import struct

import pytest

from deezy.exceptions import InvalidAtmosInputError
from deezy.track_info.damf import damf_header_of, is_damf, read_damf
from deezy.track_info.mediainfo import MediainfoParser
from deezy.track_info.track_index import TrackIndex
from tests.integration.harness import SR, SYNTHETIC_OBJECTS, synthetic_damf

ELEMENTS = 1 + len(SYNTHETIC_OBJECTS)


@pytest.fixture
def damf(tmp_path):
    return synthetic_damf(tmp_path / "master", seconds=0.5)


def test_the_master_is_read_from_its_header_and_caf(damf):
    master = read_damf(damf)
    assert master.audio == damf.with_name("m.atmos.audio")
    assert master.metadata == damf.with_name("m.atmos.metadata")
    assert (master.channels, master.sample_rate, master.bit_depth) == (ELEMENTS, SR, 24)
    assert master.frames == SR // 2
    assert master.duration_ms == 500
    assert master.size == master.audio.stat().st_size + master.metadata.stat().st_size


def test_a_caf_of_unknown_length_runs_to_the_end_of_the_file(damf):
    audio = damf.with_name("m.atmos.audio")
    raw = bytearray(audio.read_bytes())
    at = raw.index(b"data") + 4
    raw[at : at + 8] = struct.pack(">q", -1)
    audio.write_bytes(raw)
    assert read_damf(damf).frames == SR // 2


def test_quoted_names_with_spaces_are_read(damf):
    folder = damf.parent
    for part in ("audio", "metadata"):
        (folder / f"m.atmos.{part}").rename(folder / f"A Film.atmos.{part}")
    text = damf.read_text()
    text = text.replace(
        "metadata: m.atmos.metadata", "metadata: 'A Film.atmos.metadata'"
    )
    text = text.replace("audio: m.atmos.audio", 'audio: "A Film.atmos.audio"')
    header = folder / "A Film.atmos"
    header.write_text(text)
    assert read_damf(header).audio.name == "A Film.atmos.audio"


def test_a_missing_part_is_named(damf):
    damf.with_name("m.atmos.metadata").unlink()
    with pytest.raises(
        InvalidAtmosInputError, match=r"m\.atmos\.metadata, which is missing"
    ):
        read_damf(damf)


def test_a_header_that_names_no_audio_is_refused(damf):
    damf.write_text("version: 0.5.1\npresentations:\n  - metadata: m.atmos.metadata\n")
    with pytest.raises(InvalidAtmosInputError, match="names no audio"):
        read_damf(damf)


def test_audio_that_is_not_linear_pcm_is_refused(damf):
    audio = damf.with_name("m.atmos.audio")
    audio.write_bytes(audio.read_bytes().replace(b"lpcm", b"alac", 1))
    with pytest.raises(InvalidAtmosInputError, match="not linear PCM"):
        read_damf(damf)


def test_audio_that_is_not_caf_is_refused(damf):
    damf.with_name("m.atmos.audio").write_bytes(b"RIFF" + bytes(64))
    with pytest.raises(InvalidAtmosInputError, match="not a CAF file"):
        read_damf(damf)


@pytest.mark.parametrize(
    ("name", "header"),
    [
        ("m.atmos.audio", "m.atmos"),
        ("m.ATMOS.metadata", "m.ATMOS"),
        ("m.audio", None),
        ("m.atmos", None),
        ("m.wav", None),
    ],
)
def test_a_part_points_to_its_header(tmp_path, name, header):
    found = damf_header_of(tmp_path / name)
    assert (found.name if found else None) == header


def test_only_the_header_is_a_damf(tmp_path):
    assert is_damf(tmp_path / "m.atmos")
    assert is_damf(tmp_path / "m.ATMOS")
    assert not is_damf(tmp_path / "m.atmos.audio")


def test_the_probe_takes_the_masters_own_numbers(damf):
    info = MediainfoParser(damf, TrackIndex.audio(0)).get_audio_track_info()
    assert info.damf_atmos and info.atmos_master and info.atmos
    assert not info.thd_atmos and not info.adm_atmos_wav
    assert (info.channels, info.sample_rate, info.bit_depth) == (ELEMENTS, SR, 24)
    assert info.duration == 500
    assert info.fps is None
    assert info.delay_relative_to_video == 0
    assert info.recommended_free_space == read_damf(damf).size


def test_the_probe_refuses_a_part_of_a_master(damf):
    with pytest.raises(InvalidAtmosInputError, match=r"give its header, m\.atmos"):
        MediainfoParser(damf.with_name("m.atmos.audio"), TrackIndex.audio(0))
