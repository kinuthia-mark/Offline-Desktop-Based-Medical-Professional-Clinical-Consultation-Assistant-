"""Medicine-name check (AMD-38, ADR-013): flag words that look like a misheard medicine.

Speech-to-text sometimes turns a medicine into a near-miss ("Glendamycin" for clindamycin,
"Nitrofuranta" for nitrofurantoin), and the note generator then copies the mistake faithfully
(ADR-011). A vocabulary hint for Whisper did not help (ADR-013), so instead the transcript is
checked before the clinician approves it: a word is flagged when it is not an English word, not
already a known medicine, and close in spelling to one. The clinician decides; nothing is changed
automatically.

Limits: a mishearing that produces a real English word ("sulfur" for sulfa) is not flagged, and
a medicine missing from clinassist.vocabulary cannot be suggested.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from functools import lru_cache

from clinassist.vocabulary import ALSO_CORRECT, MEDICINES

# How alike two spellings must be (0 to 1). "glendamycin" and "clindamycin" score about 0.82,
# "amlotyping" and "amlodipine" 0.70. Chosen on 40 texts from the evaluation: at 0.65, 0.70 and
# 0.75 the same words were flagged; 0.70 also catches "amlotyping" (ADR-013).
SIMILARITY = 0.70
_WORD = re.compile(r"[A-Za-z][A-Za-z-]{5,}")  # six letters or more: short words give false alarms


@dataclass(frozen=True)
class Suspect:
    word: str  # as written in the transcript
    meant: str  # the closest known medicine


@lru_cache(maxsize=1)
def _known() -> tuple[set[str], list[str]]:
    from spellchecker import SpellChecker  # bundled English dictionary, works offline

    names = [m for m in MEDICINES if " " not in m]
    return set(SpellChecker().word_frequency.dictionary), names


def suspect_medicines(text: str) -> list[Suspect]:
    """Words in `text` that are probably a medicine name heard wrongly, each once."""
    english, names = _known()
    found: dict[str, Suspect] = {}
    for word in _WORD.findall(text):
        lower = word.lower()
        if lower in found or lower in names or lower in english or lower in ALSO_CORRECT:
            continue
        close = difflib.get_close_matches(lower, names, n=1, cutoff=SIMILARITY)
        if close:
            found[lower] = Suspect(word, close[0])
    return list(found.values())
