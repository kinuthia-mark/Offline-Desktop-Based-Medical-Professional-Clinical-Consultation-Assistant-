"""Detects the repetition loops seen in the MedGemma spike (ADR-002).

Without a repetition penalty, 8 of 8 long-consultation generations repeated the same sentences
until the token cap. Streaming lets us spot that early and stop, instead of waiting minutes.
"""

from __future__ import annotations

import re
from collections import Counter

# Patterns used to cut the model's JSON reply into plain sentences:
# the section names ("subjective": ...) are removed so they do not count as repeated text,
_KEY_PREFIX = re.compile(r'"?(subjective|objective|assessment|plan|suggestions)"?\s*:\s*"?', re.I)
# a sentence ends at . ! or ? followed by a space, or at a line break,
_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
# and leftover JSON punctuation at either end of a sentence is trimmed off.
_STRIP = re.compile(r'^[\s"{}\[\],:]+|[\s"{}\[\],:]+$')


def _sentences(text: str) -> list[str]:
    # Returns the finished sentences in lower case with spacing tidied, so "The patient is
    # well." and "the patient  is well." count as the same sentence.
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
    # Count how often each sentence appears. Very short ones ("Not stated.") are ignored,
    # because a real note can repeat those legitimately.
    counts = Counter(s for s in _sentences(text) if len(s) >= short_min)
    for sentence, n in counts.items():
        if (n >= short_repeats) or (len(sentence) >= long_min and n >= long_repeats):
            return f"sentence repeated {n} times"
    # Some loops never end a sentence. For those, check whether the last 120 characters
    # already appeared earlier in the reply, once there is enough text to judge.
    if len(text) >= tail_min_total:
        tail = text[-tail_chars:]
        if tail in text[:-tail_chars]:
            return "tail repeated"
    return None
