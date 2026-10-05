"""Controller tests: the clinician-in-the-loop rules (FR-11 to FR-15) with fake adapters."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from clinassist.controller import ConsultationController, State
from clinassist.domain import (
    AiSuggestion,
    Draft,
    GenerationFailed,
    GuardVerdict,
    HistoryChecklist,
    Quarantined,
    SoapNote,
    WorkflowError,
)

SECRET = "SECRET-PHI-4471"
FULL = HistoryChecklist(True, True, True)
NOTE = SoapNote("s", "o", "Clinician assessment", "p")


class FakeRecorder:
    def __init__(self) -> None:
        self.starts = self.stops = 0

    def start(self) -> None:
        self.starts += 1

    def stop(self) -> bytes:
        self.stops += 1
        return b"pcm"


class FakeASR:
    def transcribe(self, audio: bytes) -> str:
        return f"raw transcript {SECRET}"


class FakeGuard:
    def __init__(self) -> None:
        self.quarantine = False
        self.seen: list[str] = []

    def check(self, text: str) -> GuardVerdict:
        self.seen.append(text)
        if self.quarantine:
            return GuardVerdict(True, reason="prompt_injection_suspected")
        return GuardVerdict(False, clean_text=f"[clean] {text}")


class FakeGenerator:
    def __init__(self) -> None:
        self.fail_times = 0
        self.attempts: list[int] = []
        self.texts: list[str] = []
        self.draft = Draft("s", "o", "p", ai_assessment="Possible viral illness.")

    def generate(self, text: str, attempt: int) -> Draft:
        self.attempts.append(attempt)
        self.texts.append(text)
        if len(self.attempts) <= self.fail_times:
            raise GenerationFailed("timeout")
        return self.draft


class FakeStore:
    def __init__(self) -> None:
        self.saved: list = []
        self.fail = False

    def save(self, record) -> None:
        if self.fail:
            raise RuntimeError("disk_full")
        self.saved.append(record)


class FakeAuditor:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, str | None]] = []

    def record(self, event: str, session_id: str, user_id: str | None) -> None:
        self.events.append((event, session_id, user_id))

    @property
    def names(self) -> list[str]:
        return [e[0] for e in self.events]


@dataclass
class Rig:
    recorder: FakeRecorder = field(default_factory=FakeRecorder)
    guard: FakeGuard = field(default_factory=FakeGuard)
    generator: FakeGenerator = field(default_factory=FakeGenerator)
    store: FakeStore = field(default_factory=FakeStore)
    auditor: FakeAuditor = field(default_factory=FakeAuditor)
    controller: ConsultationController = field(init=False)

    def __post_init__(self) -> None:
        self.controller = self.build()

    def build(self, **kwargs) -> ConsultationController:
        return ConsultationController(
            self.recorder, FakeASR(), self.guard, self.generator, self.store, self.auditor, **kwargs
        )


def to_transcribed(c: ConsultationController) -> None:
    c.start_recording()
    c.stop_recording()


def to_approved(c: ConsultationController) -> None:
    to_transcribed(c)
    c.approve_transcript(f"edited {SECRET}", "dr1")


def to_drafted(c: ConsultationController) -> Draft:
    to_approved(c)
    return c.generate_draft()


def to_finalized(c: ConsultationController) -> None:
    to_drafted(c)
    c.finalize(NOTE, "dr1", FULL)


# ---------- FR-11: the model only ever sees approved text ----------


def test_model_never_runs_before_transcript_is_approved():
    rig = Rig()
    to_transcribed(rig.controller)
    with pytest.raises(WorkflowError):
        rig.controller.generate_draft()
    assert rig.generator.attempts == [] and rig.guard.seen == []


def test_guard_and_model_receive_the_edited_text_not_the_raw_transcript():
    rig = Rig()
    to_drafted(rig.controller)
    assert rig.guard.seen == [f"edited {SECRET}"]
    assert rig.generator.texts == [f"[clean] edited {SECRET}"]


def test_empty_transcript_cannot_be_approved():
    rig = Rig()
    to_transcribed(rig.controller)
    with pytest.raises(WorkflowError, match="empty_transcript"):
        rig.controller.approve_transcript("   ", "dr1")
    assert rig.controller.state is State.TRANSCRIBED


def test_quarantine_blocks_the_model_and_keeps_the_session_usable():
    rig = Rig()
    to_approved(rig.controller)
    rig.guard.quarantine = True
    with pytest.raises(Quarantined):
        rig.controller.generate_draft()
    assert rig.generator.attempts == []
    assert rig.controller.state is State.APPROVED and rig.controller.attempts == 0
    assert "quarantined" in rig.auditor.names


# ---------- order of actions ----------

ILLEGAL = [
    ("idle", lambda c: c.stop_recording()),
    ("idle", lambda c: c.approve_transcript("x", "dr1")),
    ("idle", lambda c: c.generate_draft()),
    ("idle", lambda c: c.finalize(NOTE, "dr1", FULL)),
    ("recording", lambda c: c.start_recording()),
    ("recording", lambda c: c.generate_draft()),
    ("transcribed", lambda c: c.start_recording()),
    ("transcribed", lambda c: c.finalize(NOTE, "dr1", FULL)),
    ("approved", lambda c: c.finalize(NOTE, "dr1", FULL)),
    ("approved", lambda c: c.approve_transcript("x", "dr1")),
    ("drafted", lambda c: c.generate_draft()),
    ("drafted", lambda c: c.approve_transcript("x", "dr1")),
    ("finalized", lambda c: c.generate_draft()),
    ("finalized", lambda c: c.finalize(NOTE, "dr1", FULL)),
    ("finalized", lambda c: c.discard()),
]
SETUP = {
    "idle": lambda c: None,
    "recording": lambda c: c.start_recording(),
    "transcribed": to_transcribed,
    "approved": to_approved,
    "drafted": to_drafted,
    "finalized": to_finalized,
}


@pytest.mark.parametrize(("state_name", "action"), ILLEGAL)
def test_out_of_order_actions_are_refused_and_change_nothing(state_name, action):
    rig = Rig()
    SETUP[state_name](rig.controller)
    before = rig.controller.state
    with pytest.raises(WorkflowError):
        action(rig.controller)
    assert rig.controller.state is before


# ---------- FR-12: finalizing needs a drafted note ----------


def test_finalize_stores_model_draft_and_clinician_note_separately():
    rig = Rig()
    to_drafted(rig.controller)
    record = rig.controller.finalize(NOTE, "dr2", FULL)
    assert rig.controller.state is State.FINALIZED
    assert rig.store.saved == [record]
    assert record.draft.ai_assessment == "Possible viral illness."
    assert record.final_note.assessment == "Clinician assessment"
    assert record.transcript_approved_by == "dr1" and record.finalized_by == "dr2"


def test_storage_failure_keeps_the_session_editable():
    rig = Rig()
    to_drafted(rig.controller)
    rig.store.fail = True
    with pytest.raises(RuntimeError):
        rig.controller.finalize(NOTE, "dr1", FULL)
    assert rig.controller.state is State.DRAFTED
    assert "finalized" not in rig.auditor.names
    rig.store.fail = False
    rig.controller.finalize(NOTE, "dr1", FULL)
    assert rig.controller.state is State.FINALIZED


# ---------- FR-13: bounded generation with a visible failure state ----------


def test_generation_failure_keeps_transcript_and_allows_retry():
    rig = Rig()
    rig.generator.fail_times = 1
    to_approved(rig.controller)
    with pytest.raises(GenerationFailed):
        rig.controller.generate_draft()
    assert rig.controller.state is State.GENERATION_FAILED
    assert rig.controller.transcript == f"edited {SECRET}"
    rig.controller.generate_draft()
    assert rig.generator.attempts == [1, 2]  # the generator can switch settings on attempt 2
    assert rig.controller.state is State.DRAFTED


def test_retries_are_limited_then_only_manual_entry_remains():
    rig = Rig()
    rig.generator.fail_times = 99
    to_approved(rig.controller)
    for _ in range(2):
        with pytest.raises(GenerationFailed):
            rig.controller.generate_draft()
    with pytest.raises(WorkflowError, match="attempts_exhausted"):
        rig.controller.generate_draft()
    assert rig.generator.attempts == [1, 2]
    manual = rig.controller.start_manual_note()
    assert manual.source == "manual" and rig.controller.state is State.DRAFTED


def test_manual_note_can_be_started_without_trying_the_model():
    rig = Rig()
    to_approved(rig.controller)
    rig.controller.start_manual_note()
    record = rig.controller.finalize(NOTE, "dr1", FULL)
    assert rig.generator.attempts == [] and record.assessment_origin == "clinician_manual"


def test_reopening_the_transcript_discards_the_draft_and_resets_attempts():
    rig = Rig()
    to_drafted(rig.controller)
    rig.controller.reopen_transcript()
    assert rig.controller.state is State.TRANSCRIBED
    assert rig.controller.draft is None and rig.controller.attempts == 0
    rig.controller.approve_transcript("corrected text", "dr1")
    rig.controller.generate_draft()
    assert rig.generator.attempts == [1, 1]


# ---------- FR-15: required history is confirmed ----------


@pytest.mark.parametrize(
    "checklist",
    [
        HistoryChecklist(False, True, True),
        HistoryChecklist(True, False, True),
        HistoryChecklist(True, True, False),
        HistoryChecklist(),
    ],
)
def test_every_history_item_must_be_confirmed(checklist):
    rig = Rig()
    to_drafted(rig.controller)
    with pytest.raises(WorkflowError, match="history_not_confirmed"):
        rig.controller.finalize(NOTE, "dr1", checklist)
    assert rig.controller.state is State.DRAFTED and rig.store.saved == []


# ---------- FR-14: the assessment is the clinician's ----------


def test_scaffold_leaves_the_assessment_blank():
    draft = Draft("s", "o", "p", ai_assessment="Possible viral illness.")
    assert draft.clinician_scaffold().assessment == ""


def test_clinician_must_write_an_assessment():
    rig = Rig()
    to_drafted(rig.controller)
    with pytest.raises(WorkflowError, match="assessment_required"):
        rig.controller.finalize(SoapNote("s", "o", "   ", "p"), "dr1", FULL)


@pytest.mark.parametrize(
    ("assessment", "expected"),
    [
        ("  Possible viral illness. ", "ai_text_accepted_verbatim"),
        ("Suspected malaria, awaiting test.", "clinician_edited"),
    ],
)
def test_assessment_origin_is_recorded(assessment, expected):
    rig = Rig()
    to_drafted(rig.controller)
    record = rig.controller.finalize(SoapNote("s", "o", assessment, "p"), "dr1", FULL)
    assert record.assessment_origin == expected


def test_accepted_suggestions_are_validated_and_stored():
    rig = Rig()
    rig.generator.draft = Draft(
        "s",
        "o",
        "p",
        ai_assessment="x",
        suggestions=(
            AiSuggestion("Malaria", "fever, chills", "test and treat", 1),
            AiSuggestion("Viral illness", "self-limiting", "fluids", 2),
        ),
    )
    to_drafted(rig.controller)
    for bad in [(2,), (-1,)]:
        with pytest.raises(WorkflowError, match="invalid_suggestion_index"):
            rig.controller.finalize(NOTE, "dr1", FULL, accepted_suggestions=bad)
    record = rig.controller.finalize(NOTE, "dr1", FULL, accepted_suggestions=(0, 1))
    assert record.accepted_suggestions == (0, 1)


# ---------- sessions, cleanup and privacy ----------


def test_discard_from_recording_releases_the_microphone():
    rig = Rig()
    rig.controller.start_recording()
    rig.controller.discard()
    assert rig.recorder.stops == 1
    assert rig.controller.state is State.IDLE and rig.controller.session_id is None


def test_discard_clears_the_transcript_and_draft():
    rig = Rig()
    to_drafted(rig.controller)
    rig.controller.discard()
    assert rig.controller.transcript == "" and rig.controller.draft is None


def test_reset_starts_a_new_session_with_a_new_id():
    ids = iter(["s1", "s2"])
    rig = Rig()
    rig.controller = rig.build(id_factory=lambda: next(ids))
    to_finalized(rig.controller)
    assert rig.controller.session_id == "s1"
    rig.controller.reset()
    rig.controller.start_recording()
    assert rig.controller.session_id == "s2"


def test_audit_trail_has_the_expected_events_and_no_clinical_text():
    rig = Rig()
    to_finalized(rig.controller)
    assert rig.auditor.names == [
        "recording_started",
        "transcribed",
        "transcript_approved",
        "draft_generated",
        "finalized",
    ]
    flat = repr(rig.auditor.events)
    assert SECRET not in flat and "Clinician assessment" not in flat


def test_error_messages_never_contain_transcript_text():
    rig = Rig()
    rig.generator.fail_times = 1
    to_approved(rig.controller)
    with pytest.raises(GenerationFailed) as failed:
        rig.controller.generate_draft()
    with pytest.raises(WorkflowError) as refused:
        rig.controller.finalize(NOTE, "dr1", FULL)
    assert SECRET not in str(failed.value) and SECRET not in str(refused.value)


def test_failed_transcription_does_not_leave_the_session_stuck():
    """The microphone is already stopped, so the session moves on with an empty transcript the
    clinician can type, and the failure is audited."""

    class BrokenASR:
        def transcribe(self, audio: bytes) -> str:
            raise RuntimeError("asr_failed")

    rig = Rig()
    c = ConsultationController(
        rig.recorder, BrokenASR(), rig.guard, rig.generator, rig.store, rig.auditor
    )
    c.start_recording()
    with pytest.raises(RuntimeError):
        c.stop_recording()
    assert c.state is State.TRANSCRIBED and c.transcript == ""
    assert "transcription_failed" in rig.auditor.names
    c.approve_transcript("Typed by the clinician.", "dr-a")
    assert c.state is State.APPROVED


# ----- typed transcript (no recording) -----
def test_typed_transcript_skips_the_microphone_but_not_the_approval_gate():
    """Typing replaces recording only. The model still runs only on approved, screened text."""
    rig = Rig()
    c = rig.controller
    c.start_typed_transcript()
    assert c.state is State.TRANSCRIBED and c.transcript == "" and c.session_id
    assert rig.recorder.starts == 0  # the microphone was never opened
    with pytest.raises(WorkflowError):
        c.generate_draft()  # FR-11: not before approval
    with pytest.raises(WorkflowError):
        c.approve_transcript("   ", "dr1")  # nothing typed yet
    c.approve_transcript(f"Doctor: typed {SECRET}", "dr1")
    c.generate_draft()
    assert rig.guard.seen == [f"Doctor: typed {SECRET}"]  # screened like spoken text
    c.finalize(NOTE, "dr1", FULL)
    assert rig.store.saved[0].transcript == f"Doctor: typed {SECRET}"
    assert rig.auditor.names[0] == "typed_transcript_started"
    assert SECRET not in repr(rig.auditor.events)


def test_typed_transcript_only_starts_a_new_consultation():
    rig = Rig()
    rig.controller.start_recording()
    with pytest.raises(WorkflowError):
        rig.controller.start_typed_transcript()
