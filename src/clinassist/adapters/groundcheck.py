"""Cheap advisory checks on a draft against its transcript.

They flag things for the clinician to look at. They never block, and they are not a faithfulness
metric: the evaluation harness measures that properly. Limits are stated per check.
"""

from __future__ import annotations

import re

_PRONOUNS = ("he", "she", "his", "her", "hers", "him", "himself", "herself")
_NUMBER = re.compile(r"\d+(?:[./]\d+)*")
_MERGED = re.compile(r"[a-z][.,;:][A-Za-z]")


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z']+", text.lower()))


def check_flags(sections: dict[str, str], transcript: str) -> tuple[str, ...]:
    """`sections` maps subjective/objective/assessment/plan to the model's text."""
    flags: list[str] = []
    note = " ".join(sections.values())

    for name, text in sections.items():
        if not text.strip():
            flags.append(f"empty_section:{name}")

    transcript_words = _words(transcript)
    for pronoun in _PRONOUNS:
        if pronoun in _words(note) and pronoun not in transcript_words:
            flags.append(f"pronoun_not_in_transcript:{pronoun}")  # the transcript never said it

    if _MERGED.search(note):
        flags.append("missing_space_after_punctuation")  # misses merged words like "healthand"

    transcript_numbers = set(_NUMBER.findall(transcript))
    if transcript_numbers:  # skipped when speech was transcribed in words ("one fifty over ninety")
        for number in dict.fromkeys(_NUMBER.findall(note)):
            if number not in transcript_numbers:
                flags.append(f"number_not_in_transcript:{number}")
    return tuple(flags)
