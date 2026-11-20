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


@pytest.mark.parametrize("fmt", ["dd", "ddp", "ddp-bluray"])
@pytest.mark.parametrize(
    ("flag", "off"),
    [
        ("--no-surround-3db", "surround_3db_attenuation"),
        ("--no-surround-90-deg-phase-shift", "surround_90_degree_phase_shift"),
    ],
)
def test_each_surround_flag_turns_off_its_own_option(fmt, flag, off):
    fields = PayloadBuilder._build_stereo_mix_fields(
        parse("encode", fmt, flag, "a.wav")
    )
    on = {"surround_3db_attenuation", "surround_90_degree_phase_shift"} - {off}
    assert fields[off] is False
    assert fields[on.pop()] is True


@pytest.mark.parametrize("fmt", ["dd", "ddp", "ddp-bluray", "ddp-atmos"])
def test_drc_none_is_offered(fmt):
    args = parse(
        "encode", fmt, "--drc-line-mode", "none", "--drc-rf-mode", "none", "a.wav"
    )
    assert args.drc_line_mode is DeeDRC.NONE
    assert args.drc_rf_mode is DeeDRC.NONE
