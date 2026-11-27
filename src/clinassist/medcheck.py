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

# This file warns about medicine names the speech model probably misheard. It runs on
# the transcript before the clinician approves it (the first gate) and only flags
# words; the clinician decides. It uses the medicine list in vocabulary.py.
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from functools import lru_cache

from clinassist.vocabulary import ALSO_CORRECT, MEDICINES

# How alike two spellings must be (0 to 1). "glendamycin" and "clindamycin" score about 0.82,
# "amlotyping" and "amlodipine" 0.70. Chosen on 40 texts from the evaluation: at 0.65, 0.70 and
# 0.75 the same words were flagged; 0.70 also catches "amlotyping" (ADR-013).
# Cut-off for "close in spelling". Higher means stricter and fewer flags.
SIMILARITY = 0.70
# Pattern for a possible medicine word: letters and hyphens, starting with a letter.
_WORD = re.compile(r"[A-Za-z][A-Za-z-]{5,}")  # six letters or more: short words give false alarms


# One flagged word and the medicine it may have been meant to be.
@dataclass(frozen=True)
class Suspect:
    word: str  # as written in the transcript
    meant: str  # the closest known medicine


# Cached so the dictionary is built once, not for every transcript.
@lru_cache(maxsize=1)
# Builds the two lookup collections: all English words (offline), and single-word medicines.
def _known() -> tuple[set[str], list[str]]:
    # Imported here so it is only loaded when the check really runs.
    from spellchecker import SpellChecker  # bundled English dictionary, works offline

    # Medicines made of one word only, because the pattern above matches one word at a time.
    names = [m for m in MEDICINES if " " not in m]
    # Every word the English dictionary knows, for quick membership tests.
    return set(SpellChecker().word_frequency.dictionary), names


# The check itself. Finds words that are not English, not a known medicine, but look like one.
def suspect_medicines(text: str) -> list[Suspect]:
    """Words in `text` that are probably a medicine name heard wrongly, each once."""
    english, names = _known()
    # Keyed by the lower-case word, so a word repeated in the text is reported once.
    found: dict[str, Suspect] = {}
    # Look at each long-enough word in the text.
    for word in _WORD.findall(text):
        lower = word.lower()
        # Skip words already flagged, known medicines, English words and accepted extra spellings.
        if lower in found or lower in names or lower in english or lower in ALSO_CORRECT:
            continue
        # Best single match above SIMILARITY from the medicine names, or an empty list.
        close = difflib.get_close_matches(lower, names, n=1, cutoff=SIMILARITY)
        if close:
            found[lower] = Suspect(word, close[0])
    return list(found.values())
