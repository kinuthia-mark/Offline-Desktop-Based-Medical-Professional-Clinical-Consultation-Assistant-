"""The consultation workspace (FR-01, FR-03, FR-06, FR-13 to FR-15; wireframe Figure 4.8).

One screen, three panels, left to right in the order of a consultation:

    1. Consultation          type or paste the consultation (the main path); dictation (beta)
                             with elapsed time and level meter; discard
    2. Transcript            edit the speech-to-text output, then approve it (gate 1)
    3. Clinical output       the drafted note, the clinician's own assessment, the AI's text
                             kept apart and labelled, advisory flags, the history checklist,
                             and Finalize (gate 2)

The screen holds no rules of its own. It calls the controller and then redraws itself from the
controller's state, so a button can only be pressed when the controller would accept it anyway.
"""

# This file is the main screen of ClinAssist: the one the clinician uses for a consultation.
# It builds the three panels (consultation, transcript, note) and wires each button to the
# ConsultationController, which holds the real rules. After every action the screen asks the
# controller what state it is in and redraws, so the screen never decides anything itself.
from __future__ import annotations

# time is used for the elapsed clock; Callable is only for type hints.
import time
from collections.abc import Callable
from datetime import date

# Qt is the window toolkit (PySide6). QTimer runs code later or on repeat without freezing.
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

# State is the controller's list of stages (IDLE, RECORDING, ... FINALIZED).
from clinassist.controller import State
from clinassist.domain import Draft, HistoryChecklist, SoapNote
from clinassist.medcheck import suspect_medicines

# message_for turns an error code into a plain sentence for the clinician.
from clinassist.ui.messages import message_for

# tone and mark only set a colour or button style (see theme.py).
from clinassist.ui.theme import mark, tone

# run_in_background is the thread-pool helper; error_code reads the short code off an error.
from clinassist.ui.workers import error_code, run_in_background

AI_LABEL = "AI-generated. Not part of your note unless you copy it."
# Colours that stay readable on both light and dark Windows themes.
# Shown when the model leaves the diagnosis to the clinician, which the prompt asks it to do
# unless the clinician said one aloud (ADR-002).
NO_AI_ASSESSMENT = (
    "The model does not write a diagnosis into the note unless one was said aloud. "
    "Its possible diagnoses are on the Diagnostics tab."
)


def ai_impression(draft: Draft) -> str:
    """The text for the "Model's assessment" box.

    If the clinician said a diagnosis aloud, the model's assessment repeats it. If not, the
    note's assessment stays empty (the model must not put a diagnosis nobody made into the note,
    ADR-002), and the box shows the model's own impression from its suggestions instead, so the
    clinician can see what the AI thinks without it entering the note unless they copy it."""
    # The note's assessment is empty when no diagnosis was said, so the model's view is shown here.
    if draft.has_ai_assessment:
        return draft.ai_assessment.strip()
    if not draft.suggestions:
        return ""
    # top is the first (most likely) suggestion; others is the rest.
    top, others = draft.suggestions[0], draft.suggestions[1:]
    lines = [
        "AI impression (the clinician did not state a diagnosis):",
        f"Most likely: {top.diagnosis}. {top.rationale}".rstrip(),
    ]
    if others:
        # Join the other diagnoses into one sentence.
        lines.append("Also consider: " + "; ".join(s.diagnosis for s in others) + ".")
    if top.management.strip():
        lines.append(f"Suggested management: {top.management}".rstrip())
    return "\n".join(lines)


# Advisory flag codes in plain words, shown under the note.
FLAG_TEXT = {
    "empty_section": "Section left empty by the model",
    "pronoun_not_in_transcript": "Gendered word the transcript never used",
    "missing_space_after_punctuation": "Words may be run together",
    "possible_merged_word": "Possible merged words",
    "number_not_in_transcript": "Number not found in the transcript",
    "merged_word_check_unavailable": "Merged-word check unavailable",
}


