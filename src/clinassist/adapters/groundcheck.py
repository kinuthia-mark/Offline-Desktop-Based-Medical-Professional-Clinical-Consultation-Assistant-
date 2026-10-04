"""Advisory checks on a draft against its transcript.

They flag things for the clinician to look at. They never block, and they are not a faithfulness
metric: the evaluation harness measures that properly. Limits are stated per check.
"""

from __future__ import annotations

import re
from functools import lru_cache

from clinassist.adapters.numbers import find_numbers

_PRONOUNS = ("he", "she", "his", "her", "hers", "him", "himself", "herself")
_MERGED_PUNCT = re.compile(r"[a-z][.,;:][A-Za-z]")
_LIST_MARKER = re.compile(r"(?:(?<=\s)|^)\d{1,2}\.\s+(?=[A-Z])")  # "6. ECG today" is numbering


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z']+", text.lower()))


@lru_cache(maxsize=1)
def _spell():
    from spellchecker import SpellChecker  # bundled English dictionary, works offline

    return SpellChecker()


def merged_words(note: str, transcript_words: set[str]) -> list[str]:
    """Words that are not in the dictionary or the transcript but split into two that are
    ("healthand", "whenpassing"). Words the clinician said are trusted, so drug names are safe."""
    spell = _spell()
    found = []
    for word in dict.fromkeys(re.findall(r"[A-Za-z]{6,}", note)):
        lower = word.lower()
        if lower in transcript_words or spell.known([lower]):
            continue
        for i in range(2, len(lower) - 1):
            if spell.known([lower[:i]]) and spell.known([lower[i:]]):
                found.append(word)
                break
    return found


def check_flags(sections: dict[str, str], transcript: str) -> tuple[str, ...]:
    """`sections` maps subjective/objective/assessment/plan to the model's text."""
    flags: list[str] = []
    note = " ".join(sections.values())
    transcript_words = _words(transcript)

    for name, text in sections.items():
        if not text.strip():
            flags.append(f"empty_section:{name}")

    for pronoun in _PRONOUNS:
        if pronoun in _words(note) and pronoun not in transcript_words:
            flags.append(f"pronoun_not_in_transcript:{pronoun}")  # the transcript never said it

    if _MERGED_PUNCT.search(note):
        flags.append("missing_space_after_punctuation")
    try:
        flags.extend(f"possible_merged_word:{w}" for w in merged_words(note, transcript_words))
    except ImportError:
        flags.append("merged_word_check_unavailable")

    # Numbers, written as digits or words. A pair like 152/94 must appear as a pair, because its
    # two numbers can each occur elsewhere. Each check is skipped when the transcript has nothing
    # of that kind to compare with.
    t_singles, t_pairs = find_numbers(transcript)
    n_singles, n_pairs = find_numbers(_LIST_MARKER.sub(" ", note))
    if t_pairs:
        known_pairs = set().union(*(p.readings for p in t_pairs))
        flags.extend(
            f"number_not_in_transcript:{p.text}" for p in n_pairs if not (p.readings & known_pairs)
        )
    if t_singles:
        known = set().union(*(s.readings for s in t_singles))
        in_pairs = {pos for p in n_pairs for pos in p.starts}
        flags.extend(
            f"number_not_in_transcript:{s.text}"
            for s in n_singles
            if s.start not in in_pairs and not (s.readings & known)
        )
    return tuple(dict.fromkeys(flags))
