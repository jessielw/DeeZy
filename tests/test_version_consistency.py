from pathlib import Path
import re

import pytest

from deezy.cli import __version__

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


@pytest.mark.skipif(
    not PYPROJECT.is_file(), reason="pyproject.toml is not shipped with the package"
)
def test_cli_version_matches_pyproject():
    """`deezy --version` must not drift from the packaged version."""
    match = re.search(
        r'^version = "([^"]+)"', PYPROJECT.read_text(encoding="utf-8"), re.MULTILINE
    )
    assert match, "version not found in pyproject.toml"
    assert __version__ == match.group(1)
