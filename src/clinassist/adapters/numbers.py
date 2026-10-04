"""Find numbers in text, written as digits or spoken words, so a note can be checked against a
transcript that says "one fifty-two over ninety-four" or "152 over 94".

Spoken blood pressures drop the word "hundred", so a run like "one fifty-two" has several
readings (1 and 52, or 152). We keep every plausible reading, so a check only reports a number
when none of its readings appears in the transcript. That favours missing an error over crying
wolf.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_UNITS = {w: i for i, w in enumerate("zero one two three four five six seven eight nine".split())}
_TEENS = {
    w: 10 + i
    for i, w in enumerate(
        "ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
    )
}
_TENS = {
    w: 20 + 10 * i
    for i, w in enumerate("twenty thirty forty fifty sixty seventy eighty ninety".split())
}
_WORDS = set(_UNITS) | set(_TEENS) | set(_TENS) | {"hundred", "point"}
_TOKEN = re.compile(r"\d+(?:\.\d+)?|[a-z]+|/")


@dataclass(frozen=True)
class Occurrence:
    text: str  # as written in the source
    readings: frozenset[str]  # every plausible numeric reading
    start: int
    end: int


@dataclass(frozen=True)
class Pair:
    text: str
    readings: frozenset[tuple[str, str]]
    starts: frozenset[int]  # token positions of its two numbers


def _int_readings(words: list[str]) -> set[str]:
    values: list[int] = []
    i = 0
    while i < len(words):
        w = words[i]
        if w == "hundred":
            if values:
                values[-1] *= 100
        elif w in _TENS:
            v = _TENS[w]
            if i + 1 < len(words) and words[i + 1] in _UNITS and _UNITS[words[i + 1]] > 0:
                v += _UNITS[words[i + 1]]
                i += 1
            values.append(v)
        elif w in _TEENS:
            values.append(_TEENS[w])
        elif w in _UNITS:
            values.append(_UNITS[w])
        i += 1
    readings = {str(v) for v in values}
    if len(values) >= 2:
        if values[0] % 100 == 0 and values[0] >= 100:
            readings.add(str(values[0] + sum(values[1:])))  # "one hundred fifty two"
        if 1 <= values[0] <= 9 and 10 <= values[1] <= 99:
            readings.add(str(values[0] * 100 + values[1]))  # "one fifty two" -> 152
    return readings


def _word_readings(words: list[str]) -> set[str]:
    if "point" in words:
        k = words.index("point")
        left, right = words[:k], words[k + 1 :]
        digits = "".join(str(_UNITS[w]) for w in right if w in _UNITS)
        whole = _int_readings(left) or {"0"}
        return {f"{w}.{digits}" for w in whole} if digits else whole
    return _int_readings(words)


def _canon(token: str) -> str:
    return str(int(token)) if token.isdigit() else token


def find_numbers(text: str) -> tuple[list[Occurrence], list[Pair]]:
    """Return every number, and every pair written as 'A over B' or 'A/B'."""
    tokens = [m.group() for m in _TOKEN.finditer(text.lower())]
    singles: list[Occurrence] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok[0].isdigit():
            singles.append(Occurrence(tok, frozenset({_canon(tok)}), i, i + 1))
            i += 1
        elif tok in _WORDS:
            j = i
            while j < len(tokens) and (
                tokens[j] in _WORDS
                or (tokens[j] == "and" and tokens[j - 1] == "hundred" and tokens[j + 1 : j + 2])
            ):
                j += 1
            run = [t for t in tokens[i:j] if t != "and"]
            singles.append(Occurrence(" ".join(tokens[i:j]), frozenset(_word_readings(run)), i, j))
            i = j
        else:
            i += 1

    pairs: list[Pair] = []
    for a, b in zip(singles, singles[1:], strict=False):
        if b.start == a.end + 1 and tokens[a.end] in {"over", "/"}:
            readings = frozenset((x, y) for x in a.readings for y in b.readings)
            pairs.append(Pair(f"{a.text}/{b.text}", readings, frozenset({a.start, b.start})))
    return singles, pairs
