"""In-process controller: the only path from audio to a stored note.

It enforces the clinician-in-the-loop rules as a state machine:

    IDLE -> RECORDING -> TRANSCRIBED -> APPROVED -> DRAFTED -> FINALIZED
      |                     ^
      +---------------------+   (typed transcript: no recording)
                              ^            |  ^        |
                              |            v  |        |
                              +------ GENERATION_FAILED +   (retry, or write the note manually)

FR-11  the model never runs before the clinician approves the transcript
FR-12  a session cannot be finalized without a drafted note
FR-13  generation is bounded; failure keeps the transcript and offers retry or manual entry
FR-14  the clinician's assessment is their own; the model's text is kept separate
FR-15  required history is confirmed before finalizing
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from enum import Enum, auto

from clinassist.domain import (
    Draft,
    GenerationFailed,
    HistoryChecklist,
    Quarantined,
    SessionRecord,
    SoapNote,
    WorkflowError,
)
from clinassist.ports import (
    Auditor,
    InputGuard,
    NoteGenerator,
    NullAuditor,
    Recorder,
    SessionStore,
    Transcriber,
)


# The stages a consultation can be in. Every action below first checks the current stage
# (`_require`), so the interface cannot skip a step, even by mistake.
class State(Enum):
    IDLE = auto()
    RECORDING = auto()
    TRANSCRIBED = auto()
    APPROVED = auto()
    DRAFTED = auto()
    GENERATION_FAILED = auto()
    FINALIZED = auto()


class ConsultationController:
    def __init__(
        self,
        recorder: Recorder,
        transcriber: Transcriber,
        guard: InputGuard,
        generator: NoteGenerator,
        store: SessionStore,
        auditor: Auditor | None = None,
        max_attempts: int = 2,
        id_factory: Callable[[], str] = lambda: uuid.uuid4().hex,
    ) -> None:
        # The controller is handed its parts instead of creating them. The real app passes the
        # microphone, Whisper, Ollama and the vault; the tests pass simple fakes, which is how
        # every rule here can be tested in seconds without any hardware or model.
        self._recorder, self._transcriber, self._guard = recorder, transcriber, guard
        self._generator, self._store = generator, store
        self._auditor = auditor or NullAuditor()
        # At most two model attempts per transcript, so a failing model cannot keep the
        # clinician waiting. After that, the note is written by hand.
        self._max_attempts = max_attempts
        self._id_factory = id_factory
        self._clear()

    # ----- read-only view for the interface -----
    # The interface can read these values but has no way to set them; only the workflow
    # methods below change the state.
    @property
    def state(self) -> State:
        return self._state

    @property
    def session_id(self) -> str | None:
        return self._session_id

    @property
    def transcript(self) -> str:
        return self._transcript

    @property
    def draft(self) -> Draft | None:
        return self._draft

    @property
    def attempts(self) -> int:
        return self._attempts

    # ----- workflow -----
    def start_recording(self) -> None:
        self._require(State.IDLE)
        # A new random id for this consultation; it links the stored record and audit entries.
        self._session_id = self._id_factory()
        self._recorder.start()
        self._state = State.RECORDING
        self._audit("recording_started")

    def stop_recording(self) -> str:
        self._require(State.RECORDING)
        # Stop the microphone and turn the audio into text. The audio itself is not kept here.
        audio = self._recorder.stop()
        try:
            self._transcript = self._transcriber.transcribe(audio)
        except Exception:
            # The microphone is already off, so staying in RECORDING would leave the clinician
            # stuck. Move on with an empty transcript they can type or discard, and re-raise
            # so the screen can say what went wrong.
            self._transcript = ""
            self._state = State.TRANSCRIBED
            self._audit("transcription_failed")
            raise
        self._state = State.TRANSCRIBED
        self._audit("transcribed")
        return self._transcript

    def start_typed_transcript(self) -> None:
        """Start a consultation without the microphone: the clinician types the transcript.

        Useful when recording is not wanted (the patient declines, the room is noisy) or the
        microphone is not working. It goes straight to the transcript step with an empty text,
        so every rule after that is the same as for speech: the typed text must be approved
        (FR-11) and is screened by the input guard before the model sees it."""
        self._require(State.IDLE)
        self._session_id = self._id_factory()
        self._transcript = ""
        self._state = State.TRANSCRIBED
        self._audit("typed_transcript_started")

    def approve_transcript(self, edited_text: str, clinician_id: str) -> None:
        """Gate 1 (FR-11): only approved text can ever reach the model."""
        self._require(State.TRANSCRIBED)
        if not edited_text.strip():
            raise WorkflowError("empty_transcript")
        # The clinician's corrected text replaces the raw speech-to-text output, and we record
        # who approved it. From here on, this is the only text the model will ever see.
        self._transcript, self._approved_by = edited_text, clinician_id
        self._state = State.APPROVED
        self._audit("transcript_approved", clinician_id)

    def reopen_transcript(self) -> None:
        """Back to editing, for example when the draft exposed a transcription error."""
        self._require(State.APPROVED, State.DRAFTED, State.GENERATION_FAILED)
        # Any draft made from the old text is thrown away, because it may contain the error the
        # clinician is about to fix. The attempt count starts again for the corrected text.
        self._draft, self._attempts = None, 0
        self._state = State.TRANSCRIBED
        self._audit("transcript_reopened", self._approved_by)

    def generate_draft(self) -> Draft:
        """One attempt. On failure the state becomes GENERATION_FAILED and the error is raised,
        with the transcript preserved. Retries are limited to `max_attempts`."""
        self._require(State.APPROVED, State.GENERATION_FAILED)
        if self._attempts >= self._max_attempts:
            raise WorkflowError("attempts_exhausted")
        # Screen the approved text before the model sees it. Text that looks like an attempt to
        # give the model instructions is held back (quarantined) and no model call is made.
        verdict = self._guard.check(self._transcript)
        if verdict.quarantined:
            self._audit("quarantined", self._approved_by)
            raise Quarantined(verdict.reason)
        self._attempts += 1
        try:
            # The guard may return a cleaned copy (for example with phone numbers masked);
            # the model gets that copy, not the original.
            draft = self._generator.generate(verdict.clean_text or self._transcript, self._attempts)
        except GenerationFailed:
            # The model failed (it looped, timed out or wrote invalid output). The transcript is
            # kept and the clinician can retry or write the note by hand.
            self._state = State.GENERATION_FAILED
            self._audit("generation_failed", self._approved_by)
            raise
        self._draft, self._state = draft, State.DRAFTED
        self._audit("draft_generated", self._approved_by)
        return draft

    def start_manual_note(self) -> Draft:
        """Write the note without the model, for example after generation failed."""
        self._require(State.APPROVED, State.GENERATION_FAILED)
        self._draft = Draft(source="manual")
        self._state = State.DRAFTED
        self._audit("manual_note_started", self._approved_by)
        return self._draft

    def finalize(
        self,
        final_note: SoapNote,
        clinician_id: str,
        checklist: HistoryChecklist,
        accepted_suggestions: tuple[int, ...] = (),
    ) -> SessionRecord:
        """Gate 2 (FR-12, FR-14, FR-15). The record is saved before the state changes, so a
        storage failure leaves the session editable."""
        self._require(State.DRAFTED)
        assert self._draft is not None
        # FR-15: allergies, medicines and pertinent negatives must all be ticked. In testing,
        # every model note read by hand left at least one of these out.
        if not checklist.complete:
            raise WorkflowError("history_not_confirmed")
        # FR-14: the assessment must be written by the clinician; it cannot be left empty for
        # the model's text to fill.
        if not final_note.assessment.strip():
            raise WorkflowError("assessment_required")
        # Suggestions the clinician accepts are referred to by position in the draft's list.
        if any(not 0 <= i < len(self._draft.suggestions) for i in accepted_suggestions):
            raise WorkflowError("invalid_suggestion_index")

        # Record where the assessment came from, so a later reader can tell whether the
        # clinician wrote it, edited the model's text, or accepted the model's words unchanged.
        if self._draft.source == "manual":
            origin = "clinician_manual"
        elif final_note.assessment.strip() == self._draft.ai_assessment.strip():
            origin = "ai_text_accepted_verbatim"
        else:
            origin = "clinician_edited"

        record = SessionRecord(
            session_id=self._session_id or "",
            transcript=self._transcript,
            transcript_approved_by=self._approved_by,
            finalized_by=clinician_id,
            draft=self._draft,
            final_note=final_note,
            accepted_suggestions=tuple(accepted_suggestions),
            assessment_origin=origin,
            checklist=checklist,
            generation_attempts=self._attempts,
        )
        # Save first, then change the state. If saving fails, the exception leaves the state at
        # DRAFTED, so the clinician's note is still on screen and nothing is lost.
        self._store.save(record)
        self._state = State.FINALIZED
        self._audit("finalized", clinician_id)
        return record

    def discard(self) -> None:
        """Abandon the session from any state except FINALIZED."""
        if self._state is State.FINALIZED:
            raise WorkflowError("action_not_allowed_in_FINALIZED")
        if self._state is State.RECORDING:
            self._recorder.stop()  # release the microphone; the audio is dropped
        self._audit("session_discarded", self._approved_by or None)
        self._clear()

    def reset(self) -> None:
        """Start over after a finalized session."""
        self._require(State.FINALIZED)
        self._clear()

    # ----- internals -----
    def _clear(self) -> None:
        self._state = State.IDLE
        self._session_id: str | None = None
        self._transcript = ""
        self._approved_by = ""
        self._draft: Draft | None = None
        self._attempts = 0

    def _require(self, *allowed: State) -> None:
        # The guard on every action: refuse anything that is not allowed in the current stage.
        # The error is a code naming the stage, never anything from the consultation.
        if self._state not in allowed:
            raise WorkflowError(f"action_not_allowed_in_{self._state.name}")

    def _audit(self, event: str, user_id: str | None = None) -> None:
        # Audit entries carry only the event name, the session id and the user id. Transcript
        # and note text are never passed to the auditor.
        self._auditor.record(event, self._session_id or "", user_id or None)
