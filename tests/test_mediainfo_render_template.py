from pathlib import Path
from types import SimpleNamespace
from typing import cast

from pymediainfo import Track

from deezy.track_info.mediainfo import MediainfoParser
from deezy.track_info.track_index import TrackIndex


def make_parser(tmp_path: Path, filename: str, mi_audio_attrs: dict, guess: dict):
    """Construct a MediainfoParser-like object without invoking MediaInfo.parse()."""
    p = object.__new__(MediainfoParser)
    file_path = tmp_path / filename
    # create an empty file so Path operations are valid
    file_path.write_text("")
    p.file_input = file_path
    p.track_index = TrackIndex.audio(0)
    # minimal fake media info audio track
    fake_track = cast(Track, SimpleNamespace(**mi_audio_attrs))
    p.mi_audio_obj = fake_track
    # guess dict (mimics guessit result)
    p.guess = guess
    return p


def test_token_substitution_and_sanitization(tmp_path: Path):
    mi_attrs = {
        "other_language": ["eng"],
        "channel_s": 6,
        "other_channel_s": ["6"],
        "channel_s__original": "6",
        "delay_relative_to_video": "123",
    }
    guess = {"title": "Bad:Title/Name", "year": 2020}
    p = make_parser(tmp_path, "My.Source.TrueHD.Atmos.mkv", mi_attrs, guess)

    tpl = "{title}-{year}-{stem}-{source}-{lang}-{channels}-{worker}-{delay}"
    out = p.render_output_template(
        tpl,
        suffix=".ec3",
        output_channels="2.0",
        delay_was_stripped=False,
        delay_relative_to_video=123,
        worker_id="w1",
    )
    # sanitize should replace forbidden chars like :, / with _
    assert "Bad_Title_Name" in out.name
    assert "2020" in out.name
    assert "w1" in out.name
    # delay from mediainfo present (templates control surrounding brackets)
    assert "DELAY 123ms" in out.name


def test_delay_from_filename_when_mediainfo_missing(tmp_path: Path):
    # create file that contains delay token in filename
    mi_attrs = {
        "other_language": None,
        "channel_s": 2,
        "other_channel_s": ["2"],
        "channel_s__original": "2",
        # no mediainfo delay available
        "delay_relative_to_video": None,
    }
    guess = {"title": "Title"}
    # filename contains 'delay 10ms' which should be parsed
    p = make_parser(tmp_path, "Movie delay 10ms TrueHD.mkv", mi_attrs, guess)

    out = p.render_output_template(
        "{title} {delay}",
        suffix=".ec3",
        output_channels="2.0",
        delay_was_stripped=False,
        delay_relative_to_video=0,
        worker_id=None,
    )
    assert "DELAY 10ms" in out.name


def test_ignore_delay_and_stripped_injected(tmp_path: Path):
    mi_attrs = {
        "other_language": None,
        "channel_s": 2,
        "other_channel_s": ["2"],
        "channel_s__original": "2",
        "delay_relative_to_video": None,
    }
    guess = {"title": "Title"}
    p = make_parser(tmp_path, "SomeFile.mkv", mi_attrs, guess)

    out = p.render_output_template(
        "{title} {delay}",
        suffix=".ec3",
        output_channels="2.0",
        delay_was_stripped=True,
        delay_relative_to_video=0,
        worker_id=None,
    )
    assert "DELAY 0ms" in out.name


def test_missing_tokens_and_empty_fields(tmp_path: Path):
    mi_attrs = {
        "other_language": None,
        "channel_s": 2,
        "other_channel_s": ["2"],
        "channel_s__original": "2",
        "delay_relative_to_video": None,
    }
    # guess missing year -> year token should be empty
    guess = {"title": "OnlyTitle"}
    p = make_parser(tmp_path, "OnlyTitle.mkv", mi_attrs, guess)

    out = p.render_output_template(
        "{title}-{year}-{unknown}",
        suffix=".ec3",
        output_channels="2.0",
        delay_was_stripped=False,
        delay_relative_to_video=0,
        worker_id=None,
    )
    # year missing -> hyphen followed by empty; unknown token remains as literal
    assert "OnlyTitle-" in out.name


