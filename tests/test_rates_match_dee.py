"""DeeZy's data-rate lists must only offer rates DEE 6.7 accepts.

The accepted rates come from the fixture scripts/probe_dee.py writes by running
the encoders, so a rate DEE refuses fails here instead of mid-encode.
"""

import json
from pathlib import Path

import pytest

import deezy
from deezy.enums.aac import AacProfile
from deezy.enums.ac4 import Ac4Channels
from deezy.enums.atmos import AtmosMode
from deezy.enums.dd import DolbyDigitalChannels
from deezy.enums.ddp import DolbyDigitalPlusChannels
from deezy.enums.ddp_bluray import DolbyDigitalPlusBlurayChannels

FIXTURE = Path(deezy.__file__).parent / "dee" / "data" / "dee_6_7_0.json"
RATES = json.loads(FIXTURE.read_text(encoding="utf-8"))["rates"]

CASES = [
    (DolbyDigitalChannels.MONO, ("dee_ddp_encoder", "dd", "1.0")),
    (DolbyDigitalChannels.STEREO, ("dee_ddp_encoder", "dd", "2.0")),
    (DolbyDigitalChannels.SURROUND, ("dee_ddp_encoder", "dd", "5.1")),
    (DolbyDigitalPlusChannels.MONO, ("dee_ddp_encoder", "ddp", "1.0")),
    (DolbyDigitalPlusChannels.STEREO, ("dee_ddp_encoder", "ddp", "2.0")),
    (DolbyDigitalPlusChannels.SURROUND, ("dee_ddp_encoder", "ddp", "5.1")),
    (DolbyDigitalPlusBlurayChannels.SURROUNDEX, ("dee_ddp_encoder", "bluray", "7.1")),
    (AtmosMode.STREAMING, ("dee_ddpjoc_encoder", "ddpjoc")),
    (AtmosMode.BLURAY, ("dee_ddpjoc_encoder", "bluray")),
    (Ac4Channels.IMMERSIVE_STEREO, ("dee_ac4ims_encoder",)),
]


def accepted(path: tuple[str, ...]) -> set[int]:
    node = RATES
    for key in path:
        node = node[key]
    return set(node["rates"])


@pytest.mark.parametrize("profile", list(AacProfile), ids=str)
def test_aac_choices_are_in_dee_range(profile):
    low, high = RATES["dee_aac_encoder"][profile.value]
    rates = profile.get_bitrate_obj()
    assert min(rates.choices) == low
    assert max(rates.choices) == high
    assert rates.default in rates.choices


@pytest.mark.parametrize(("member", "path"), CASES, ids=lambda c: str(c))
def test_choices_are_accepted_by_dee(member, path):
    rates = member.get_bitrate_obj()
    assert set(rates.choices) <= accepted(path)
    assert rates.default in rates.choices
