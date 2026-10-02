"""Detects the repetition loops seen in the MedGemma spike (ADR-002).

Without a repetition penalty, 8 of 8 long-consultation generations repeated the same sentences
until the token cap. Streaming lets us spot that early and stop, instead of waiting minutes.
"""

from __future__ import annotations

import re
from collections import Counter

_KEY_PREFIX = re.compile(r'"?(subjective|objective|assessment|plan|suggestions)"?\s*:\s*"?', re.I)
_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_STRIP = re.compile(r'^[\s"{}\[\],:]+|[\s"{}\[\],:]+$')


def _sentences(text: str) -> list[str]:
    cleaned = _KEY_PREFIX.sub(" ", text)
    parts = _SPLIT.split(cleaned)
    if parts and not re.search(r"[.!?][\"'}\]\s]*$", cleaned):
        parts = parts[:-1]  # the last fragment is still being written
    out = []
    for part in parts:
        norm = re.sub(r"\s+", " ", _STRIP.sub("", part)).lower()
        if norm:
            out.append(norm)
    return out


def find_repetition(
    text: str,
    *,
    short_min: int = 20,
    short_repeats: int = 3,
    long_min: int = 60,
    long_repeats: int = 2,
    tail_chars: int = 120,
    tail_min_total: int = 400,
) -> str | None:
    """Return a description of the repetition found, or None.

    A loop is: the same sentence of at least `short_min` characters three times, the same
    sentence of at least `long_min` characters twice, or the last `tail_chars` characters
    already appearing earlier in the text (loops without sentence breaks).
    """
    counts = Counter(s for s in _sentences(text) if len(s) >= short_min)
    for sentence, n in counts.items():
        if (n >= short_repeats) or (len(sentence) >= long_min and n >= long_repeats):
            return f"sentence repeated {n} times"
    if len(text) >= tail_min_total:
        tail = text[-tail_chars:]
        if tail in text[:-tail_chars]:
            return "tail repeated"
    return None
