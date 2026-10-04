"""Scoring a drafted note against a scripted consultation's key facts (FR-05, NFR-03, ADR-011).

Each scenario in eval/scenarios/ has a script (what is said) and a JSON file of what a correct
note must and must not contain:

    facts      things the note must state, each with the SOAP section it belongs in. A fact is a
               list of groups; every group must match, and a group matches if any of its phrases
               appears. Example: [["nitrofurantoin"], ["100 mg"]].
    negatives  things the patient denied ("no cough"). The note may leave them out; if it
               mentions one in the history or examination, it must be as a negative. A mention
               there without "no", "denies", "without" and so on is counted as a contradiction.
               The plan is not checked, since "come back if there is blood" is correct advice.
    traps      things a careless note might state that were never said: a relative's illness as
               the patient's, a test the doctor decided against, a diagnosis nobody made. A trap
               is triggered when its term appears in a clause that is not negated and that has
               none of the trap's "unless" words (for example "brother" for "smokes"). An
               "exact" trap is triggered by the phrase itself, such as "no blurred vision"
               when the patient described blurred vision.

Text is normalised before matching: lower case, numbers as digits, British and American spelling
treated as the same (clinassist.metrics). Every triggered trap and contradiction is reported with
the clause that triggered it, because these are text rules and a person should confirm them.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from clinassist.metrics import normalize

SECTIONS = ("subjective", "objective", "assessment", "plan")
# Words that negate what follows in the same clause.
_NEGATION = {
    "no", "not", "denies", "denied", "without", "negative", "nil", "none", "never", "absent",
    "neither", "nor", "free",
}  # fmt: skip
_CONDITIONAL = {"if", "unless", "should", "whether"}
# Phrases meaning "missing from the note", which must not count as a negation.
_UNSTATED = re.compile(r"\b(not stated|not mentioned|not documented|not recorded|not known)\b")
# Clause boundaries: sentence ends, semicolons, and a turn such as "but". A colon is not one:
# "Allergies: none" is a single statement.
_CLAUSE = re.compile(r"[.;\n]|\bbut\b|\bhowever\b|\bwhereas\b")


# A direct question ("Any cough?", "Do I have TB?") states nothing, so it is removed before
# scoring. "?malaria", the shorthand for "query malaria", is kept: there the "?" follows a space.
_QUESTION = re.compile(r"[^.?!\n]*\w\?(?=\s|$)")


def drop_questions(text: str) -> str:
    return _QUESTION.sub(" ", text)


def norm(text: str) -> str:
    """The normalised form used on both sides of every comparison, padded with spaces so a
    phrase only matches whole words."""
    # "500mg" and "500 mg" must match each other, so digits and letters are split apart first.
    text = re.sub(r"(\d)([a-zA-Z])", r"\1 \2", text)
    text = re.sub(r"([a-zA-Z])(\d)", r"\1 \2", text)
    return " " + " ".join(normalize(text, numbers_as_digits=True, standard_spelling=True)) + " "


def _has(text_norm: str, phrase: str) -> bool:
    return norm(phrase) in text_norm


def _clauses(text: str) -> list[str]:
    text = _UNSTATED.sub(" unstated ", text.lower())
    return [c for c in _CLAUSE.split(text) if c.strip()]


def positive_mentions(text: str, terms: list[str], unless: list[str] = ()) -> list[str]:
    """Clauses where one of `terms` appears without a negation before it (or "none" after it)
    and without any of the `unless` words."""
    found = []
    for clause in _clauses(text):
        words = norm(clause).split()
        joined = " " + " ".join(words) + " "
        for term in terms:
            t = norm(term)
            if t not in joined:
                continue
            before = joined[: joined.index(t)].split()
            after = joined[joined.index(t) + len(t) :].split()[:3]
            # "if" and "unless" make the rest conditional: "come back if you get a fever" does not
            # say there is a fever.
            negated = any(w in _NEGATION or w in _CONDITIONAL for w in before) or any(
                w in ("none", "nil", "negative", "absent", "not") for w in after
            )
            excused = any(_has(joined, u) for u in unless)
            if not negated and not excused:
                found.append(clause.strip())
                break
    return found


# ----- scenarios -----
@dataclass(frozen=True)
class Fact:
    """`match`: groups of phrases, every group must match. `denied`: instead, these terms must be
    mentioned and every mention negated ("no allergies", "does not have any allergies")."""

    id: str
    section: str
    match: tuple[tuple[str, ...], ...]
    critical: bool = False
    denied: tuple[str, ...] = ()


@dataclass(frozen=True)
class Negative:
    id: str
    terms: tuple[str, ...]
    critical: bool = False
    sections: tuple[str, ...] = ("subjective", "objective")


@dataclass(frozen=True)
class Trap:
    id: str
    terms: tuple[str, ...]
    unless: tuple[str, ...] = ()
    why: str = ""
    exact: bool = False


@dataclass(frozen=True)
class Scenario:
    id: str
    title: str
    script: Path
    facts: tuple[Fact, ...]
    negatives: tuple[Negative, ...]
    traps: tuple[Trap, ...]

    @classmethod
    def load(cls, path: Path) -> Scenario:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        for f in data["facts"]:
            if f["section"] not in SECTIONS:
                raise ValueError(f"bad section in {path.name}: {f['id']}")
        return cls(
            id=data["id"],
            title=data["title"],
            script=Path(path).with_name(data["script"]),
            facts=tuple(
                Fact(
                    f["id"],
                    f["section"],
                    tuple(tuple(g) for g in f.get("match", [])),
                    f.get("critical", False),
                    tuple(f.get("denied", [])),
                )
                for f in data["facts"]
            ),
            negatives=tuple(
                Negative(n["id"], tuple(n["terms"]), n.get("critical", False))
                for n in data.get("negatives", [])
            ),
            traps=tuple(
                Trap(
                    t["id"],
                    tuple(t["terms"]),
                    tuple(t.get("unless", [])),
                    t.get("why", ""),
                    t.get("exact", False),
                )
                for t in data.get("traps", [])
            ),
        )


def load_all(folder: Path) -> list[Scenario]:
    return [Scenario.load(p) for p in sorted(Path(folder).glob("*.json"))]


# ----- scoring -----
@dataclass
class Score:
    facts_found: list[str] = field(default_factory=list)
    facts_missed: list[str] = field(default_factory=list)
    critical_missed: list[str] = field(default_factory=list)
    wrong_section: list[str] = field(default_factory=list)
    contradictions: dict[str, list[str]] = field(default_factory=dict)  # negative id -> clauses
    traps: dict[str, list[str]] = field(default_factory=dict)  # trap id -> clauses
    facts_total: int = 0
    critical_total: int = 0

    @property
    def recall(self) -> float:
        return len(self.facts_found) / self.facts_total if self.facts_total else 0.0

    @property
    def critical_recall(self) -> float:
        if not self.critical_total:
            return 1.0
        return (self.critical_total - len(self.critical_missed)) / self.critical_total


def _fact_in(text_norm: str, fact: Fact, raw: str = "") -> bool:
    if fact.denied:
        mentioned = any(_has(text_norm, term) for term in fact.denied)
        return mentioned and not positive_mentions(raw, list(fact.denied))
    return all(any(_has(text_norm, phrase) for phrase in group) for group in fact.match)


def score_note(scenario: Scenario, sections: dict[str, str]) -> Score:
    """`sections` maps subjective/objective/assessment/plan to the note's text."""
    sections = {k: drop_questions(v) for k, v in sections.items()}
    whole = norm(" ".join(sections.get(s, "") for s in SECTIONS))
    s = Score(facts_total=len(scenario.facts))
    for fact in scenario.facts:
        if fact.critical:
            s.critical_total += 1
        raw_all = " . ".join(sections.get(x, "") for x in SECTIONS)
        if _fact_in(whole, fact, raw_all):
            s.facts_found.append(fact.id)
            own = sections.get(fact.section, "")
            if not _fact_in(norm(own), fact, own):
                s.wrong_section.append(fact.id)
        else:
            s.facts_missed.append(fact.id)
            if fact.critical:
                s.critical_missed.append(fact.id)
    text = " . ".join(sections.get(x, "") for x in SECTIONS)
    for neg in scenario.negatives:
        history = " . ".join(sections.get(x, "") for x in neg.sections)
        clauses = positive_mentions(history, list(neg.terms))
        if clauses:
            s.contradictions[neg.id] = clauses
    for trap in scenario.traps:
        if trap.exact:
            clauses = [
                c.strip() for c in _clauses(text) if any(_has(norm(c), p) for p in trap.terms)
            ]
        else:
            clauses = positive_mentions(text, list(trap.terms), list(trap.unless))
        if clauses:
            s.traps[trap.id] = clauses
    return s
