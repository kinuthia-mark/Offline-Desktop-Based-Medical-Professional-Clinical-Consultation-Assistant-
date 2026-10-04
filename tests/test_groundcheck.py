import json
from pathlib import Path

import pytest
from model_outputs import (
    GOOD_LONG_632,
    GOOD_LONG_670,
    GOOD_SHORT,
    REAL_LONG_ATTEMPT2,
    REAL_SHORT_ATTEMPT1,
)

from clinassist.adapters import groundcheck
from clinassist.adapters.groundcheck import check_flags

TRANSCRIPTS = Path(__file__).resolve().parents[1] / "spikes" / "transcripts"
CLEAN = {"subjective": "s", "objective": "o", "assessment": "a", "plan": "p"}


def transcript(name):
    lines = (TRANSCRIPTS / name).read_text(encoding="utf-8").splitlines()
    return "\n".join(line for line in lines if not line.startswith("#")).strip()


SHORT = transcript("synthetic_consult_01.txt")
LONG = transcript("synthetic_consult_long.txt")


def test_clean_note_has_no_flags():
    assert check_flags(CLEAN, "Doctor: hello. Patient: cough.") == ()


def test_empty_sections_are_flagged():
    assert "empty_section:plan" in check_flags({**CLEAN, "plan": "  "}, "x")


def test_pronoun_the_transcript_never_used_is_flagged():
    sections = {**CLEAN, "subjective": "She reports a cough."}
    assert "pronoun_not_in_transcript:she" in check_flags(sections, "Patient: I have a cough.")
    assert not any(f.startswith("pronoun") for f in check_flags(sections, "My wife, she cooks."))


# ---------- real notes from the spike and from this branch ----------


@pytest.mark.parametrize(
    ("note", "word"),
    [
        (REAL_SHORT_ATTEMPT1, "whenpassing"),
        (REAL_LONG_ATTEMPT2, "tohypertension"),
        (GOOD_LONG_632, "lackof"),
        (GOOD_LONG_670, "healthand"),
        (GOOD_LONG_670, "gramin"),
    ],
)
def test_real_merged_words_are_found(note, word):
    transcript_text = LONG if note != REAL_SHORT_ATTEMPT1 else SHORT
    assert f"possible_merged_word:{word}" in check_flags(json.loads(note), transcript_text)


def test_punctuation_without_a_space_is_found_on_real_notes():
    for note in (GOOD_LONG_632, GOOD_LONG_670):  # "vomiting,vision" and "normal.Chest"
        assert "missing_space_after_punctuation" in check_flags(json.loads(note), LONG)


def test_drug_names_and_clinical_words_are_not_called_merged():
    text = "ibuprofen paracetamol amlodipine metformin glucometer ugali hyperglycemia neuropathy"
    flags = check_flags({**CLEAN, "plan": text}, "x")
    assert not any(f.startswith("possible_merged_word") for f in flags)


def test_words_the_clinician_said_are_trusted():
    # "healthand" would be called a merged word, unless the transcript itself contains it.
    note = {**CLEAN, "plan": "Review healthand safety."}
    assert "possible_merged_word:healthand" in check_flags(note, "Doctor: review safety.")
    assert check_flags(note, "Doctor: review healthand safety.") == ()


def test_the_real_long_note_is_flagged_for_its_real_errors_and_nothing_else():
    flags = check_flags(json.loads(REAL_LONG_ATTEMPT2), LONG)
    assert flags == (
        "pronoun_not_in_transcript:his",
        "possible_merged_word:tohypertension",
        "number_not_in_transcript:150/94",  # home BP was 150/90; the clinic reading was 152/94
    )


def test_real_short_notes():
    assert check_flags(json.loads(REAL_SHORT_ATTEMPT1), SHORT) == (
        "possible_merged_word:whenpassing",
    )
    assert check_flags(json.loads(GOOD_SHORT), SHORT) == ()


def test_list_numbering_is_not_mistaken_for_clinical_numbers():
    flags = check_flags(json.loads(GOOD_LONG_632), LONG)
    assert not any(f.startswith("number_not_in_transcript") for f in flags)


# ---------- numbers against a transcript written in digits ----------


def test_pairs_must_match_as_pairs_when_the_transcript_has_digits():
    transcript_text = "Doctor: blood pressure 152 over 94, pulse 96. Later 148 over 92."
    wrong = check_flags({**CLEAN, "objective": "BP 152/95, pulse 96."}, transcript_text)
    assert wrong == ("number_not_in_transcript:152/95",)  # reported once, as a pair
    ok = check_flags({**CLEAN, "objective": "BP 152/94, pulse 96."}, transcript_text)
    assert not any(f.startswith("number") for f in ok)
    swapped = check_flags({**CLEAN, "objective": "BP 152/92."}, transcript_text)
    assert "number_not_in_transcript:152/92" in swapped  # both numbers occur, but not together


def test_single_numbers_are_checked_too():
    flags = check_flags({**CLEAN, "plan": "Give 20 mg."}, "Doctor: give 10 mg.")
    assert "number_not_in_transcript:20" in flags


def test_number_checks_are_skipped_when_the_transcript_has_none():
    assert not any(
        f.startswith("number") for f in check_flags({**CLEAN, "plan": "Give 20 mg."}, "Give it.")
    )


def test_a_missing_dictionary_is_reported_not_hidden(monkeypatch):
    def unavailable():
        raise ImportError

    monkeypatch.setattr(groundcheck, "_spell", unavailable)
    assert "merged_word_check_unavailable" in check_flags(CLEAN, "x")
