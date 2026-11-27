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

# This file measures how good the speech-to-text is. The evaluation scripts call word_error_rate()
# to compare what a speaker said with what Whisper (the speech model) wrote, and term_recall()
# to check that important words such as medicine names came out right.
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

# Spoken number words. _VALUE below maps each one to its number (one -> 1, fourteen -> 14, sixty
# -> 60).
_UNITS = "zero one two three four five six seven eight nine".split()
_TEENS = "ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
_TENS = "twenty thirty forty fifty sixty seventy eighty ninety".split()
# The | joins the three small dictionaries into one lookup table.
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


# The result of one comparison. frozen=True makes it read-only once made.
@dataclass(frozen=True)
class WerResult:
    wer: float
    substitutions: int
    deletions: int
    insertions: int
    reference_words: int


# Turns text into a clean list of words, so two texts can be compared fairly.
def normalize(
    text: str, numbers_as_digits: bool = False, standard_spelling: bool = False
) -> list[str]:
    # Drop the speaker labels and the comment lines, one line of text at a time.
    lines = [
        re.sub(r"^\s*(doctor|patient)\s*:", " ", line, flags=re.I)
        for line in text.splitlines()
        if not line.lstrip().startswith("#")  # comment lines in the synthetic scripts
    ]
    text = " ".join(lines).lower().replace("-", " ")
    # A word is letters and digits. An inner . or ' is kept, so "3.5" and "don't" stay whole.
    words = re.findall(r"[a-z0-9]+(?:[.'][a-z0-9]+)*", text)
    # Make spellings and units the same first (alright -> all right), then single words.
    if standard_spelling:
        words = " ".join(_SAME_PHRASE.get(w, w) for w in words).split()
        words = [_SAME_WORD.get(w, w) for w in words]
    # Number words are only turned into digits when asked.
    return _digits(words) if numbers_as_digits else words


# Helper for _digits: reads a number below 100 that is spelled out in words.
def _below_100(words: list[str], i: int) -> tuple[int, int] | None:
    """Read a number from 1 to 99 starting at words[i] ("four", "fifty", "forty two").
    Returns (value, index after it), or None."""
    if i >= len(words):
        return None
    w = words[i]
    if w in _TENS:
        # A tens word can be followed by a unit: "forty" then "two" is 42.
        if i + 1 < len(words) and words[i + 1] in _UNITS[1:]:
            return _VALUE[w] + _VALUE[words[i + 1]], i + 2
        return _VALUE[w], i + 1
    # Teens and 1 to 9 stand alone. _UNITS[1:] leaves out "zero".
    if w in _TEENS or w in _UNITS[1:]:
        return _VALUE[w], i + 1
    return None


# Helper for normalize(): walks along the words and replaces spelled-out numbers with digits.
def _digits(words: list[str]) -> list[str]:
    """Write number words as digits: "twenty two" -> "22", "one hundred and four" -> "104",
    and the clinical habit "one fifty two" -> "152"."""
    out: list[str] = []
    i = 0
    while i < len(words):
        w = words[i]
        # Not a number word, so keep it as it is.
        if w not in _VALUE:
            out.append(w)
            i += 1
            continue
        # The next word, or empty text when this is the last word.
        nxt = words[i + 1] if i + 1 < len(words) else ""
        if w in _UNITS[1:] and nxt == "hundred":
            # "one hundred", "two hundred and fifty", "one hundred forty four"
            value, i = _VALUE[w] * 100, i + 2
            # An "and" may come before the rest ("one hundred and four"), so skip it.
            j = i + 1 if i < len(words) and words[i] == "and" else i
            rest = _below_100(words, j)
            if rest:
                value, i = value + rest[0], rest[1]
        elif w in _UNITS[1:] and (nxt in _TENS or nxt in _TEENS):
            # "one fifty two" or "one twelve": a blood pressure said without "hundred"
            rest = _below_100(words, i + 1)
            value, i = _VALUE[w] * 100 + rest[0], rest[1]
        else:
            # A plain number. If _below_100 cannot read it, use the word's own value.
            value, i = _below_100(words, i) or (_VALUE[w], i + 1)
        out.append(str(value))
    return out


# The main function of this file. WER counts the fewest word changes that turn the reference
# into the hypothesis. That count is called the edit distance.
def word_error_rate(
    reference: str,
    hypothesis: str,
    numbers_as_digits: bool = False,
    standard_spelling: bool = False,
) -> WerResult:
    """Compare what was said (reference) with what speech-to-text wrote (hypothesis)."""
    # Both texts are cleaned the same way before they are compared.
    ref = normalize(reference, numbers_as_digits, standard_spelling)
    hyp = normalize(hypothesis, numbers_as_digits, standard_spelling)
    # Edit distance between the two word lists, keeping track of which kind of edit each step
    # was. row[j] holds (cost, substitutions, deletions, insertions) for ref[:i] vs hyp[:j].
    # First row: with no reference words yet, every hypothesis word so far is an insertion.
    row = [(j, 0, 0, j) for j in range(len(hyp) + 1)]
    for i in range(1, len(ref) + 1):
        # First column: reference words against nothing are all deletions.
        new = [(i, 0, i, 0)]
        for j in range(1, len(hyp) + 1):
            # Same word, so no cost. Copy the result from the diagonal.
            if ref[i - 1] == hyp[j - 1]:
                new.append(row[j - 1])
                continue
            # The three ways to reach this cell: replace a word (diagonal), delete one (above),
            # insert one (left).
            sub, dele, ins = row[j - 1], row[j], new[j - 1]
            # Keep the cheapest. Tuples compare by their first value, which is the cost.
            best = min(
                (sub[0] + 1, sub[1] + 1, sub[2], sub[3]),
                (dele[0] + 1, dele[1], dele[2] + 1, dele[3]),
                (ins[0] + 1, ins[1], ins[2], ins[3] + 1),
            )
            new.append(best)
        # Only the previous row is needed for the next one, so older rows are thrown away.
        row = new
    cost, s, d, n = row[-1]
    return WerResult(
        # WER is edits divided by reference words. With an empty reference it is 1.0 if anything
        # was written, else 0.0.
        wer=round(cost / len(ref), 4) if ref else float(bool(hyp)),
        substitutions=s,
        deletions=d,
        insertions=n,
        reference_words=len(ref),
    )


# Checks the words that matter most, such as drug names, because one wrong drug name is worse
# than several wrong small words.
def term_recall(reference: str, hypothesis: str, terms: list[str]) -> tuple[int, int]:
    """How many mentions of `terms` in the reference also appear in the hypothesis, as
    (found, total). Each mention counts once, so three "amlodipine" said and one written gives
    1 of 3."""
    # A Counter holds how many times each word appears.
    ref = Counter(normalize(reference))
    hyp = Counter(normalize(hypothesis))
    # The wanted terms in lower case, in a set for quick lookup.
    wanted = {t.lower() for t in terms}
    # How many mentions of the wanted terms there are in the reference.
    total = sum(n for w, n in ref.items() if w in wanted)
    # min() stops extra copies in the hypothesis counting for more than the reference has.
    found = sum(min(n, hyp[w]) for w, n in ref.items() if w in wanted)
    return found, total
