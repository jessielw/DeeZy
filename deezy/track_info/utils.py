import re
from pathlib import Path

DELAY_REGEX = r"delay\s*(-?\d+(?:ms|s))"


def parse_delay_from_file(media_path: Path) -> str | None:
    """Parse delay from filename, if None found return 0ms."""
    match = re.search(DELAY_REGEX, media_path.name, flags=re.I)
    if match:
        return match.group(1)


def strip_delay_from_file_string_and_cleanse(media_path: Path) -> Path:
    """Remove all delay strings from a file path and return the modified path."""
    suffix = media_path.suffix
    name_without_suffix = media_path.stem
    # remove any 'delay <n>ms' or 'delay<n>s' occurrences (case-insensitive)
    cleaned = re.sub(
        DELAY_REGEX,
        "",
        name_without_suffix,
        flags=re.I,
    )
    # collapse multiple spaces into one
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    # remove spaces around common separators (underscores, dashes, dots)
    cleaned = re.sub(r"\s*[_\-\.]\s*", lambda m: m.group(0).strip(), cleaned)
    # strip trailing separators left before the suffix
    cleaned = re.sub(r"[\._\-\s]+$", "", cleaned)
    # return reconstructed filename
    return Path(f"{cleaned}{suffix}")
