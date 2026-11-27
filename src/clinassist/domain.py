"""Domain objects and errors. No I/O. Exception messages are codes and never contain PHI."""

# This file holds the plain data objects the whole app passes around (notes, drafts, the saved
# record) and the error types. It has no code that touches files, the network or the screen,
# so every other file can import it safely. The controller, the model code and the vault all
# share these same shapes.
# Lets the type hints refer to classes defined later in the file, without quotes.
from __future__ import annotations

# dataclass writes the boring parts (init, equality) for classes that just hold values.
from dataclasses import dataclass

# The three kinds of error the workflow can raise. Each carries a short code (for example
# "history_not_confirmed"), so the interface can show a clear message and nothing from the
# consultation ever ends up in an error text or a log.


# Raised when a step is taken out of order or a rule is not met, for example a missing tick.
class WorkflowError(RuntimeError):
    """An action was attempted out of order or without its prerequisites."""


# Raised when the input guard holds the text back. No model call is made.
class Quarantined(RuntimeError):
    """The input guard rejected the transcript; no model call was made."""

    # Keeps the reason code on the object so the screen can read it.
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# Raised when the model fails to give a usable note. The clinician can retry or write by hand.
class GenerationFailed(RuntimeError):
    """The note generator could not produce a valid note (loop, cap, bad output, timeout).

    `partial_output` is for debugging with synthetic data only. It is never part of the message
    and must not be logged for real consultations."""

    # partial_output is kept only for debugging with made-up data. It is never put in the message.
    def __init__(self, reason: str, partial_output: str = "") -> None:
        super().__init__(reason)
        self.reason = reason
        self.partial_output = partial_output


# The objects below are "frozen": once made they cannot be changed, only replaced. That stops
# one part of the program from quietly altering a note another part is relying on.


# The two roles. The system administrator runs the system for the facility: accounts, backups,
# model updates, offline protection, the audit log, and the facility's reports. Only clinicians
# see consultation notes. The stored code stays "admin"; people see the job title.
# The two role codes stored in the database.
CLINICIAN, ADMIN = "clinician", "admin"
# All valid roles in one tuple, so a role can be checked with `in`.
ROLES = (CLINICIAN, ADMIN)
# Maps the stored code to the name shown on screen.
ROLE_LABELS = {CLINICIAN: "Clinician", ADMIN: "System Administrator"}


# frozen=True makes the object read-only after it is made.
@dataclass(frozen=True)
class GuardVerdict:
    # The input check's answer: hold the text back (quarantined) or pass on a cleaned copy.
    quarantined: bool
    reason: str = ""
    clean_text: str = ""
    # What was hidden before the model saw the text, as "kind:count" (for example
    # "phone_number:1"), so the interface can tell the clinician. Never the values themselves.
    masked: tuple[str, ...] = ()


# The note as the clinician finally writes it.
@dataclass(frozen=True)
class SoapNote:
    # The clinician's final note in the standard four parts.
    subjective: str = ""
    objective: str = ""
    assessment: str = ""
    plan: str = ""


# One possible diagnosis from the model. It sits beside the note and is never part of it.
@dataclass(frozen=True)
class AiSuggestion:
    """A model-generated diagnosis suggestion. Ordering only; not a calibrated confidence."""

    diagnosis: str
    rationale: str
    management: str
    rank: int


# What the model (or the clinician, for a manual note) produced before the clinician edits.
@dataclass(frozen=True)
class Draft:
    """Model (or manual) output. The model's assessment is kept apart from the clinician's."""

    subjective: str = ""
    objective: str = ""
    plan: str = ""
    # Named ai_assessment, not assessment, so it can never be mistaken for the clinician's own.
    ai_assessment: str = ""
    suggestions: tuple[AiSuggestion, ...] = ()
    source: str = "model"  # "model" or "manual"
    flags: tuple[str, ...] = ()  # advisory checks for the clinician to look at; never blocking

    # A property is read like a field (draft.has_ai_assessment) but is worked out each time.
    @property
    def has_ai_assessment(self) -> bool:
        """Whether the model wrote an assessment. It is told to write 'not stated' when the
        clinician gave no diagnosis, which counts as none."""
        stated = self.ai_assessment.strip()
        # True only if there is text and it is not just 'not stated' (ignoring a final full stop).
        return bool(stated) and stated.lower().rstrip(".") != "not stated"

    # Builds the starting note the clinician edits on the review screen.
    def clinician_scaffold(self) -> SoapNote:
        """Starting point for the clinician's note. The assessment is deliberately blank."""
        # Subjective, objective and plan are copied in for the clinician to edit. The
        # assessment box starts empty so the clinician forms their own view first.
        return SoapNote(self.subjective, self.objective, "", self.plan)


# The three history checks the clinician must tick at gate 2.
@dataclass(frozen=True)
class HistoryChecklist:
    """The clinician confirms each item before a note can be finalized."""

    allergies: bool = False
    medications: bool = False
    pertinent_negatives: bool = False

    # A property: true only when every check is ticked.
    @property
    def complete(self) -> bool:
        # All three must be ticked; two out of three is not enough.
        return self.allergies and self.medications and self.pertinent_negatives


# The one thing saved in the vault for a finished consultation.
@dataclass(frozen=True)
class SessionRecord:
    """What is stored: the approved transcript, the model draft and the clinician's note."""

    session_id: str
    transcript: str
    # Who approved the transcript and who finalized the note; usually the same clinician.
    transcript_approved_by: str
    finalized_by: str
    # The model's draft and the clinician's final note are both kept, side by side, so it is
    # always possible to see what the model wrote and what the clinician changed.
    draft: Draft
    final_note: SoapNote
    accepted_suggestions: tuple[int, ...]
    # Says whether the assessment is the clinician's or the model's, so a reader can tell.
    assessment_origin: str  # clinician_manual | clinician_edited | ai_text_accepted_verbatim
    checklist: HistoryChecklist
    generation_attempts: int
    # Which models produced the record, so a later reader can tell which version wrote which
    # note even after an update (FR-10b). Empty when not used: a typed transcript has no speech
    # model, and a note written by hand has no language model.
    asr_model: str = ""
    model_version: str = ""
    # The speech model's language and its confidence hint (0 to 1), as shown at review.
    transcript_language: str = ""
    asr_confidence: float | None = None
