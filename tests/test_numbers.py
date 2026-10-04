import pytest

from clinassist.adapters.numbers import find_numbers


def readings(text):
    singles, pairs = find_numbers(text)
    return [set(s.readings) for s in singles], [set(p.readings) for p in pairs]


@pytest.mark.parametrize(
    ("spoken", "expected"),
    [
        ("one fifty-two over ninety-four", ("152", "94")),
        ("one forty-eight over ninety-two", ("148", "92")),
        ("one eighteen over seventy-six", ("118", "76")),
        ("152 over 94", ("152", "94")),
        ("150/94", ("150", "94")),
    ],
)
def test_blood_pressure_pairs_are_found_in_words_and_digits(spoken, expected):
    _, pairs = readings(spoken)
    assert any(expected in p for p in pairs)


@pytest.mark.parametrize(
    ("spoken", "expected"),
    [
        ("eleven point two", "11.2"),
        ("thirty-eight point six", "38.6"),
        ("five hundred milligrams", "500"),
        ("one hundred and fifty two", "152"),
        ("seventy-eight", "78"),
        ("twelve", "12"),
        ("eighty two kilograms", "82"),
    ],
)
def test_spoken_numbers_have_the_right_reading(spoken, expected):
    singles, _ = readings(spoken)
    assert any(expected in s for s in singles)


def test_a_pair_needs_over_or_a_slash_between_neighbours():
    _, pairs = readings("152 and 94")
    assert pairs == []
    _, pairs = readings("blood pressure one fifty over ninety, then pulse seventy-eight")
    assert len(pairs) == 1


def test_a_range_is_two_numbers_and_not_a_pair():
    singles, pairs = readings("blood sugar 9-10")
    assert pairs == [] and [{"9"}, {"10"}] == singles


def test_ordinary_words_are_not_numbers():
    assert find_numbers("twice daily with food, once at night") == ([], [])
