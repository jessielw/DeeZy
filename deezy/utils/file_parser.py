import glob
from pathlib import Path


def parse_input_s(args_list: list[str]) -> list[Path]:
    """Parse CLI-style file inputs and return absolute file Paths.

    The function accepts a list of input tokens (for example what you'd get
    from ``argparse`` with ``nargs="+"``). Each token may be:

    - a single file path (absolute or relative),
    - a non-recursive glob containing ``*`` (e.g. ``folder/*.mp4``), or
    - a recursive glob containing ``**`` (e.g. ``folder/**/*.mkv`` or
        ``**/*.txt``).

    Behavior and guarantees:

    - Returns a list of absolute :class:`pathlib.Path` objects pointing to
        files only (directories are filtered out).
    - If a token contains ``**``, the implementation attempts to use
        :meth:`pathlib.Path.rglob` for efficiency when the prefix is a literal
        directory. If the prefix contains glob metacharacters (``*``, ``?``,
        or ``[``), the function falls back to :func:`glob.glob(..., recursive=True)`
        so patterns like ``foo*/**/*.txt`` are expanded correctly.
    - Tokens with a single ``*`` are expanded with :func:`glob.iglob`.
    - An empty/whitespace-only token is rejected and raises
        :class:`FileNotFoundError`.
    - Results are deduplicated by absolute path while preserving first-seen
        order (useful when multiple overlapping patterns are provided).
    - When a recursive pattern has an empty prefix (for example ``**/*.txt``),
        the search base is the current working directory (``Path('.')``), which
        matches typical CLI expectations.

    Raises:
        FileNotFoundError: If a provided token doesn't match any file or is
        not a valid path.
    """
    input_s = []
    for arg_input in args_list:
        arg_input = arg_input.strip()

        # reject empty/whitespace-only args early
        if not arg_input:
            raise FileNotFoundError(f"'{arg_input}' is not a valid input path.")

        # recursive search: prefer pathlib.Path.rglob for literal prefixes
        # (faster and preserves root semantics); fall back to glob.glob
        # when the prefix itself contains glob metacharacters. Handle '**'
        # before '*' so recursive patterns are processed correctly.
        if "**" in arg_input:
            matches = []
            # split the pattern at the first occurrence of ** to determine base
            prefix, _sep, after = arg_input.partition("**")

            # If the prefix contains glob magic characters, fall back to
            # glob.glob with recursive=True so patterns like 'foo*/**/*.txt'
            # are expanded correctly. Otherwise use pathlib.Path.rglob which
            # preserves root semantics and is more efficient for literal bases.
            if prefix and glob.has_magic(prefix):
                for p_str in glob.glob(arg_input, recursive=True):
                    p = Path(p_str)
                    if p.is_file():
                        matches.append(p.absolute())
            else:
                base = Path(prefix) if prefix else Path(".")
                # relative pattern to pass to rglob (strip leading path separators)
                rel_pattern = after.lstrip("/\\")
                pattern = rel_pattern if rel_pattern else "*"
                for p in base.rglob(pattern):
                    if p.is_file():
                        matches.append(p.absolute())

            input_s.extend(matches)

        # non recursive (single-star) patterns
        elif "*" in arg_input:
            # use iglob to avoid creating an intermediate list
            matches = []
            for p_str in glob.iglob(arg_input):
                p = Path(p_str)
                if p.is_file():
                    matches.append(p.absolute())
            input_s.extend(matches)

        # single file path
        else:
            p = Path(arg_input)
            if p.exists() and p.is_file() and arg_input != "":
                input_s.append(p.absolute())
            else:
                raise FileNotFoundError(f"'{arg_input}' is not a valid input path.")

    # deduplicate while preserving order (user may pass overlapping patterns)
    seen = set()
    deduped = []
    for p in input_s:
        if p not in seen:
            seen.add(p)
            deduped.append(p)

    return deduped
