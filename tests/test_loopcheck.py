import json

import pytest
from model_outputs import GOOD_LONG_632, GOOD_LONG_670, GOOD_SHORT, LOOP_HEAD

from clinassist.adapters.loopcheck import find_repetition


@pytest.mark.parametrize("note", [GOOD_LONG_632, GOOD_LONG_670, GOOD_SHORT])
def test_real_notes_that_ended_normally_are_not_flagged(note):
    assert find_repetition(note) is None


def test_real_looping_output_is_detected_early():
    assert find_repetition(LOOP_HEAD) is not None


def test_detected_before_the_whole_note_is_written():
    # Streaming sees prefixes. The first time the loop shows should be well before the end.
    first = next(n for n in range(200, len(LOOP_HEAD), 20) if find_repetition(LOOP_HEAD[:n]))
    assert first < len(LOOP_HEAD)


@pytest.mark.parametrize("prefix", ["", '{"subjective": "'])
def test_three_identical_sentences_are_a_loop(prefix):
    sentence = "Patient reports no chest pain. "
    assert find_repetition(prefix + sentence * 3) is not None


def test_two_short_identical_sentences_are_not_a_loop():
    assert find_repetition("Patient reports no chest pain. Patient reports no chest pain. ") is None


def test_an_unfinished_last_sentence_is_not_counted():
    sentence = "Patient reports no chest pain. "
    assert find_repetition(sentence * 2 + "Patient reports no chest pain") is None
    assert find_repetition(sentence * 2 + "Patient reports no chest pain.") is not None


def test_a_loop_without_sentence_breaks_is_caught_by_the_tail_check():
    assert find_repetition("fever and chills " * 60) == "tail repeated"


def test_normal_prose_with_repeated_words_is_fine():
    text = json.dumps({"plan": "Take paracetamol. Drink fluids. Rest. Take paracetamol if needed."})
    assert find_repetition(text) is None