def _text_box(placeholder: str, read_only: bool = False) -> QPlainTextEdit:
    # A small helper so every text box is built the same way.
    box = QPlainTextEdit()
    box.setPlaceholderText(placeholder)
    box.setReadOnly(read_only)
    return box


class ConsultationWorkspace(QWidget):
    """`services` comes from app.build(). `user_id()` names the clinician who is logged in.
    `before_action()` is called before every step; it raises if the login has expired."""

    def __init__(
        self,
        services,
        user_id: Callable[[], str],
        before_action: Callable[[], None] = lambda: None,
        confirm: Callable[[str], bool] | None = None,
    ) -> None:
        super().__init__()
        # Keep the objects the screen needs; the controller holds the real consultation state.
        self._services = services
        self._user_id = user_id
        self._before_action = before_action
        # If no custom confirm is given, use the Yes/No popup (self._ask).
        self._confirm = confirm or self._ask
        self.controller = services.new_controller()
        self._busy = ""  # what is running in the background, or "" when idle
        # Raised each time the consultation is abandoned, so a transcription or draft that was
        # still running for it is ignored when it finishes (see abandon()).
        self._generation = 0
        self._last_error = ""
        self._build()
        # The model reports how many pieces it has sent; the worker thread stores that number.
        services.progress.listener = self._on_progress_from_worker
        # Count of pieces received from the model so far, shown while drafting.
        self._pieces = 0
        # While recording, the meter and the clock are refreshed ten times a second.
        self._meter = QTimer(self)
        self._meter.setInterval(100)
        self._meter.timeout.connect(self._update_meter)
        # Draw the screen once so the buttons start in the right state.
        self.refresh()

    # ----- layout -----
    def _build(self) -> None:
        # Panel 1: session and audio
        # Every widget is created once here; refresh() later only changes what is enabled or shown.
        self.session_label = QLabel()
        self.date_label = QLabel(f"Date: {date.today().isoformat()}")
        self.status_label = QLabel()
        # The status says what to do next, so it wraps instead of being cut off in a narrow
        # panel or at a large text size (WCAG 1.4.10).
        self.status_label.setWordWrap(True)
        self.duration_label = QLabel("Duration: 00:00:00")
        self.level_bar = QProgressBar()
        self.level_bar.setRange(0, 100)
        self.level_bar.setFormat("Level")
        # The main path: the clinician types or pastes the consultation, which is fully under
        # their control. Dictation is offered beside it as a beta: speech recognition can mishear
        # words (14.6% of words wrong on real conversations, more with Kenyan accents), so it is
        # a convenience whose every word the clinician checks, not the main feature.
        self.type_button = QPushButton("Type or paste the consultation")
        self.start_button = QPushButton("Dictate (beta)")
        self.stop_button = QPushButton("Stop dictation")
        self.beta_note = QLabel(
            "Beta: dictation can mishear words. Check every word of the transcript before you "
            "approve it."
        )
        self.beta_note.setWordWrap(True)
        tone(self.beta_note, "quiet")
        self.discard_button = QPushButton("Discard consultation")
        self.new_button = QPushButton("New consultation")
        # Connect each button to the method that handles it.
        self.start_button.clicked.connect(self.start_recording)
        self.stop_button.clicked.connect(self.stop_recording)
        self.type_button.clicked.connect(self.type_transcript)
        self.discard_button.clicked.connect(self.discard)
        self.new_button.clicked.connect(self.new_consultation)
        audio = QGroupBox("1. Consultation")
        # a is the vertical layout of panel 1.
        a = QVBoxLayout(audio)
        # Several plain widgets share one loop to save lines.
        for w in (self.session_label, self.date_label):
            a.addWidget(w)
        a.addWidget(self.type_button)
        a.addSpacing(8)
        a.addWidget(self.start_button)
        a.addWidget(self.stop_button)
        a.addWidget(self.beta_note)
        a.addWidget(self.status_label)
        a.addWidget(self.duration_label)
        a.addWidget(self.level_bar)
        a.addStretch(1)
        a.addWidget(self.discard_button)
        a.addWidget(self.new_button)

        # Panel 2: transcript
        # Panel 2 starts with the editable transcript box.
        self.transcript_box = _text_box(
            "Choose 'Type or paste the consultation' and write it here, with 'Doctor:' and "
            "'Patient:' where it helps. A dictated transcript (beta) also appears here: correct "
            "every mistake before approving."
        )
        self.asr_label = QLabel()
        # Medicine names that may have been misheard (AMD-38), refreshed as the clinician edits.
        self.medicine_label = QLabel()
        self.medicine_label.setWordWrap(True)
        tone(self.medicine_label, "ai")
        # The timer waits 400 ms after the last keystroke, so the check runs once typing pauses.
        self._medicine_timer = QTimer(self)
        self._medicine_timer.setSingleShot(True)
        self._medicine_timer.setInterval(400)
        self._medicine_timer.timeout.connect(self.check_medicines)
        # Every edit restarts the timer.
        self.transcript_box.textChanged.connect(self._medicine_timer.start)
        self.approve_button = QPushButton("Approve transcript and draft the note")
        self.manual_button = QPushButton("Write the note by hand")
        self.reopen_button = QPushButton("Edit the transcript again")
        self.approve_button.clicked.connect(self.approve_and_draft)
        self.manual_button.clicked.connect(self.write_by_hand)
        self.reopen_button.clicked.connect(self.reopen_transcript)
        transcript = QGroupBox("2. Transcript")
        t = QVBoxLayout(transcript)
        t.addWidget(self.transcript_box, 1)
        t.addWidget(self.asr_label)
        t.addWidget(self.medicine_label)
        t.addWidget(self.approve_button)
        # The two small buttons sit side by side in a row.
        row = QHBoxLayout()
        row.addWidget(self.manual_button)
        row.addWidget(self.reopen_button)
        t.addLayout(row)

        # Panel 3: clinical output
        self.progress_bar = QProgressBar()
        # Setting the range to 0,0 makes Qt show a busy bar.
        self.progress_bar.setRange(0, 0)  # moving bar: the length of the reply is unknown
        self.progress_label = QLabel()
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        tone(self.error_label, "error")
        self.retry_button = QPushButton("Try the model again")
        self.retry_button.clicked.connect(self.approve_and_draft)
        self.subjective_box = _text_box("Subjective")
        self.objective_box = _text_box("Objective")
        self.assessment_box = _text_box(
            "Your assessment. Required. The model's text is shown separately below."
        )
        self.plan_box = _text_box("Plan")
        self.ai_assessment_box = _text_box("", read_only=True)
        self.copy_ai_button = QPushButton("Copy the AI text into my assessment")
        self.copy_ai_button.clicked.connect(self._copy_ai_assessment)
        self.flags_list = QListWidget()
        self.allergies_check = QCheckBox("Allergies confirmed")
        self.medications_check = QCheckBox("Current medications confirmed")
        self.negatives_check = QCheckBox("Pertinent negatives confirmed")
        # Ticking a box or typing an assessment re-runs refresh(), which decides if Finalize is
        # allowed.
        for box in (self.allergies_check, self.medications_check, self.negatives_check):
            box.toggled.connect(self.refresh)
        self.assessment_box.textChanged.connect(self.refresh)
        self.finalize_button = QPushButton("Finalize and save")
        self.finalize_button.clicked.connect(self.finalize)

        # The note's boxes sit in a scrolling area with a minimum height each, so a small or
        # resized window scrolls instead of squeezing a box until it disappears.
        soap_inner = QWidget()
        s = QVBoxLayout(soap_inner)
        # Build the four note sections as a label plus a text box.
        for label, box in (
            ("Subjective", self.subjective_box),
            ("Objective", self.objective_box),
            ("Assessment (yours)", self.assessment_box),
            ("Plan", self.plan_box),
        ):
            box.setMinimumHeight(80)
            s.addWidget(QLabel(label))
            s.addWidget(box, 1)
        ai = QGroupBox("Model's assessment")
        ai_layout = QVBoxLayout(ai)
        ai_label = QLabel(AI_LABEL)
        tone(ai_label, "ai")
        self.ai_assessment_box.setMinimumHeight(60)
        ai_layout.addWidget(ai_label)
        ai_layout.addWidget(self.ai_assessment_box)
        ai_layout.addWidget(self.copy_ai_button)
        s.addWidget(ai)
        # The scroll area wraps the note so a short window scrolls instead of squashing the boxes.
        soap = QScrollArea()
        soap.setWidgetResizable(True)
        soap.setWidget(soap_inner)

        # The Diagnostics tab lists the model's possible diagnoses with tick boxes.
        self.suggestions_list = QListWidget()
        # Each suggestion wraps, so its reason and management are readable without side-scrolling.
        self.suggestions_list.setWordWrap(True)
        diagnostics = QWidget()
        d = QVBoxLayout(diagnostics)
        diagnostics_label = QLabel(AI_LABEL + " Tick the ones you agree with.")
        tone(diagnostics_label, "ai")
        diagnostics_label.setWordWrap(True)
        d.addWidget(diagnostics_label)
        d.addWidget(self.suggestions_list)

        self.tabs = QTabWidget()
        self.tabs.addTab(soap, "SOAP note")
        self.tabs.addTab(diagnostics, "Diagnostics")

        output = QGroupBox("3. Clinical output")
        o = QVBoxLayout(output)
        # The wireframe's model label: which language model drafts the note, and that it runs
        # on this computer.
        # Read the model name from the config. getattr with a default avoids a crash if it is
        # missing.
        model = getattr(getattr(self._services, "config", None), "llm_model", "") or "unknown"
        self.model_label = QLabel(f"Model: {model} (quantized, runs on this computer)")
        tone(self.model_label, "quiet")
        o.addWidget(self.model_label)
        o.addWidget(self.progress_bar)
        o.addWidget(self.progress_label)
        o.addWidget(self.error_label)
        o.addWidget(self.retry_button)
        o.addWidget(self.tabs, 1)
        o.addWidget(QLabel("Check these before saving:"))
        # The note gets the room: on a 768-pixel-high screen an unbounded list squeezed the
        # SOAP sections to two lines each. The list scrolls past about five flags.
        self.flags_list.setMaximumHeight(130)
        o.addWidget(self.flags_list)
        for box in (self.allergies_check, self.medications_check, self.negatives_check):
            o.addWidget(box)
        o.addWidget(self.finalize_button)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        # Add the three panels to the splitter, so the user can drag the dividers.
        for panel in (audio, transcript, output):
            splitter.addWidget(panel)
        # Stretch factors set the starting widths: 1 : 3 : 4.
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setStretchFactor(2, 4)
        # The main step on each panel stands out; discarding is marked as destructive.
        for button in (self.type_button, self.approve_button, self.finalize_button):
            mark(button, "primary")
        mark(self.discard_button, "danger")
        # Keyboard shortcuts for the main steps, so a clinician need not reach for the mouse.
        # Qt ignores the shortcut of a disabled button, so Ctrl+R starts or stops recording,
        # whichever is possible at the time.
        # The same shortcut on start and stop is fine: only the enabled one fires.
        for button, keys in (
            (self.start_button, "Ctrl+R"),
            (self.stop_button, "Ctrl+R"),
            (self.type_button, "Ctrl+T"),
            (self.approve_button, "Ctrl+Return"),
            (self.finalize_button, "Ctrl+S"),
        ):
            # Set the key and a tooltip that shows it (Return is shown as Enter).
            button.setShortcut(QKeySequence(keys))
            button.setToolTip(f"{button.text()} ({keys.replace('Return', 'Enter')})")
        # The splitter fills the whole widget.
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(splitter)

    # ----- the steps -----
    def start_recording(self) -> None:
        # Dictation start: check the login, then ask the controller to open the microphone.
        if not self._step():
            return
        # Step 1 of a new consultation: if the last note was saved, clear the screen first.
        self._leave_saved()
        try:
            self.controller.start_recording()
        except Exception as exc:
            self._show_error(exc)
            return
        # Start the 100 ms timer that updates the clock and level bar.
        self._meter.start()
        self.refresh()

    def stop_recording(self) -> None:
        # Dictation stop: stop the timer, then transcribe in the background.
        if not self._step():
            return
        self._meter.stop()
        # Stopping also transcribes, which can take a minute or two: run it in the background.
        self._run("Turning speech into text...", self.controller.stop_recording, self._on_text)

    def type_transcript(self) -> None:
        """Start without recording. The typed text is approved and screened like spoken text."""
        if not self._step():
            return
        self._leave_saved()
        try:
            self.controller.start_typed_transcript()
        except Exception as exc:
            self._show_error(exc)
            return
        self._clear_all()
        # Tell the clinician the text did not come from a recording.
        self.asr_label.setText("Typed by the clinician (no recording)")
        self.refresh()
        self.transcript_box.setFocus()

    def check_medicines(self) -> None:
        """Show words that look like a misheard medicine, with the likely intended name."""
        suspects = suspect_medicines(self.transcript_box.toPlainText())
        if suspects:
            listed = ", ".join(f'"{s.word}" ({s.meant}?)' for s in suspects)
            self.medicine_label.setText(f"Check these medicine names before approving: {listed}")
        else:
            self.medicine_label.clear()

    # Runs when transcription finishes: show the text and the speech-to-text confidence.
    def _on_text(self, text: str) -> None:
        self.transcript_box.setPlainText(text)
        self.check_medicines()
        # last_info holds the language and confidence of the last transcription, or None.
        info = self._services.plan.last_info
        if info is not None:
            self.asr_label.setText(
                f"Language: {info.language}   Speech-to-text confidence: "
                f"{info.confidence:.0%} (a hint, not accuracy)"
            )

    # Gate 1: the clinician's approval of the transcript, then the model drafts the note.
    def approve_and_draft(self) -> None:
        if not self._step():
            return
        try:
            # Approve only once. A retry after a failure skips this, as the state is already
            # APPROVED.
            if self.controller.state is State.TRANSCRIBED:
                # Gate 1: the edited text, approved by the clinician, is all the model will see.
                self.controller.approve_transcript(
                    self.transcript_box.toPlainText(), self._user_id()
                )
        except Exception as exc:
            self._show_error(exc)
            return
        # Reset the pieces counter before a new draft.
        self._pieces = 0
        self._run("Drafting the note...", self.controller.generate_draft, self._show_draft)

    # Skip the model: approve the transcript and open an empty note to fill in by hand.
    def write_by_hand(self) -> None:
        if not self._step():
            return
        try:
            if self.controller.state is State.TRANSCRIBED:
                self.controller.approve_transcript(
                    self.transcript_box.toPlainText(), self._user_id()
                )
            self._show_draft(self.controller.start_manual_note())
        except Exception as exc:
            self._show_error(exc)

    # Go back from the note to editing the transcript, and clear the note.
    def reopen_transcript(self) -> None:
        if not self._step():
            return
        try:
            self.controller.reopen_transcript()
        except Exception as exc:
            self._show_error(exc)
            return
        self._clear_note()
        self.refresh()

    # Gate 2: collect the note, checklist and ticked suggestions and ask the controller to save.
    def finalize(self) -> None:
        if not self._step():
            return
        # Positions of the suggestions the clinician ticked.
        accepted = tuple(
            i
            for i in range(self.suggestions_list.count())
            if self.suggestions_list.item(i).checkState() == Qt.CheckState.Checked
        )
        note = SoapNote(
            self.subjective_box.toPlainText(),
            self.objective_box.toPlainText(),
            self.assessment_box.toPlainText(),
            self.plan_box.toPlainText(),
        )
        checklist = HistoryChecklist(
            self.allergies_check.isChecked(),
            self.medications_check.isChecked(),
            self.negatives_check.isChecked(),
        )
        try:
            # Gate 2: the controller checks the assessment and the checklist again, and the
            # database checks them a third time.
            self.controller.finalize(note, self._user_id(), checklist, accepted)
        except Exception as exc:
            self._show_error(exc)  # the note stays on screen; nothing is lost
            return
        self.refresh()  # the status line now reads "Saved"

    # Throw away the consultation after the clinician confirms.
    def discard(self) -> None:
        # Nothing to discard when idle, or when the login check fails.
        if self.controller.state is State.IDLE or not self._step():
            return
        if not self._confirm("Discard this consultation? The transcript and note will be lost."):
            return
        self._meter.stop()
        self.controller.discard()
        self._clear_all()
        self.refresh()

    # Start fresh after a saved note, then clear and redraw.
    def new_consultation(self) -> None:
        if self.controller.state is State.FINALIZED:
            self.controller.reset()
        self._clear_all()
        self.refresh()

    def _leave_saved(self) -> None:
        """After a note is saved, recording or typing starts the next consultation at once,
        without pressing "New consultation" first."""
        if self.controller.state is State.FINALIZED:
            self.new_consultation()

    # A property lets callers write ws.in_progress without brackets.
    @property
    def in_progress(self) -> bool:
        """True while there is work on screen that would be lost: a recording, a transcript or
        a note not yet saved, or a job running in the background."""
        return bool(self._busy) or self.controller.state not in (State.IDLE, State.FINALIZED)

    @property
    def keeps_session_alive(self) -> bool:
        """Recording, transcribing and drafting count as activity for the idle timeout: a
        consultation recorded hands-free is not locked half-way (main.check_idle)."""
        return bool(self._busy) or self.controller.state is State.RECORDING

    def abandon(self) -> None:
        """Drop the consultation without asking, for example when another clinician logs in.

        If a transcription or draft is still running for it, its result arrives later on the
        old controller and is ignored, so it can never appear on the next user's screen. The
        microphone is released and the discard is written to the audit log."""
        self._generation += 1
        if self._busy:
            self._finish()
        self._meter.stop()
        # Swap in a fresh controller; keep the old one so it can be discarded and audited.
        old, self.controller = self.controller, self._services.new_controller()
        try:
            if old.state is not State.FINALIZED:
                old.discard()
        except Exception:
            # The microphone may already be stopped (a transcription was running); the old
            # controller is dropped either way.
            pass
        self._clear_all()
        self.refresh()

    # ----- drawing -----
    # The one place where the screen is redrawn from the controller's state.
    def refresh(self) -> None:
        """Enable exactly the buttons the controller would accept in its current state."""
        # Short names for the two facts used most below.
        state, busy = self.controller.state, bool(self._busy)
        idle_or_done = state in (State.IDLE, State.FINALIZED)
        self.session_label.setText("Session: " + (self.controller.session_id or "-")[:8].upper())
        # Show the busy message if a job runs, else the text for the current state.
        self.status_label.setText("Status: " + (self._busy or _STATUS[state]))
        # A new consultation can start only when nothing is running and the last one is done.
        can_start = not busy and state in (State.IDLE, State.FINALIZED)
        self.start_button.setEnabled(can_start)
        self.type_button.setEnabled(can_start)
        self.stop_button.setEnabled(not busy and state is State.RECORDING)
        # The clock and the level meter only mean something while dictating.
        dictating = state is State.RECORDING
        self.duration_label.setVisible(dictating)
        self.level_bar.setVisible(dictating)
        self.discard_button.setEnabled(not busy and not idle_or_done)
        self.new_button.setEnabled(not busy and state is State.FINALIZED)

        # The transcript can be edited only after transcription and while nothing runs.
        editing = state is State.TRANSCRIBED and not busy
        self.transcript_box.setReadOnly(not editing)
        self.approve_button.setEnabled(not busy and state in (State.TRANSCRIBED, State.APPROVED))
        self.manual_button.setEnabled(
            not busy and state in (State.TRANSCRIBED, State.APPROVED, State.GENERATION_FAILED)
        )
        self.reopen_button.setEnabled(
            not busy and state in (State.APPROVED, State.DRAFTED, State.GENERATION_FAILED)
        )

        # Failure shows the retry button; the error text shows only if there is one.
        failed = state is State.GENERATION_FAILED
        self.retry_button.setVisible(failed)
        self.retry_button.setEnabled(not busy and self.controller.can_retry)
        self.error_label.setVisible(bool(self._last_error))
        self.progress_bar.setVisible(busy)
        self.progress_label.setVisible(busy)

        # The note is editable only while it is drafted and nothing runs.
        drafted = state is State.DRAFTED and not busy
        for box in (self.subjective_box, self.objective_box, self.assessment_box, self.plan_box):
            box.setReadOnly(not drafted)
        self.copy_ai_button.setEnabled(drafted and bool(self.ai_assessment_box.toPlainText()))
        for box in (self.allergies_check, self.medications_check, self.negatives_check):
            box.setEnabled(drafted)
        # Finalize needs an assessment and all three history ticks.
        ready = (
            drafted
            and bool(self.assessment_box.toPlainText().strip())
            and self.allergies_check.isChecked()
            and self.medications_check.isChecked()
            and self.negatives_check.isChecked()
        )
        self.finalize_button.setEnabled(ready)
        # Tell the clinician what is still missing.
        if drafted and not ready and not self._busy:
            self.status_label.setText("Status: " + _still_needed(self))

    # Fill every part of the note screen from the draft the model returned.
    def _show_draft(self, draft: Draft) -> None:
        self._last_error = ""
        self.error_label.clear()
        self.subjective_box.setPlainText(draft.subjective)
        self.objective_box.setPlainText(draft.objective)
        self.plan_box.setPlainText(draft.plan)
        self.assessment_box.clear()  # always blank: the clinician writes it (FR-14)
        impression = ai_impression(draft)
        self.ai_assessment_box.setPlainText(impression)
        if not impression:
            self.ai_assessment_box.setPlaceholderText(NO_AI_ASSESSMENT)
        self.flags_list.clear()
        for flag in draft.flags:
            # A flag looks like 'code:detail'. partition splits at the first colon.
            kind, _, detail = flag.partition(":")
            # Use the plain-words text for the code, and add the detail if there is any.
            text = FLAG_TEXT.get(kind, kind) + (f": {detail}" if detail else "")
            self.flags_list.addItem(text)
        if not draft.flags:
            self.flags_list.addItem(
                "No advisory flags. Still read the note against the transcript."
            )
        self.suggestions_list.clear()
        for s in draft.suggestions:
            item = QListWidgetItem(
                f"{s.rank}. {s.diagnosis}\nReason: {s.rationale}\nManagement: {s.management}"
            )
            # Make each suggestion tickable, starting unticked.
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.suggestions_list.addItem(item)
        count = len(draft.suggestions)
        # Show the number of suggestions on the tab title.
        self.tabs.setTabText(1, f"Diagnostics ({count})" if count else "Diagnostics")
        self.refresh()

    def _copy_ai_assessment(self) -> None:
        self.assessment_box.setPlainText(self.ai_assessment_box.toPlainText())

    # Runs every 100 ms while recording.
    def _update_meter(self) -> None:
        mic = self._services.microphone
        # getattr with a default keeps this safe if the microphone object lacks the value.
        seconds = int(getattr(mic, "seconds", 0))
        # Turn seconds into hours, minutes and seconds.
        h, rem = divmod(seconds, 3600)
        self.duration_label.setText(f"Duration: {h:02d}:{rem // 60:02d}:{rem % 60:02d}")
        # Normal speech peaks around 0.1 to 0.3, so the bar is scaled up four times.
        self.level_bar.setValue(min(int(getattr(mic, "level", 0.0) * 400), 100))

    # Qt widgets must only be touched on the screen thread, so the worker just stores the number.
    def _on_progress_from_worker(self, pieces: int) -> None:
        # Called on the worker thread; only store the number. The timer below draws it.
        self._pieces = pieces

    # ----- helpers -----
    # Run slow work in the background while showing a progress message.
    def _run(self, label: str, fn, on_done) -> None:
        self._busy = label
        self._last_error = ""
        self.error_label.clear()
        self.progress_label.setText(label)
        started = time.monotonic()
        # Remember which consultation this job belongs to.
        generation = self._generation

        # tick runs every 250 ms to update the elapsed time.
        def tick() -> None:
            # Elapsed time, so a long draft does not look stuck; drafting takes from about
            # 30 seconds to 3 minutes on the reference PC (ADR-017).
            elapsed = int(time.monotonic() - started)
            text = f"{label} {elapsed // 60}:{elapsed % 60:02d}"
            if self._pieces:
                text += f" ({self._pieces} pieces received)"
            self.progress_label.setText(text)

        # Kept on self so finish() can stop it.
        self._progress_timer = QTimer(self)
        self._progress_timer.setInterval(250)
        self._progress_timer.timeout.connect(tick)
        self._progress_timer.start()
        self.refresh()

        # Called on the screen thread when the job succeeds.
        def done(result) -> None:
            if generation != self._generation:
                return  # the consultation was abandoned while this ran
            self._finish()
            on_done(result)
            self.refresh()

        # Called on the screen thread when the job raises an error.
        def failed(exc: Exception) -> None:
            if generation != self._generation:
                return
            self._finish()
            self._show_error(exc)

        # Hand the work to the thread pool; the result returns through Qt signals.
        run_in_background(fn, done, failed)

    # Mark the job as finished and stop the progress timer.
    def _finish(self) -> None:
        self._busy = ""
        self._progress_timer.stop()

    def _step(self) -> bool:
        """Every action first confirms the login is still valid (idle timeout, FR-08)."""
        try:
            self._before_action()
        except Exception as exc:
            self._show_error(exc)
            return False
        return True

    # Show the plain-language message for the error and redraw.
    def _show_error(self, exc: Exception) -> None:
        self._last_error = error_code(exc)
        self.error_label.setText(message_for(self._last_error))
        self.refresh()

    # Empty the note side of the screen and untick the checklist.
    def _clear_note(self) -> None:
        for box in (
            self.subjective_box,
            self.objective_box,
            self.assessment_box,
            self.plan_box,
            self.ai_assessment_box,
        ):
            box.clear()
        self.flags_list.clear()
        self.suggestions_list.clear()
        self.tabs.setTabText(1, "Diagnostics")
        self.ai_assessment_box.setPlaceholderText("")
        for box in (self.allergies_check, self.medications_check, self.negatives_check):
            box.setChecked(False)

    # Empty everything, including the transcript, ready for the next consultation.
    def _clear_all(self) -> None:
        self._clear_note()
        self.transcript_box.clear()
        self.asr_label.clear()
        self.medicine_label.clear()
        self._last_error = ""
        self.error_label.clear()
        self.level_bar.setValue(0)
        self.duration_label.setText("Duration: 00:00:00")

    # The default confirm: a Yes/No popup.
    def _ask(self, question: str) -> bool:
        answer = QMessageBox.question(self, "Please confirm", question)
        return answer == QMessageBox.StandardButton.Yes


# Used by refresh() to build the 'To save: ...' hint.
def _still_needed(ws) -> str:
    """What is still missing before the note can be saved, in the order the screen shows it."""
    missing = []
    if not ws.assessment_box.toPlainText().strip():
        missing.append("write your assessment")
    # True if any of the three history boxes is unticked.
    if not (
        ws.allergies_check.isChecked()
        and ws.medications_check.isChecked()
        and ws.negatives_check.isChecked()
    ):
        missing.append("tick the three history checks")
    return "To save: " + " and ".join(missing)


# Plain-words status line for each controller state.
_STATUS = {
    State.IDLE: "Ready",
    State.RECORDING: "Recording",
    State.TRANSCRIBED: "Check and approve the transcript",
    State.APPROVED: "Transcript approved",
    State.DRAFTED: "Review the note, write your assessment, tick the checklist",
    State.GENERATION_FAILED: "The model could not draft the note",
    State.FINALIZED: "Saved",
}
