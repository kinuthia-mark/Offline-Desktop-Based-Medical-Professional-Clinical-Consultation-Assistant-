"""Word error rate (WER) for measuring speech-to-text (NFR-06, ADR-007).

WER = (substituted + deleted + inserted words) / words in the reference. 0.0 is perfect; 0.1
means about one word in ten is wrong. It is the standard measure for speech recognition.

Before comparing, both texts are normalised the same way: lower case, punctuation removed,
"Doctor:" and "Patient:" labels dropped, and hyphens split ("long-term" -> "long term").
`numbers_as_digits=True` also writes spoken numbers as digits ("three" -> "3", "twenty two"
-> "22", and the clinical habit "one fifty two" -> "152"), because Whisper often writes digits
where the script has words. `standard_spelling=True` also treats British and American spellings
and written-out units as the same word (litre/liter, milligrams/mg), as speech-recognition
scoring usually does. The raw score is always reported next to the normalised ones.

`term_recall` counts how many mentions of chosen words (for example medicine names) came out
exactly right, because one misheard drug name matters more than several misheard small words.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

_UNITS = "zero one two three four five six seven eight nine".split()
_TEENS = "ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
_TENS = "twenty thirty forty fifty sixty seventy eighty ninety".split()
_VALUE = (
    {w: i for i, w in enumerate(_UNITS)}
    | {w: 10 + i for i, w in enumerate(_TEENS)}
    | {w: 20 + 10 * i for i, w in enumerate(_TENS)}
)


# British -> American spellings and written-out units, applied when standard_spelling=True.
_SAME_WORD = {
    "diarrhoea": "diarrhea",
    "haemoglobin": "hemoglobin",
    "anaemia": "anemia",
    "oedema": "edema",
    "litre": "liter",
    "litres": "liters",
    "neighbour": "neighbor",
    "colour": "color",
    "paediatric": "pediatric",
    "oesophagus": "esophagus",
    "milligrams": "mg",
    "milligram": "mg",
    "kilograms": "kg",
    "kilogram": "kg",
    "okay": "ok",
}
_SAME_PHRASE = {"alright": "all right", "nighttime": "night time"}


@dataclass(frozen=True)
class WerResult:
    wer: float
    substitutions: int
    deletions: int
    insertions: int
    reference_words: int


def normalize(
    text: str, numbers_as_digits: bool = False, standard_spelling: bool = False
) -> list[str]:
    lines = [
        re.sub(r"^\s*(doctor|patient)\s*:", " ", line, flags=re.I)
        for line in text.splitlines()
        if not line.lstrip().startswith("#")  # comment lines in the synthetic scripts
    ]
    text = " ".join(lines).lower().replace("-", " ")
    words = re.findall(r"[a-z0-9]+(?:[.'][a-z0-9]+)*", text)
    if standard_spelling:
        words = " ".join(_SAME_PHRASE.get(w, w) for w in words).split()
        words = [_SAME_WORD.get(w, w) for w in words]
    return _digits(words) if numbers_as_digits else words


def _below_100(words: list[str], i: int) -> tuple[int, int] | None:
    """Read a number from 1 to 99 starting at words[i] ("four", "fifty", "forty two").
    Returns (value, index after it), or None."""
    if i >= len(words):
        return None
    w = words[i]
    if w in _TENS:
        if i + 1 < len(words) and words[i + 1] in _UNITS[1:]:
            return _VALUE[w] + _VALUE[words[i + 1]], i + 2
        return _VALUE[w], i + 1
    if w in _TEENS or w in _UNITS[1:]:
        return _VALUE[w], i + 1
    return None


def _digits(words: list[str]) -> list[str]:
    """Write number words as digits: "twenty two" -> "22", "one hundred and four" -> "104",
    and the clinical habit "one fifty two" -> "152"."""
    out: list[str] = []
    i = 0
    while i < len(words):
        w = words[i]
        if w not in _VALUE:
            out.append(w)
            i += 1
            continue
        nxt = words[i + 1] if i + 1 < len(words) else ""
        if w in _UNITS[1:] and nxt == "hundred":
            # "one hundred", "two hundred and fifty", "one hundred forty four"
            value, i = _VALUE[w] * 100, i + 2
            j = i + 1 if i < len(words) and words[i] == "and" else i
            rest = _below_100(words, j)
            if rest:
                value, i = value + rest[0], rest[1]
        elif w in _UNITS[1:] and (nxt in _TENS or nxt in _TEENS):
            # "one fifty two" or "one twelve": a blood pressure said without "hundred"
            rest = _below_100(words, i + 1)
            value, i = _VALUE[w] * 100 + rest[0], rest[1]
        else:
            value, i = _below_100(words, i) or (_VALUE[w], i + 1)
        out.append(str(value))
    return out


def word_error_rate(
    reference: str,
    hypothesis: str,
    numbers_as_digits: bool = False,
    standard_spelling: bool = False,
) -> WerResult:
    """Compare what was said (reference) with what speech-to-text wrote (hypothesis)."""
    ref = normalize(reference, numbers_as_digits, standard_spelling)
    hyp = normalize(hypothesis, numbers_as_digits, standard_spelling)
    # Edit distance between the two word lists, keeping track of which kind of edit each step
    # was. row[j] holds (cost, substitutions, deletions, insertions) for ref[:i] vs hyp[:j].
    row = [(j, 0, 0, j) for j in range(len(hyp) + 1)]
    for i in range(1, len(ref) + 1):
        new = [(i, 0, i, 0)]
        for j in range(1, len(hyp) + 1):
            if ref[i - 1] == hyp[j - 1]:
                new.append(row[j - 1])
                continue
            sub, dele, ins = row[j - 1], row[j], new[j - 1]
            best = min(
                (sub[0] + 1, sub[1] + 1, sub[2], sub[3]),
                (dele[0] + 1, dele[1], dele[2] + 1, dele[3]),
                (ins[0] + 1, ins[1], ins[2], ins[3] + 1),
            )
            new.append(best)
        row = new
    cost, s, d, n = row[-1]
    return WerResult(
        wer=round(cost / len(ref), 4) if ref else float(bool(hyp)),
        substitutions=s,
        deletions=d,
        insertions=n,
        reference_words=len(ref),
    )


def term_recall(reference: str, hypothesis: str, terms: list[str]) -> tuple[int, int]:
    """How many mentions of `terms` in the reference also appear in the hypothesis, as
    (found, total). Each mention counts once, so three "amlodipine" said and one written gives
    1 of 3."""
    ref = Counter(normalize(reference))
    hyp = Counter(normalize(hypothesis))
    wanted = {t.lower() for t in terms}
    total = sum(n for w, n in ref.items() if w in wanted)
    found = sum(min(n, hyp[w]) for w, n in ref.items() if w in wanted)
    return found, total
