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
    # return reconstructed filename
    return Path(f"{cleaned}{suffix}")


def clean_title(s: str) -> str:
    """Return a cleaned track/title string.

    Removes common metadata decorations such as bracketed language tags,
    delay tokens, codec tokens, sample rates, audio channel hints (5.1, stereo, etc.),
    leading track numbers, and common separators.

    Returns the cleaned string with internal whitespace normalized.
    """
    # remove bracketed or parenthesized tags: [eng], (jpn), etc.
    s = re.sub(r"[\[\(][^\]\)]+[\]\)]", "", s)

    # remove explicit delay tokens (e.g. "DELAY 12ms", "delay-5ms")
    s = re.sub(r"\bdelay\s*[-:]?\s*-?\d+\s*(?:ms|s)?\b", "", s, flags=re.I)

    # remove numeric audio channel info like 5.1, 7.1ch, 5ch; remove simple words
    # such as 'stereo' and 'mono' but keep words that can be valid titles
    # (e.g. 'surround', 'multichannel') so we don't strip meaningful titles.
    s = re.sub(r"(?<!\w)(?:\d+\.\d+(?:ch)?|\d+\s*ch)(?!\w)", "", s, flags=re.I)
    s = re.sub(r"(?<!\w)(?:stereo|mono|dual\s+mono)(?!\w)", "", s, flags=re.I)

    # remove codec/sample rate tokens only if not the only word left
    s = re.sub(
        r"(\s|-|_|\b)(ac3|eac3|ddp|dts|flac|aac|mp3|wav|pcm|mka|m4a|ogg|"
        r"opus|alac|wma|ape|aiff|dsd|wv|48k(?:hz)?|96k(?:hz)?|192k(?:hz)?)(\s|-|_|\b)",
        " ",
        s,
        flags=re.I,
    )

    # normalize separators to spaces
    s = re.sub(r"[_.]+", " ", s)

    # replace any remaining non-word separators with spaces
    s = re.sub(r"[^\w\s\-&]", " ", s)

    # collapse runs of spaces or hyphens
    s = re.sub(r"[\-\s]{2,}", " ", s)

    return s.strip()
