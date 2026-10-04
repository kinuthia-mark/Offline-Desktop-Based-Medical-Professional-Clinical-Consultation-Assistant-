"""Keeps the requirement and amendment documents consistent with the proposal copy.

The amendment log is used for the one final update of the approved proposal, so a wrong section
number there is a real cost. These checks catch references to sections that do not exist, broken
tables and duplicate identifiers. They cannot check that a section says what an entry claims.
Checks that read the proposal text (docs/proposal/PROPOSAL.md) are skipped when that file is not
present."""

import re
from pathlib import Path

import pytest

DOCS = Path(__file__).resolve().parents[1] / "docs"
PROPOSAL_PATH = DOCS / "proposal" / "PROPOSAL.md"
PROPOSAL = PROPOSAL_PATH.read_text(encoding="utf-8") if PROPOSAL_PATH.exists() else ""
needs_proposal = pytest.mark.skipif(not PROPOSAL, reason="proposal text not present")
AMENDMENTS = (DOCS / "AMENDMENTS.md").read_text(encoding="utf-8").splitlines()
TRACE = (DOCS / "traceability.md").read_text(encoding="utf-8").splitlines()


def rows(lines, prefix):
    return [
        [c.strip() for c in line.strip().strip("|").split("|")]
        for line in lines
        if line.startswith(prefix)
    ]


def proposal_sections() -> set[str]:
    found = re.findall(r"^#{1,4} \**(\d+(?:\.\d+)*)[\s.]", PROPOSAL, flags=re.M)
    return set(found)


@needs_proposal
def test_the_proposal_copy_has_the_expected_structure():
    sections = proposal_sections()
    for expected in ("1.1", "1.7.2", "2.3.3", "3.2.5", "3.7", "4.2.1", "4.8", "4.9"):
        assert expected in sections
    for name in ("Abstract", "References", "Appendix 1"):
        assert name in PROPOSAL


@needs_proposal
def test_every_section_cited_in_the_amendment_log_exists_in_the_proposal():
    sections = proposal_sections()
    missing = []
    for amd in rows(AMENDMENTS, "| AMD-"):
        for ref in re.findall(r"\b\d+(?:\.\d+)+\b", amd[1]):
            if ref not in sections:
                missing.append((amd[0], ref))
    assert not missing, missing


def test_amendment_table_is_well_formed_with_unique_sequential_ids():
    entries = rows(AMENDMENTS, "| AMD-")
    assert entries and all(len(e) == 6 for e in entries)
    ids = [e[0] for e in entries]
    assert ids == [f"AMD-{n:02d}" for n in range(1, len(ids) + 1)]
    assert all(e[1] and e[2] and e[3] and e[4] for e in entries)


def test_traceability_ids_are_unique_and_complete():
    entries = rows(TRACE, "| FR-") + rows(TRACE, "| NFR-")
    assert entries and all(len(e) == 6 for e in entries)
    ids = [e[0] for e in entries]
    assert len(ids) == len(set(ids))
    for needed in ("FR-10a", "FR-10b", "FR-10c", "FR-10d", "FR-11", "FR-15", "NFR-07", "NFR-08"):
        assert needed in ids


def test_every_adr_file_is_named_in_order():
    names = sorted(p.name for p in (DOCS / "ADR").glob("[0-9][0-9][0-9]-*.md"))
    numbers = [int(n[:3]) for n in names]
    assert numbers == sorted(set(numbers))


@needs_proposal
def test_the_proposal_figures_exist():
    figures = re.findall(r"media/(image\d+\.\w+)", PROPOSAL)
    assert figures
    for name in figures:
        assert (DOCS / "proposal" / "media" / name).exists(), name
