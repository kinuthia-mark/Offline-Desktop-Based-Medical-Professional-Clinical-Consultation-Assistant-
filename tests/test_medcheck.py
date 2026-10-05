"""Medicine-name check (AMD-38, ADR-013)."""

from __future__ import annotations

from pathlib import Path

import pytest

from clinassist.evaluation import load_all
from clinassist.medcheck import suspect_medicines

SCENARIOS = Path(__file__).resolve().parents[1] / "eval" / "scenarios"


@pytest.mark.parametrize(
    "heard, meant",
    [
        ("Glendamycin", "clindamycin"),  # seen in evaluation
        ("Nitrofuranta", "nitrofurantoin"),  # seen in evaluation
        ("bechlametisone", "beclometasone"),  # seen in evaluation
        ("amlotyping", "amlodipine"),  # seen with Whisper base
        ("parasetamol", "paracetamol"),
    ],
)
def test_misheard_medicines_are_flagged_with_the_likely_name(heard, meant):
    found = suspect_medicines(f"Take {heard} twice a day.")
    assert [(s.word, s.meant) for s in found] == [(heard, meant)]


@pytest.mark.parametrize("scenario", load_all(SCENARIOS), ids=lambda s: s.id)
def test_no_false_alarm_on_correct_consultations(scenario):
    assert suspect_medicines(scenario.script.read_text(encoding="utf-8")) == []


def test_each_word_is_reported_once_and_known_names_are_not():
    text = "Glendamycin now, Glendamycin later, and paracetamol."
    assert [s.word for s in suspect_medicines(text)] == ["Glendamycin"]


def test_known_limit_a_real_english_word_is_not_flagged():
    """ "sulfur" for sulfa is a real word, so it is not flagged (ADR-013)."""
    assert suspect_medicines("allergic to sulfur drugs") == []


@pytest.mark.parametrize("word", ["beclomethasone", "statin", "Cotrimoxazole", "acetaminophen"])
def test_other_correct_spellings_and_drug_classes_are_not_flagged(word):
    """Two false alarms found on the evaluation notes: an American spelling and a drug class."""
    assert suspect_medicines(f"Consider {word} today.") == []
