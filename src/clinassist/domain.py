"""Domain objects and errors. No I/O. Exception messages are codes and never contain PHI."""

from __future__ import annotations

from dataclasses import dataclass


class WorkflowError(RuntimeError):
    """An action was attempted out of order or without its prerequisites."""


class Quarantined(RuntimeError):
    """The input guard rejected the transcript; no model call was made."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class GenerationFailed(RuntimeError):
    """The note generator could not produce a valid note (loop, cap, bad output, timeout).

    `partial_output` is for debugging with synthetic data only. It is never part of the message
    and must not be logged for real consultations."""

    def __init__(self, reason: str, partial_output: str = "") -> None:
        super().__init__(reason)
        self.reason = reason
        self.partial_output = partial_output


@dataclass(frozen=True)
class GuardVerdict:
    quarantined: bool
    reason: str = ""
    clean_text: str = ""


@dataclass(frozen=True)
class SoapNote:
    subjective: str = ""
    objective: str = ""
    assessment: str = ""
    plan: str = ""


@dataclass(frozen=True)
class AiSuggestion:
    """A model-generated diagnosis suggestion. Ordering only; not a calibrated confidence."""

    diagnosis: str
    rationale: str
    management: str
    rank: int


@dataclass(frozen=True)
class Draft:
    """Model (or manual) output. The model's assessment is kept apart from the clinician's."""

    subjective: str = ""
    objective: str = ""
    plan: str = ""
    ai_assessment: str = ""
    suggestions: tuple[AiSuggestion, ...] = ()
    source: str = "model"  # "model" or "manual"
    flags: tuple[str, ...] = ()  # advisory checks for the clinician to look at; never blocking

    def clinician_scaffold(self) -> SoapNote:
        """Starting point for the clinician's note. The assessment is deliberately blank."""
        return SoapNote(self.subjective, self.objective, "", self.plan)


@dataclass(frozen=True)
class HistoryChecklist:
    """The clinician confirms each item before a note can be finalized."""

    allergies: bool = False
    medications: bool = False
    pertinent_negatives: bool = False

    @property
    def complete(self) -> bool:
        return self.allergies and self.medications and self.pertinent_negatives


@dataclass(frozen=True)
class SessionRecord:
    """What is stored: the approved transcript, the model draft and the clinician's note."""

    session_id: str
    transcript: str
    transcript_approved_by: str
    finalized_by: str
    draft: Draft
    final_note: SoapNote
    accepted_suggestions: tuple[int, ...]
    assessment_origin: str  # clinician_manual | clinician_edited | ai_text_accepted_verbatim
    checklist: HistoryChecklist
    generation_attempts: int
