"""The evaluation scorer and the scenario files (ADR-011)."""

from __future__ import annotations

from pathlib import Path

import pytest

from clinassist.evaluation import (
    SECTIONS,
    Fact,
    Negative,
    Scenario,
    Trap,
    drop_questions,
    load_all,
    norm,
    positive_mentions,
    score_note,
)

SCENARIOS = Path(__file__).resolve().parents[1] / "eval" / "scenarios"
ALL = load_all(SCENARIOS)

# Facts that a written note states plainly but the dialogue only implies, so they cannot be
# found in the raw script: "Any allergies? - No." and "I would like you to stop it".
DIALOGUE_ONLY = {("s01_fever", "no_allergies"), ("s02_hypertension_diabetes", "stop_ibuprofen")}


# ----- the scenario files -----
def test_there_are_eight_scenarios_with_scripts():
    assert len(ALL) == 8
    assert all(s.script.is_file() for s in ALL)


@pytest.mark.parametrize("scenario", ALL, ids=lambda s: s.id)
def test_each_scenario_is_well_formed(scenario):
    ids = [f.id for f in scenario.facts] + [n.id for n in scenario.negatives]
    ids += [t.id for t in scenario.traps]
    assert len(ids) == len(set(ids)), "duplicate ids"
    assert all(f.section in SECTIONS for f in scenario.facts)
    assert all((f.match and all(f.match)) or f.denied for f in scenario.facts)
    assert any(f.critical for f in scenario.facts)
    assert scenario.script.read_text(encoding="utf-8").startswith("# SYNTHETIC")


@pytest.mark.parametrize("scenario", ALL, ids=lambda s: s.id)
def test_the_script_itself_contains_every_fact_and_triggers_no_trap(scenario):
    """A fact the script cannot satisfy is badly written; a trap the script triggers is unfair."""
    text = scenario.script.read_text(encoding="utf-8")
    s = score_note(scenario, {x: text for x in SECTIONS})
    missed = {(scenario.id, m) for m in s.facts_missed}
    assert missed <= DIALOGUE_ONLY, missed - DIALOGUE_ONLY
    assert s.traps == {} and s.contradictions == {}


# ----- matching -----
def test_numbers_units_and_spelling_match_in_any_form():
    assert norm("500mg") == norm("500 mg") == norm("five hundred mg")
    assert norm("BP one fifty two over ninety four") == " bp 152 over 94 "
    assert norm("haemoglobin 10.1") == norm("hemoglobin 10.1")


@pytest.mark.parametrize("phrase, text", [("ors", "Doors closed."), ("pain", "Painful leg.")])
def test_a_phrase_matches_whole_words_only(phrase, text):
    """ "ORS" must not be found inside "doors", nor "pain" inside "painful"."""
    fact = Fact("x", "plan", ((phrase,),))
    s = score_note(Scenario("t", "t", Path("x"), (fact,), (), ()), {"plan": text})
    assert s.facts_missed == ["x"]


def test_every_group_of_a_fact_must_match():
    fact = Fact("dose", "plan", (("nitrofurantoin",), ("100 mg",)), critical=True)
    sc = Scenario("t", "t", Path("x"), (fact,), (), ())
    assert score_note(sc, {"plan": "Nitrofurantoin 100mg twice daily."}).facts_found == ["dose"]
    s = score_note(sc, {"plan": "Nitrofurantoin twice daily."})
    assert s.critical_missed == ["dose"] and s.critical_recall == 0.0


def test_fact_in_the_wrong_section_is_found_but_noted():
    fact = Fact("bp", "objective", (("118 76", "118 over 76"),))
    sc = Scenario("t", "t", Path("x"), (fact,), (), ())
    s = score_note(sc, {"subjective": "BP 118/76", "objective": "chest clear"})
    assert s.facts_found == ["bp"] and s.wrong_section == ["bp"]


# ----- negatives and traps -----
@pytest.mark.parametrize(
    "text",
    [
        "No cough.",
        "Denies cough or sore throat.",
        "Without cough.",
        "Cough: none.",
        "Cough not present.",
        "Return if a cough develops.",
    ],
)
def test_negated_or_conditional_mentions_are_not_positive(text):
    assert positive_mentions(text, ["cough"]) == []


@pytest.mark.parametrize("text", ["Patient reports cough.", "Cough for 3 days, worse at night."])
def test_plain_mentions_are_positive(text):
    assert positive_mentions(text, ["cough"])


def test_not_stated_is_not_a_negation():
    """ "Allergies: not stated" means missing, not denied."""
    assert positive_mentions("Allergies not stated.", ["allergies"])


def test_denied_fact_needs_a_mention_and_every_mention_negated():
    fact = Fact("no_allergies", "subjective", (), True, ("allergies", "allergy"))
    sc = Scenario("t", "t", Path("x"), (fact,), (), ())
    for ok in ("Allergies: none.", "Does not have any allergies.", "No medicines or allergies."):
        assert score_note(sc, {"subjective": ok}).facts_found == ["no_allergies"], ok
    for bad in ("Allergies: not stated.", "Fever for 3 days.", "Allergy to penicillin."):
        assert score_note(sc, {"subjective": bad}).facts_missed == ["no_allergies"], bad


def test_contradiction_is_reported_with_its_clause():
    neg = Negative("no_cough", ("cough",))
    sc = Scenario("t", "t", Path("x"), (), (neg,), ())
    s = score_note(sc, {"subjective": "Fever for 3 days. Productive cough at night."})
    assert s.contradictions == {"no_cough": ["productive cough at night"]}


def test_negatives_are_not_checked_in_the_plan():
    neg = Negative("no_blood", ("blood in stool",))
    sc = Scenario("t", "t", Path("x"), (), (neg,), ())
    s = score_note(sc, {"subjective": "No blood in stool.", "plan": "Blood in stool: return."})
    assert s.contradictions == {}


def test_trap_respects_unless_words():
    trap = Trap("smoker", ("smokes",), ("brother",))
    sc = Scenario("t", "t", Path("x"), (), (), (trap,))
    assert score_note(sc, {"subjective": "Brother smokes indoors."}).traps == {}
    assert score_note(sc, {"subjective": "Patient smokes 10 a day."}).traps == {
        "smoker": ["patient smokes 10 a day"]
    }


def test_exact_trap_fires_even_when_negated():
    trap = Trap("blur", ("no blurred vision",), exact=True)
    sc = Scenario("t", "t", Path("x"), (), (), (trap,))
    assert score_note(sc, {"subjective": "No blurred vision."}).traps


def test_questions_are_dropped_but_query_shorthand_is_kept():
    assert drop_questions("Any cough? No cough.").strip() == "No cough."
    assert "?malaria" in drop_questions("Fever ?malaria.")


def test_a_negation_at_the_end_of_a_list_covers_the_whole_list():
    """Found in the suggestions run: "chest pain, palpitations or shortness of breath are not
    present" was counted as a positive mention."""
    text = "Chest pain, palpitations or shortness of breath are not present."
    assert positive_mentions(text, ["chest pain"]) == []
    assert positive_mentions(text, ["palpitations"]) == []
    # A clause that does not end by negating is unaffected.
    assert positive_mentions("Chest pain for two days and getting worse.", ["chest pain"])