def test_whitespace_and_forbidden_chars_collapsed(tmp_path: Path):
    mi_attrs = {
        "other_language": None,
        "channel_s": 2,
        "other_channel_s": ["2"],
        "channel_s__original": "2",
        "delay_relative_to_video": None,
    }
    guess = {"title": "A    B:C/ D"}
    p = make_parser(tmp_path, "x.mkv", mi_attrs, guess)

    tpl = '{title}    {title}<>:"/\\|?*'
    out = p.render_output_template(
        tpl,
        suffix=".ec3",
        output_channels="2.0",
        delay_was_stripped=False,
        delay_relative_to_video=0,
        worker_id=None,
    )
    # forbidden chars replaced with underscore and multiple spaces collapsed
    assert "A B_C_ D" in out.name or "A_B_C__D" in out.name


def test_channel_mapping_and_lang_detection(tmp_path: Path):
    mi_attrs = {
        "other_language": ["eng"],
        "channel_s": 8,
        "other_channel_s": ["8"],
        "channel_s__original": "8",
        "delay_relative_to_video": None,
    }
    guess = {"title": "Movie"}
    p = make_parser(tmp_path, "movie.mkv", mi_attrs, guess)

    out = p.render_output_template(
        "{channels}-{lang}",
        suffix=".ec3",
        output_channels="7.1",
        delay_was_stripped=False,
        delay_relative_to_video=0,
        worker_id=None,
    )
    # 8 channels maps to 7.1 and lang from other_language should be 'eng'
    assert "7.1" in out.name
    assert "eng" in out.name


def test_multiple_delay_in_filename_uses_first_match(tmp_path: Path):
    mi_attrs = {
        "other_language": None,
        "channel_s": 2,
        "other_channel_s": ["2"],
        "channel_s__original": "2",
        "delay_relative_to_video": None,
    }
    guess = {"title": "Title"}
    # filename contains two delay tokens; parse_delay_from_file should capture first
    p = make_parser(tmp_path, "Video delay 10ms delay 20ms.mkv", mi_attrs, guess)

    out = p.render_output_template(
        "{delay}",
        suffix=".ec3",
        output_channels="2.0",
        delay_was_stripped=False,
        delay_relative_to_video=0,
        worker_id=None,
    )
    assert "DELAY 10ms" in out.name


def test_empty_template_results_in_suffix_only(tmp_path: Path):
    mi_attrs = {
        "other_language": None,
        "channel_s": 2,
        "other_channel_s": ["2"],
        "channel_s__original": "2",
        "delay_relative_to_video": None,
    }
    guess = {"title": "T"}
    p = make_parser(tmp_path, "T.mkv", mi_attrs, guess)

    out = p.render_output_template(
        "",
        suffix=".ec3",
        output_channels="2.0",
        delay_was_stripped=False,
        delay_relative_to_video=0,
        worker_id=None,
    )
    # name should end with the suffix
    assert out.name.endswith(".ec3")


def test_generate_output_filename_tv_show_and_filename_delay(tmp_path: Path):
    mi_attrs = {
        "other_language": ["eng"],
        "channel_s": 6,
        "other_channel_s": ["6"],
        "channel_s__original": "6",
        "delay_relative_to_video": None,
    }
    # no title in guess -> fallback to stem; include season/episode/year
    guess = {"season": 1, "episode": 2, "year": 2019}
    # filename contains delay token
    p = make_parser(tmp_path, "Show delay 5ms.mkv", mi_attrs, guess)

    out = p.generate_output_filename(
        delay_was_stripped=False,
        delay_relative_to_video=5,
        suffix=".ec3",
        output_channels="2.0",
        worker_id="wrk1",
    )
    # season/episode and year should appear and delay from filename should be used
    assert "S01E02" in out.name
    assert "2019" in out.name
    # delay is appended without surrounding brackets in current generation
    assert "DELAY 5ms" in out.name
    assert "wrk1" in out.name


def test_generate_output_filename_ignore_delay_injects_zero(tmp_path: Path):
    mi_attrs = {
        "other_language": None,
        "channel_s": 2,
        "other_channel_s": ["2"],
        "channel_s__original": "2",
        "delay_relative_to_video": None,
    }
    guess = {"title": "MyMovie"}
    p = make_parser(tmp_path, "MyMovie.mkv", mi_attrs, guess)

    out = p.generate_output_filename(
        delay_was_stripped=True,
        delay_relative_to_video=0,
        suffix=".ec3",
        output_channels="2.0",
        worker_id=None,
    )
    assert "DELAY 0ms" in out.name
