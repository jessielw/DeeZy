import os
import shutil
import tempfile
from pathlib import Path

import pytest

from deezy.utils.file_parser import parse_input_s


def setup_test_tree(base: Path):
    # create tree:
    # base/
    #   a.txt
    #   sub/
    #     b.txt
    #     deep/
    #       c.txt
    base.mkdir(parents=True, exist_ok=True)
    (base / "a.txt").write_text("a")
    sub = base / "sub"
    sub.mkdir(exist_ok=True)
    (sub / "b.txt").write_text("b")
    deep = sub / "deep"
    deep.mkdir(exist_ok=True)
    (deep / "c.txt").write_text("c")


@pytest.fixture
def tmp_tree(tmp_path):
    tree = tmp_path / "tree"
    setup_test_tree(tree)
    return tree


def test_single_file(tmp_tree):
    a = tmp_tree / "a.txt"
    res = parse_input_s([str(a)])
    assert len(res) == 1
    assert res[0].name == "a.txt"


def test_star_glob(tmp_tree):
    pattern = str(tmp_tree / "*")
    res = parse_input_s([pattern])
    names = sorted(p.name for p in res)
    assert names == ["a.txt", "sub"] or names == ["a.txt"]
    # ensure files only
    assert all(p.is_file() for p in res)


def test_double_star_glob(tmp_tree):
    pattern = str(tmp_tree / "**" / "*.txt")
    res = parse_input_s([pattern])
    names = sorted(p.name for p in res)
    assert names == ["a.txt", "b.txt", "c.txt"]


def test_mixed_input(tmp_tree):
    # mix explicit file, non-recursive, and recursive patterns in one call
    a = tmp_tree / "a.txt"
    star = tmp_tree / "*"
    deep = tmp_tree / "**" / "*.txt"
    res = parse_input_s([str(a), str(star), str(deep)])
    # should contain a.txt, then any non-recursive matches, then recursive matches
    # and no duplicates
    names = [p.name for p in res]
    assert "a.txt" in names
    assert "b.txt" in names
    assert "c.txt" in names
    # ensure unique
    assert len(names) == len(set(names))


def test_empty_whitespace_arg(tmp_tree):
    # a whitespace-only argument should be rejected
    with pytest.raises(FileNotFoundError):
        parse_input_s(["   "])


def test_duplicate_matches_dedup(tmp_tree):
    # a pattern that matches a file and an explicit path to the same file
    # should not produce duplicates
    pattern = str(tmp_tree / "**" / "*.txt")
    explicit = str(tmp_tree / "sub" / "b.txt")
    res = parse_input_s([pattern, explicit])
    names = sorted(p.name for p in res)
    assert names == ["a.txt", "b.txt", "c.txt"]


def test_order_preserved(tmp_tree):
    # explicit file provided first should appear first in the results
    a = tmp_tree / "a.txt"
    pattern = str(tmp_tree / "**" / "*.txt")
    res = parse_input_s([str(a), pattern])
    assert res[0].name == "a.txt"


@pytest.mark.skipif(not os.name == "nt", reason="Windows-specific path separators")
def test_backslash_pattern_windows(tmp_tree):
    # on Windows users may pass backslash-separated patterns; ensure these work
    pattern = str(tmp_tree / "**" / "*.txt").replace("/", "\\")
    res = parse_input_s([pattern])
    names = sorted(p.name for p in res)
    assert names == ["a.txt", "b.txt", "c.txt"]


def test_wildcarded_prefix_recursive(tmp_path):
    # Ensure patterns with wildcarded prefixes like 'foo*/**/*.txt' are expanded
    base = tmp_path / "wildcard_test"
    (base / "foo1" / "x").mkdir(parents=True)
    (base / "foo2" / "y").mkdir(parents=True)
    (base / "foo1" / "x" / "a.txt").write_text("a")
    (base / "foo2" / "y" / "b.txt").write_text("b")

    pattern = str(base / "foo*" / "**" / "*.txt")
    res = parse_input_s([pattern])
    names = sorted(p.name for p in res)
    assert names == ["a.txt", "b.txt"]


def test_explicit_absolute_recursive(tmp_path):
    # ensure an absolute recursive pattern behaves correctly (preserves root)
    base = tmp_path / "abs_test"
    (base / "sub" / "deep").mkdir(parents=True)
    (base / "root.txt").write_text("r")
    (base / "sub" / "d.txt").write_text("d")

    pattern = str(base / "**" / "*.txt")
    res = parse_input_s([pattern])
    names = sorted(p.name for p in res)
    assert names == ["d.txt", "root.txt"] or names == ["root.txt", "d.txt"]


def test_empty_prefix_uses_cwd(tmp_path, monkeypatch):
    # ensure pattern with leading '**' uses the process CWD as base
    base = tmp_path / "cwd_test"
    (base / "sub").mkdir(parents=True)
    (base / "a.txt").write_text("a")
    (base / "sub" / "b.txt").write_text("b")

    # change current working directory to base and run pattern with empty prefix
    monkeypatch.chdir(base)
    res = parse_input_s(["**/*.txt"])  # empty prefix -> Path('.') behavior
    names = sorted(p.name for p in res)
    assert names == ["a.txt", "b.txt"]


def test_absolute_pattern_from_different_cwd(tmp_path, monkeypatch):
    # ensure an absolute recursive pattern works regardless of current working dir
    base = tmp_path / "abs_from_other"
    (base / "sub").mkdir(parents=True)
    (base / "root.txt").write_text("r")
    (base / "sub" / "d.txt").write_text("d")

    # change cwd to somewhere else
    other = tmp_path / "othercwd"
    other.mkdir()
    monkeypatch.chdir(other)

    pattern = str(base / "**" / "*.txt")
    res = parse_input_s([pattern])
    names = sorted(p.name for p in res)
    assert set(names) == {"root.txt", "d.txt"}


def test_invalid_path(tmp_tree):
    with pytest.raises(FileNotFoundError):
        parse_input_s([str(tmp_tree / "does_not_exist.txt")])
