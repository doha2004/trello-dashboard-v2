"""
services/utils.py
==================
Text-normalization utilities ported 1:1 from the original n8n JavaScript.

These are intentionally low-level and dependency-free so that both
`cleaning.py` and `kpis.py` can reuse them without circular imports.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Optional

# Matches the JS: /[🀀-🿿]/gu  → a broad block of symbol/emoji-ish glyphs
_SYMBOL_BLOCK_RE = re.compile(r"[\U0001F000-\U0001FFFF]")
# Matches the JS: /[\u2000-\u2BFF]/g → general punctuation / symbols block
_PUNCT_SYMBOL_RE = re.compile(r"[\u2000-\u2BFF]")
_NON_ALNUM_SPACE_RE = re.compile(r"[^a-z0-9\s]")
_MULTI_SPACE_RE = re.compile(r"\s+")
_DIGITS_RE = re.compile(r"\d+")


def clean_text(value: Any) -> str:
    """
    Normalize free text exactly like the JS `cleanText`:
    - stringify
    - strip accents (NFD + combining marks removal)
    - lowercase
    - strip emoji / symbol blocks
    - strip punctuation (keep only a-z0-9 and spaces)
    - collapse whitespace
    - trim
    """
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.lower()
    text = _SYMBOL_BLOCK_RE.sub("", text)
    text = _PUNCT_SYMBOL_RE.sub("", text)
    text = _NON_ALNUM_SPACE_RE.sub("", text)
    text = _MULTI_SPACE_RE.sub(" ", text)
    return text.strip()


def to_key(value: Any) -> str:
    """Equivalent of JS `toKey`: cleaned text, digits removed, spaces removed."""
    text = clean_text(value)
    text = _DIGITS_RE.sub("", text)
    text = _MULTI_SPACE_RE.sub("", text)
    return text


def clean_boolean(value: Any) -> bool:
    """Equivalent of JS `cleanBoolean`."""
    return clean_text(value) in {"true", "1", "yes", "oui"}


def clean_priority(value: Any) -> str:
    """Equivalent of JS `cleanPriority`: returns 'high' or 'normal'."""
    val = clean_text(value)
    if val in {"high", "highest", "urgent"}:
        return "high"
    return "normal"


def clean_status(value: Any) -> str:
    """Equivalent of JS `cleanStatus`: returns 'done' or 'other'."""
    val = clean_text(value)
    if val in {"done", "completed", "approved", "termine", "archive"}:
        return "done"
    return "other"


def clean_dimension(value: Any, fallback: str) -> str:
    """Equivalent of JS `cleanDimension`: cleaned text or fallback if empty."""
    cleaned = clean_text(value)
    return cleaned if cleaned else fallback


def days_between(d1: Optional[Any], d2: Optional[Any]) -> Optional[int]:
    """Equivalent of JS `daysBetween`: integer day difference, or None if invalid/negative."""
    if d1 is None or d2 is None:
        return None
    try:
        diff = round((d2 - d1).total_seconds() / 86400)
    except Exception:
        return None
    return diff if diff >= 0 else None


def avg(values: list) -> Optional[float]:
    """Equivalent of JS `avg`: rounded mean of numeric values, or '' (None) if empty."""
    nums = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    if not nums:
        return None
    return round(sum(nums) / len(nums))
