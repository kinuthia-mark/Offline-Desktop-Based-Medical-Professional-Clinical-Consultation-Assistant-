import json

from model_outputs import GOOD_LONG_632, GOOD_LONG_670

from clinassist.adapters.groundcheck import check_flags

CLEAN = {"subjective": "s", "objective": "o", "assessment": "a", "plan": "p"}


def test_clean_note_has_no_flags():
    assert check_flags(CLEAN, "Doctor: hello. Patient: cough.") == ()


def test_empty_sections_are_flagged():
    flags = check_flags({**CLEAN, "plan": "  "}, "x")
    assert "empty_section:plan" in flags


def test_pronoun_the_transcript_never_used_is_flagged():
    sections = {**CLEAN, "subjective": "She reports a cough."}
    assert "pronoun_not_in_transcript:she" in check_flags(sections, "Patient: I have a cough.")
    assert not any(f.startswith("pronoun") for f in check_flags(sections, "My wife, she cooks."))


def test_merged_words_after_punctuation_are_flagged_on_real_notes():
    for note in (GOOD_LONG_632, GOOD_LONG_670):  # "vomiting,vision" and "normal.Chest"
        sections = json.loads(note)
        assert "missing_space_after_punctuation" in check_flags(sections, "x")


def test_numbers_are_checked_only_when_the_transcript_has_digits():
    transcript = "Doctor: blood pressure 152/94, pulse 96."
    sections = {**CLEAN, "objective": "BP 152/95, pulse 96."}
    assert "number_not_in_transcript:152/95" in check_flags(sections, transcript)
    assert "number_not_in_transcript:96" not in check_flags(sections, transcript)
    # Speech written in words cannot be compared, so the check stays quiet.
    assert not any(
        f.startswith("number") for f in check_flags(sections, "blood pressure one fifty-two")
    )
