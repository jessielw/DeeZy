import argparse

import pytest

from deezy.cli import (
    create_common_argument_groups,
    create_encode_parsers,
    create_main_parser,
)
from deezy.cli.payload_factory import PayloadBuilder
from deezy.enums.shared import DeeDRC


def parse(*argv: str) -> argparse.Namespace:
    parser = create_main_parser()
    subparsers = parser.add_subparsers(dest="sub_command")
    create_encode_parsers(subparsers, create_common_argument_groups())
    return parser.parse_args(list(argv))


def mix_fields(*argv: str) -> dict:
    return PayloadBuilder._build_stereo_mix_fields(parse("encode", *argv, "a.wav"))


@pytest.mark.parametrize("fmt", ["dd", "ddp", "ddp-bluray"])
def test_the_surround_3db_attenuation_is_off_unless_asked_for(fmt):
    assert mix_fields(fmt)["surround_3db_attenuation"] is False
    assert mix_fields(fmt, "--surround-3db")["surround_3db_attenuation"] is True
    # 1.x's flag still parses, and asks for what is now the default
    assert mix_fields(fmt, "--no-surround-3db")["surround_3db_attenuation"] is False


@pytest.mark.parametrize("fmt", ["dd", "ddp", "ddp-bluray"])
def test_each_surround_flag_sets_its_own_option(fmt):
    fields = mix_fields(fmt, "--no-surround-90-deg-phase-shift")
    assert fields["surround_90_degree_phase_shift"] is False
    assert fields["surround_3db_attenuation"] is False
    fields = mix_fields(fmt, "--surround-3db")
    assert fields["surround_90_degree_phase_shift"] is True
    assert fields["surround_3db_attenuation"] is True


@pytest.mark.parametrize(
    "argv",
    [
        ["dd"],
        ["ddp"],
        ["ddp-bluray"],
        ["ddp-atmos"],
        ["ac4-ims"],
        ["preset", "--name", "x"],
    ],
)
def test_metering_mode_is_gone(argv, capsys):
    """DEE 6.7 measures with ITU-R BS.1770-4 only, so 2.0 has no --metering-mode."""
    with pytest.raises(SystemExit):
        parse("encode", *argv, "--metering-mode", "1770_4", "a.wav")
    assert "unrecognized arguments: --metering-mode" in capsys.readouterr().err


@pytest.mark.parametrize("fmt", ["dd", "ddp", "ddp-bluray", "ddp-atmos"])
def test_drc_none_is_offered(fmt):
    args = parse(
        "encode", fmt, "--drc-line-mode", "none", "--drc-rf-mode", "none", "a.wav"
    )
    assert args.drc_line_mode is DeeDRC.NONE
    assert args.drc_rf_mode is DeeDRC.NONE
