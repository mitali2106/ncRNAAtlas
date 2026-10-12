"""Generic text cleaning that never alters biologically meaningful content."""
import re
import unicodedata

_WS = re.compile(r"\s+")
_DASHES = dict.fromkeys(map(ord, "‐‑‒–—−－"), "-")
_QUOTES = dict.fromkeys(map(ord, "‘’“”´`"), "'")


def clean_text(value):
    """Trim, collapse internal whitespace and strip wrapping quotes.

    Returns ``None`` for empty / missing values (including pandas NaN).
    Case is preserved: capitalization can be meaningful (``miR`` vs ``mir``).
    """
    if value is None:
        return None
    if isinstance(value, float) and value != value:  # NaN
        return None
    text = unicodedata.normalize("NFKC", str(value)).translate(_DASHES).translate(_QUOTES)
    text = _WS.sub(" ", text).strip()
    while len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1].strip()
    return text or None


def normalize_key(value):
    """Case-insensitive comparison key (used for exact-match deduplication only)."""
    text = clean_text(value)
    if text is None:
        return None
    text = text.lower().rstrip(".")
    text = re.sub(r"\s*,\s*", ", ", text)
    text = re.sub(r"\s*-\s*", "-", text)
    return text


def clean_pmid(value):
    """Return a PMID as a digit string, or ``None`` if the value is not a PMID."""
    text = clean_text(value)
    if not text:
        return None
    if text.endswith(".0") and text[:-2].isdigit():  # spreadsheet float artifacts
        text = text[:-2]
    if text.isdigit() and 1 <= len(text) <= 9 and int(text) > 0:
        return text
    return None


def split_pmids(value):
    """Split a field that may hold several PMIDs (``;``, ``,``, ``|`` or whitespace)."""
    text = clean_text(value)
    if not text:
        return []
    out = []
    for part in re.split(r"[;,|\s]+", text):
        pmid = clean_pmid(part)
        if pmid and pmid not in out:
            out.append(pmid)
    return out


def like_escape(value):
    """Escape SQL LIKE wildcards in user input (used with ``escape='\\'``)."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
