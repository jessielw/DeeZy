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


def _examples(*folders: Path) -> list[tuple[str, str]]:
    found = []
    for folder in folders or (cli_docs.DOCS, cli_docs.FORMAT_DOCS):
        for page in sorted(folder.glob("*.md")):
            text = page.read_text(encoding="utf-8").replace("\r\n", "\n")
            for block in _BASH.findall(text):
                for line in block.splitlines():
                    if line.startswith("deezy "):
                        found.append((f"{folder.name}/{page.name}", line))
    return found


def test_the_cli_reference_is_up_to_date():
    stale = cli_docs.stale_pages()
    assert not stale, f"run 'python scripts/cli_docs.py' to update {stale}"


def _format_pages() -> set[str]:
    return {f"formats/{page.name}" for page in cli_docs.FORMAT_DOCS.glob("*.md")}


def test_every_page_is_in_the_nav():
    nav = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    pages = {f"cli/{page}" for page in cli_docs.PAGES} | _format_pages()
    assert not [page for page in sorted(pages) if page not in nav]


def test_each_page_has_examples():
    pages = {page for page, _ in _examples()}
    assert pages == {f"cli/{page}" for page in cli_docs.PAGES} | _format_pages()


@pytest.mark.parametrize(("page", "command"), _examples())
def test_an_example_parses(page, command, capsys):
    parser = cli_docs.build_parser()
    try:
        parser.parse_args(shlex.split(command)[1:])
    except SystemExit:
        pytest.fail(f"{page}: {command!r} doesn't parse: {capsys.readouterr().err}")
