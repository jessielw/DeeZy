"""
dee_shim: an optional runner for three of the DEE tools (DD+, DD+ Atmos and
TrueHD).

dee_shim runs the DEE tool inside its own process, with DEE's own arguments
after ``--``. DeeZy finds it, checks its version and keeps the shim's own
environment settings out of its runs. Without it, every job DEE can do alone
runs as before.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import os
from pathlib import Path
import re
import shutil
import subprocess

from deezy.dee.tools import get_executable_extension
from deezy.exceptions import DependencyNotFoundError
from deezy.utils.logger import logger

SHIM_NAME = "dee_shim"
MIN_SHIM_VERSION = (0, 3, 0)
MIN_SHIM_TEXT = ".".join(str(part) for part in MIN_SHIM_VERSION)
# dee_shim's subcommand for each DEE tool it runs
SHIM_SUBCOMMANDS = {
    "dee_ddp_encoder": "ddp_encoder",
    "dee_ddpjoc_encoder": "ddpjoc_encoder",
    "dee_dthd_encoder": "dthd_encoder",
}
# a job dee_shim refuses: one of its own options, or a DEE build it has no
# profile for. DEE's own failures pass through with DEE's exit code.
SHIM_REFUSED = 2
# a DEE build that doesn't match the shim
SHIM_BUILD_MISMATCH = 3

# the settings dee_shim reads from its environment, which would change its
# output or its log behind DeeZy's back
_SHIM_ENV_PREFIXES = ("DSHIM_", "DEE_SHIM_")
_SHIM_ENV_NAMES = ("RUST_LOG",)
# `v0.3.0+g2ae7f95` as -V prints it, or `0.3.0+g2ae7f95` as DeeZy keeps it
_VERSION = re.compile(r"(?<![\w.])v?(\d+)\.(\d+)\.(\d+)(\S*)")
# dee_shim's own error lines: its option parser's and its runner's
_ERROR_PREFIXES = ("error: ", "dee_shim ERROR: ")
_NO_PROFILE = "no optional shim profile"


@dataclass(frozen=True, slots=True)
class DeeShim:
    path: Path
    # as `dee_shim -V` reports it, e.g. `0.3.0+g2ae7f95`
    version: str

    def argv(self, dee_argv: Sequence[str], *shim_args: str) -> tuple[str, ...]:
        """A DEE command run through dee_shim, with the shim's options first."""
        tool = Path(dee_argv[0])
        return (
            str(self.path),
            SHIM_SUBCOMMANDS[tool.stem],
            *shim_args,
            "--binary",
            str(tool),
            "--",
            *dee_argv[1:],
        )


def parse_version(text: str) -> tuple[int, int, int] | None:
    found = _VERSION.search(text)
    if not found:
        return None
    major, minor, patch = (int(part) for part in found.groups()[:3])
    return major, minor, patch


def _version_text(text: str) -> str | None:
    found = _VERSION.search(text)
    if not found:
        return None
    major, minor, patch, suffix = found.groups()
    return f"{major}.{minor}.{patch}{suffix}"


def clean_env(environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """The environment without the variables dee_shim reads."""
    source = os.environ if environ is None else environ
    return {
        key: value
        for key, value in source.items()
        if not key.upper().startswith(_SHIM_ENV_PREFIXES)
        and key.upper() not in _SHIM_ENV_NAMES
    }


def shim_version(path: Path) -> str | None:
    """The version `dee_shim -V` reports, e.g. `0.3.0+g2ae7f95`."""
    try:
        proc = subprocess.run(  # noqa: S603
            [str(path), "-V"],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=30,
            env=clean_env(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return _version_text((proc.stdout or "") + (proc.stderr or ""))


def find_shim(base_wd: Path, dee_dir: Path | None) -> Path | None:
    """dee_shim beside the DEE tools, then beside DeeZy, then on PATH."""
    name = f"{SHIM_NAME}{get_executable_extension()}"
    candidates = [base_wd / "apps" / SHIM_NAME / name]
    if dee_dir:
        candidates.insert(0, dee_dir / name)
    found = next((path for path in candidates if path.is_file()), None)
    if found:
        return found
    on_path = shutil.which(name)
    return Path(on_path) if on_path else None


def user_shim_path(user_value: str) -> Path:
    """The dee_shim a path or command name the user gave names."""
    candidate = Path(user_value.strip()).expanduser()
    if candidate.is_file():
        return candidate
    on_path = shutil.which(str(candidate))
    if on_path:
        return Path(on_path)
    raise DependencyNotFoundError(
        f"Configured dependency path does not exist: {SHIM_NAME} ('{user_value}')."
    )


def resolve_shim(
    base_wd: Path,
    dee_dir: Path | None,
    user_value: str | None = None,
    disabled: bool = False,
) -> DeeShim | None:
    """
    The dee_shim DeeZy may run, or None.

    A path the user gives must exist and report 0.3.0 or newer. One DeeZy
    finds by itself that reports an older version is skipped with a warning,
    since the shim is optional.
    """
    if disabled:
        logger.debug(f"{SHIM_NAME} is turned off.")
        return None
    explicit = bool(user_value and user_value.strip())
    path = user_shim_path(user_value) if explicit else find_shim(base_wd, dee_dir)  # pyright: ignore[reportArgumentType]
    if path is None:
        logger.debug(f"{SHIM_NAME} not found.")
        return None
    version = shim_version(path)
    parsed = parse_version(version or "")
    if parsed is None or parsed < MIN_SHIM_VERSION:
        needed = MIN_SHIM_TEXT
        reported = version or "no version"
        if explicit:
            raise DependencyNotFoundError(
                f"DeeZy needs {SHIM_NAME} {needed} or newer, but '{path}' "
                f"reports {reported}."
            )
        logger.warning(
            f"Skipping {SHIM_NAME} at '{path}': it reports {reported}, and DeeZy "
            f"needs {needed} or newer."
        )
        return None
    logger.debug(f"{SHIM_NAME} {version}: {path}")
    return DeeShim(path, version)  # pyright: ignore[reportArgumentType]


def is_shim_command(cmd: Sequence[str]) -> bool:
    """Whether a DEE command runs through dee_shim (see `DeeShim.argv`)."""
    return len(cmd) > 1 and cmd[1] in SHIM_SUBCOMMANDS.values() and "--" in cmd


def shim_binary(cmd: Sequence[str]) -> Path | None:
    """The DEE tool a dee_shim command runs, or None for a plain DEE command."""
    if not is_shim_command(cmd):
        return None
    own = cmd[: cmd.index("--")]
    return Path(own[own.index("--binary") + 1]) if "--binary" in own else None


def shim_failure(return_code: int, lines: Sequence[str]) -> str | None:
    """
    dee_shim's reason for a failed run, or None when DEE itself failed (its
    errors pass through dee_shim unchanged).
    """
    if return_code not in (SHIM_REFUSED, SHIM_BUILD_MISMATCH):
        return None
    reasons = [
        line[len(prefix) :].strip()
        for line in lines
        for prefix in _ERROR_PREFIXES
        if line.startswith(prefix)
    ]
    reason = reasons[0] if reasons else ""
    if return_code == SHIM_BUILD_MISMATCH or _NO_PROFILE in reason:
        detail = f" ({reason})" if reason else ""
        return (
            f"{SHIM_NAME} doesn't support this DEE build{detail}. Use a "
            f"{SHIM_NAME} release made for it, or turn it off with --no-shim."
        )
    if reason:
        return f"{SHIM_NAME} refused the job: {reason}"
    return None
