"""Scoring against clinician-written notes from public datasets (ADR-016)."""

from __future__ import annotations

import pytest

from clinassist.public_scoring import (
    clinician_impression,
    diagnosis_rank,
    expand,
    highlight_covered,
    rouge_l,
    rouge_n,
)

# The PriMock57 note for day 1, consultation 1, shortened (CC BY 4.0, Babylon Health).
CLINICIAN = """3/7 hx of diarrhea, mainly watery. No blood in stool. Associated LLQ pain - crampy.
Fever on first day, nil since.
PMH: Asthma
Imp: gastroenteritis
Plan: Conservative management - rest, push fluids, paracetamol if feverish."""


def test_rouge_matches_hand_calculation():
    # reference "the cat sat", hypothesis "the cat ran": 2 of 3 words shared both ways.
    assert rouge_n("the cat sat", "the cat ran", 1) == pytest.approx(2 / 3, abs=1e-4)
    # bigrams: "the cat" shared, 1 of 2 each way.
    assert rouge_n("the cat sat", "the cat ran", 2) == 0.5
    # longest common sequence "the cat": 2 of 3.
    assert rouge_l("the cat sat", "the cat ran") == pytest.approx(2 / 3, abs=1e-4)
    assert rouge_l("a b c d", "a x c y d") == pytest.approx(
        2 * (3 / 4) * (3 / 5) / (3 / 4 + 3 / 5), abs=1e-4
    )


def test_rouge_edge_cases():
    assert rouge_n("", "anything", 1) == 0.0
    assert rouge_l("same words here", "same words here") == 1.0


def test_clinical_shorthand_is_spelled_out():
    text = expand("3/7 hx of LLQ pain, SOB on exertion, 2/52 of cough, nil else")
    assert "3 days history of left lower quadrant pain" in text
    assert "shortness of breath" in text and "2 weeks" in text and "no else" in text


@pytest.mark.parametrize(
    ("highlight", "covered"),
    [
        ("3/7 hx of diarrhea", True),  # "three days of diarrhoea" in other spelling
        ("LLQ pain", True),
        ("Fever", True),
        ("Conservative management", False),
    ],
)
def test_highlights_are_matched_after_shorthand_and_spelling(highlight, covered):
    note = (
        "The patient reports diarrhoea for 3 days and left lower quadrant pain with a fever. "
        "Advised rest and fluids."
    )
    assert highlight_covered(highlight, note) is covered


def test_the_clinicians_impression_is_found():
    assert clinician_impression(CLINICIAN) == "gastroenteritis"
    assert clinician_impression("Impression - viral URTI\nPlan: rest") == "viral URTI"
    assert clinician_impression("no impression line") == ""


@pytest.mark.parametrize(
    ("reference", "suggestions", "rank"),
    [
        ("gastroenteritis", ["Viral gastroenteritis", "Food poisoning"], 1),
        ("likely UTI", ["Pyelonephritis", "Urinary tract infection"], 2),
        ("viral URTI", ["Upper respiratory tract infection"], 1),
        ("gastroenteritis", ["Appendicitis", "Dehydration"], None),
        ("", ["anything"], None),
    ],
)
def test_diagnosis_rank(reference, suggestions, rank):
    assert diagnosis_rank(reference, suggestions) == rank


def test_fillers_are_dropped_before_the_word_error_rate():
    from clinassist.public_scoring import drop_fillers

    assert drop_fillers("Um, so, uh, how long? Erm. Three days.") == "so, how long? Three days."


def test_spoken_punctuation_is_removed_for_the_second_word_error_rate():
    from clinassist.public_scoring import drop_dictated_punctuation

    heard = "in older people, coma, in women, full stop. Take it with food, period."
    assert drop_dictated_punctuation(heard) == "in older people, in women, Take it with food,"


@pytest.mark.parametrize(
    ("note", "diagnoses"),
    [
        ("PMH: none\nImp: gastroenteritis\nPlan: fluids", ["gastroenteritis"]),
        ("DDx - MI, PE, GORD\nPlan - called ambulance", ["MI", "PE", "GORD"]),
        ("DDx ??hypothyroid?\nPlans : bloods", ["hypothyroid"]),
        ("Plan: stemetil. Most likely disgnosis is labrynthitis", ["labrynthitis"]),
        ("We are suspecting an anaphylactic reaction", ["anaphylactic reaction"]),
        ("Likely migraine however need to consider more serious differentials", ["migraine"]),
        ("Looks well. Expect to improve in 5 days.", []),
        ("Unlikely to be pregnant. Likely migraine however see today", ["migraine"]),
        ("Imp: Bell's Palsy- need to rule out any other focal neurology", ["Bell's Palsy"]),
        (
            "Imp: insect bite reaction, no evidence of acute anaphylactic reaction, cellulitis",
            ["insect bite reaction", "cellulitis"],
        ),
    ],
)
def test_the_clinicians_diagnoses_are_read_in_their_different_forms(note, diagnoses):
    from clinassist.public_scoring import clinician_diagnoses

    assert clinician_diagnoses(note) == diagnoses


def test_any_listed_diagnosis_counts():
    assert diagnosis_rank(["MI", "PE", "GORD"], ["Pulmonary embolism", "Pleurisy"]) == 1
    assert diagnosis_rank(["MI", "PE", "GORD"], ["Pleurisy", "Costochondritis"]) is None
    assert diagnosis_rank(["MI", "PE", "GORD"], ["Costochondritis", "GORD"]) == 2
