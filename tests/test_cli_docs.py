"""The generated docs match the code, and every `deezy` example in them parses."""

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

_FENCE = re.compile(r"^```[^\n]*\n(.*?)^```", re.S | re.M)


def _examples(*pages: Path) -> list[tuple[str, str]]:
    """Each `deezy ...` line in the pages' fenced blocks, by page."""
    found = []
    for page in pages:
        text = page.read_text(encoding="utf-8").replace("\r\n", "\n")
        for block in _FENCE.findall(text):
            for line in block.splitlines():
                if line.strip().startswith("deezy "):
                    found.append((page.relative_to(ROOT).as_posix(), line.strip()))
    return found


def _reference_pages() -> list[Path]:
    return sorted(cli_docs.DOCS.glob("*.md")) + sorted(
        cli_docs.FORMAT_DOCS.glob("*.md")
    )


def test_the_generated_docs_are_up_to_date():
    stale = cli_docs.stale_pages()
    assert not stale, f"run 'python scripts/cli_docs.py' to update {stale}"


def test_every_reference_page_is_in_the_nav():
    nav = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    pages = [page.relative_to(ROOT / "docs").as_posix() for page in _reference_pages()]
    assert {f"cli/{page}" for page in cli_docs.PAGES} <= set(pages)
    assert not [page for page in pages if page not in nav]


def test_each_reference_page_has_examples():
    with_examples = {page for page, _ in _examples(*_reference_pages())}
    pages = {page.relative_to(ROOT).as_posix() for page in _reference_pages()}
    assert with_examples == pages


@pytest.mark.parametrize(
    ("page", "command"),
    _examples(*sorted((ROOT / "docs").rglob("*.md")), ROOT / "README.md"),
)
def test_an_example_parses(page, command, capsys):
    parser = cli_docs.build_parser()
    try:
        parser.parse_args(shlex.split(command)[1:])
    except SystemExit as exit:
        if exit.code:
            pytest.fail(f"{page}: {command!r} doesn't parse: {capsys.readouterr().err}")
