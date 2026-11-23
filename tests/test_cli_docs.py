"""The CLI reference in docs/cli matches the parsers, and its examples parse."""

import importlib.util
from pathlib import Path
import re
import shlex

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "cli_docs", ROOT / "scripts" / "cli_docs.py"
)
assert _spec and _spec.loader
cli_docs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cli_docs)

_BASH = re.compile(r"^```bash\n(.*?)^```", re.S | re.M)


def _examples() -> list[tuple[str, str]]:
    found = []
    for page in sorted(cli_docs.DOCS.glob("*.md")):
        text = page.read_text(encoding="utf-8").replace("\r\n", "\n")
        for block in _BASH.findall(text):
            for line in block.splitlines():
                if line.startswith("deezy "):
                    found.append((page.name, line))
    return found


def test_the_cli_reference_is_up_to_date():
    stale = cli_docs.stale_pages()
    assert not stale, f"run 'python scripts/cli_docs.py' to update {stale}"


def test_every_page_is_in_the_nav():
    nav = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    missing = [page for page in cli_docs.PAGES if f"cli/{page}" not in nav]
    assert not missing


def test_each_page_has_examples():
    pages = {page for page, _ in _examples()}
    assert pages == set(cli_docs.PAGES)


@pytest.mark.parametrize(("page", "command"), _examples())
def test_an_example_parses(page, command, capsys):
    parser = cli_docs.build_parser()
    try:
        parser.parse_args(shlex.split(command)[1:])
    except SystemExit:
        pytest.fail(f"{page}: {command!r} doesn't parse: {capsys.readouterr().err}")
