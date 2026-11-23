"""`deezy tools`: the tools DeeZy finds, where they are and their versions."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import re
import subprocess

from deezy.dee.shim import (
    MIN_SHIM_TEXT,
    MIN_SHIM_VERSION,
    SHIM_NAME,
    find_shim,
    parse_version,
    shim_version,
    user_shim_path,
)
from deezy.dee.tools import (
    DEE_MARKER_TOOL,
    SUPPORTED_DEE_VERSION,
    FindDependencies,
    dee_version,
    find_license,
)
from deezy.exceptions import DependencyNotFoundError

_FFMPEG_VERSION = re.compile(r"ffmpeg version (\S+)")
_TRUEHDD_VERSION = re.compile(r"truehdd (\S+)")
NAME_WIDTH = 9


@dataclass(frozen=True, slots=True)
class ToolRow:
    """One tool: where DeeZy found it, what it reports and what that means."""

    name: str
    path: Path | None
    version: str | None
    # what is wrong with it, or what it is for when it isn't there
    note: str = ""
    # False when DeeZy can't encode with what it found
    ok: bool = True
    # more lines about the tool (DEE's license)
    extra: tuple[str, ...] = ()


def tool_version(cmd: list[str], pattern: re.Pattern[str]) -> str | None:
    """The version ``cmd`` prints, as ``pattern``'s first group."""
    try:
        proc = subprocess.run(  # noqa: S603
            cmd, capture_output=True, text=True, errors="replace", timeout=30
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    found = pattern.search((proc.stdout or "") + (proc.stderr or ""))
    return found.group(1) if found else None


def ffmpeg_version(path: Path) -> str | None:
    return tool_version([str(path), "-hide_banner", "-version"], _FFMPEG_VERSION)


def truehdd_version(path: Path) -> str | None:
    return tool_version([str(path), "--version"], _TRUEHDD_VERSION)


def _bad(bad: list[str], name: str) -> str | None:
    """What was wrong with the path given for ``name``, from ``locate``'s list."""
    prefix = f"{name} ("
    entry = next((entry for entry in bad if entry.startswith(prefix)), None)
    return entry[len(prefix) : -1] if entry else None


def _row(
    name: str,
    path: Path | None,
    version_of: Callable[[Path], str | None],
    missing: str,
    bad: list[str],
    required: bool,
) -> ToolRow:
    given = _bad(bad, name)
    if given:
        return ToolRow(name, None, None, f"not found at {given}", ok=False)
    if path is None:
        return ToolRow(name, None, None, missing, ok=not required)
    version = version_of(path)
    if version is None:
        return ToolRow(name, path, None, "reports no version", ok=not required)
    return ToolRow(name, path, version)


def _license_line(dee_dir: Path) -> str:
    if (dee_dir / "license.lic").is_file():
        return "license: license.lic beside the tools"
    found = find_license(dee_dir)
    if found:
        return f"license: {found}"
    return "license: none found; DEE looks for license.lic beside the tools"


def _dee_row(dee: Path | None, bad: list[str]) -> ToolRow:
    given = _bad(bad, "dee")
    if given:
        return ToolRow("DEE", None, None, f"not found at {given}", ok=False)
    if dee is None:
        return ToolRow(
            "DEE",
            None,
            None,
            f"not found (a folder with {DEE_MARKER_TOOL}; every encode needs it)",
            ok=False,
        )
    version = dee_version(dee)
    extra = (_license_line(dee),)
    if version is None:
        return ToolRow("DEE", dee, None, "reports no version", ok=False, extra=extra)
    if not version.startswith(f"{SUPPORTED_DEE_VERSION}."):
        note = f"DeeZy needs DEE {SUPPORTED_DEE_VERSION}"
        return ToolRow("DEE", dee, version, note, ok=False, extra=extra)
    return ToolRow("DEE", dee, version, extra=extra)


def _shim_row(
    base_wd: Path, dee: Path | None, user_value: str | None, disabled: bool
) -> ToolRow:
    if disabled:
        return ToolRow(SHIM_NAME, None, None, "turned off (--no-shim or no_shim)")
    if user_value and user_value.strip():
        try:
            path = user_shim_path(user_value)
        except DependencyNotFoundError:
            note = f"not found at '{user_value}'"
            return ToolRow(SHIM_NAME, None, None, note, ok=False)
    else:
        path = find_shim(base_wd, dee)
    if path is None:
        return ToolRow(
            SHIM_NAME,
            None,
            None,
            "not found (DD+ 7.1 and 7.0, DD+ Atmos Blu-ray and standard, "
            "TrueHD that decodes to its source, and measuring 7.1 need it)",
        )
    version = shim_version(path)
    parsed = parse_version(version or "")
    if parsed is None or parsed < MIN_SHIM_VERSION:
        needed = MIN_SHIM_TEXT
        return ToolRow(
            SHIM_NAME,
            path,
            version,
            f"DeeZy needs {needed} or newer, so it isn't used",
            # a path the user gave must work; one DeeZy finds is only skipped
            ok=not (user_value and user_value.strip()),
        )
    return ToolRow(SHIM_NAME, path, version)


def tool_rows(
    base_wd: Path,
    *,
    ffmpeg: str | None = None,
    truehdd: str | None = None,
    dee: str | None = None,
    dee_shim: str | None = None,
    no_shim: bool = False,
) -> list[ToolRow]:
    """The tools an encode would use, found as an encode finds them."""
    found_ffmpeg, found_truehdd, found_dee, bad = FindDependencies().locate(
        base_wd, ffmpeg, truehdd, dee
    )
    return [
        _row(
            "ffmpeg",
            found_ffmpeg,
            ffmpeg_version,
            "not found (every encode needs it)",
            bad,
            required=True,
        ),
        _row(
            "truehdd",
            found_truehdd,
            truehdd_version,
            "not found (TrueHD Atmos sources need it)",
            bad,
            required=False,
        ),
        _dee_row(found_dee, bad),
        _shim_row(base_wd, found_dee, dee_shim, no_shim),
    ]


def tool_lines(rows: list[ToolRow]) -> list[str]:
    """Two lines or more per tool: its version and note, then where it is."""
    lines = []
    for row in rows:
        head = row.version or ("" if row.note else "found")
        if row.note:
            head = f"{head}: {row.note}" if head else row.note
        lines.append(f"{row.name:<{NAME_WIDTH}} {head}")
        indent = " " * (NAME_WIDTH + 1)
        if row.path is not None:
            lines.append(f"{indent}{row.path.absolute()}")
        lines.extend(f"{indent}{line}" for line in row.extra)
    return lines
