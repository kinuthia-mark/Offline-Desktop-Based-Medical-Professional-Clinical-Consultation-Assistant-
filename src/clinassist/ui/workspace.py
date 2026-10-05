"""The consultation workspace (FR-01, FR-03, FR-06, FR-13 to FR-15; wireframe Figure 4.8).

One screen, three panels, left to right in the order of a consultation:

    1. Session and audio     start and stop recording, elapsed time, level meter, discard
    2. Transcript            edit the speech-to-text output, then approve it (gate 1)
    3. Clinical output       the drafted note, the clinician's own assessment, the AI's text
                             kept apart and labelled, advisory flags, the history checklist,
                             and Finalize (gate 2)

The screen holds no rules of its own. It calls the controller and then redraws itself from the
controller's state, so a button can only be pressed when the controller would accept it anyway.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from PySide6.QtCore import Qt, QTimer
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

from clinassist.controller import State
from clinassist.domain import Draft, HistoryChecklist, SoapNote
from clinassist.medcheck import suspect_medicines
from clinassist.ui.messages import message_for
from clinassist.ui.workers import error_code, run_in_background

AI_LABEL = "AI-generated. Not part of your note unless you copy it."
# Colours that stay readable on both light and dark Windows themes.
AI_COLOUR = "#c98a00"  # amber: AI-generated content
ERROR_COLOUR = "#e0484d"  # red: something needs attention
# Shown when the model leaves the diagnosis to the clinician, which the prompt asks it to do
# unless the clinician said one aloud (ADR-002).
NO_AI_ASSESSMENT = (
    "The model does not write a diagnosis into the note unless one was said aloud. "
    "Its possible diagnoses are on the Diagnostics tab."
)

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
        self._services = services
        self._user_id = user_id
        self._before_action = before_action
        self._confirm = confirm or self._ask
        self.controller = services.new_controller()
        self._busy = ""  # what is running in the background, or "" when idle
        self._last_error = ""
        self._build()
        services.progress.listener = self._on_progress_from_worker
        self._pieces = 0
        # While recording, the meter and the clock are refreshed ten times a second.
        self._meter = QTimer(self)
        self._meter.setInterval(100)
        self._meter.timeout.connect(self._update_meter)
        self.refresh()

    # ----- layout -----
    def _build(self) -> None:
        # Panel 1: session and audio
        self.session_label = QLabel()
        self.date_label = QLabel(f"Date: {date.today().isoformat()}")
        self.status_label = QLabel()
        self.duration_label = QLabel("Duration: 00:00:00")
        self.level_bar = QProgressBar()
        self.level_bar.setRange(0, 100)
        self.level_bar.setFormat("Level")
        self.start_button = QPushButton("Start recording")
        self.stop_button = QPushButton("Stop recording")
        # For a consultation without recording: the clinician types the transcript instead.
        self.type_button = QPushButton("Type the transcript instead")
        self.discard_button = QPushButton("Discard consultation")
        self.new_button = QPushButton("New consultation")
        self.start_button.clicked.connect(self.start_recording)
        self.stop_button.clicked.connect(self.stop_recording)
        self.type_button.clicked.connect(self.type_transcript)
        self.discard_button.clicked.connect(self.discard)
        self.new_button.clicked.connect(self.new_consultation)
        audio = QGroupBox("1. Session and audio")
        a = QVBoxLayout(audio)
        for w in (self.session_label, self.date_label, QLabel("Sample rate: 16 kHz, mono")):
            a.addWidget(w)
        a.addWidget(self.start_button)
        a.addWidget(self.stop_button)
        a.addWidget(self.type_button)
        a.addWidget(self.status_label)
        a.addWidget(self.duration_label)
        a.addWidget(self.level_bar)
        a.addStretch(1)
        a.addWidget(self.discard_button)
        a.addWidget(self.new_button)

        # Panel 2: transcript
        self.transcript_box = _text_box(
            "The transcript appears here after recording, or type it here after choosing 'Type "
            "the transcript instead'. Correct any mistakes, and add "
            "'Doctor:' and 'Patient:' where it helps, before approving."
        )
        self.asr_label = QLabel()
        # Medicine names that may have been misheard (AMD-38), refreshed as the clinician edits.
        self.medicine_label = QLabel()
        self.medicine_label.setWordWrap(True)
        self.medicine_label.setStyleSheet(f"color: {AI_COLOUR}; font-weight: bold;")
        self._medicine_timer = QTimer(self)
        self._medicine_timer.setSingleShot(True)
        self._medicine_timer.setInterval(400)
        self._medicine_timer.timeout.connect(self.check_medicines)
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
        row = QHBoxLayout()
        row.addWidget(self.manual_button)
        row.addWidget(self.reopen_button)
        t.addLayout(row)

        # Panel 3: clinical output
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # moving bar: the length of the reply is unknown
        self.progress_label = QLabel()
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet(f"color: {ERROR_COLOUR};")
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
        for box in (self.allergies_check, self.medications_check, self.negatives_check):
            box.toggled.connect(self.refresh)
        self.assessment_box.textChanged.connect(self.refresh)
        self.finalize_button = QPushButton("Finalize and save")
        self.finalize_button.clicked.connect(self.finalize)

        # The note's boxes sit in a scrolling area with a minimum height each, so a small or
        # resized window scrolls instead of squeezing a box until it disappears.
        soap_inner = QWidget()
        s = QVBoxLayout(soap_inner)
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
        ai_label.setStyleSheet(f"color: {AI_COLOUR}; font-weight: bold;")
        self.ai_assessment_box.setMinimumHeight(60)
        ai_layout.addWidget(ai_label)
        ai_layout.addWidget(self.ai_assessment_box)
        ai_layout.addWidget(self.copy_ai_button)
        s.addWidget(ai)
        soap = QScrollArea()
        soap.setWidgetResizable(True)
        soap.setWidget(soap_inner)

        self.suggestions_list = QListWidget()
        diagnostics = QWidget()
        d = QVBoxLayout(diagnostics)
        diagnostics_label = QLabel(AI_LABEL + " Tick the ones you agree with.")
        diagnostics_label.setStyleSheet(f"color: {AI_COLOUR}; font-weight: bold;")
        diagnostics_label.setWordWrap(True)
        d.addWidget(diagnostics_label)
        d.addWidget(self.suggestions_list)

        self.tabs = QTabWidget()
        self.tabs.addTab(soap, "SOAP note")
        self.tabs.addTab(diagnostics, "Diagnostics")

        output = QGroupBox("3. Clinical output")
        o = QVBoxLayout(output)
        o.addWidget(self.progress_bar)
        o.addWidget(self.progress_label)
        o.addWidget(self.error_label)
        o.addWidget(self.retry_button)
        o.addWidget(self.tabs, 1)
        o.addWidget(QLabel("Check these before saving:"))
        o.addWidget(self.flags_list)
        for box in (self.allergies_check, self.medications_check, self.negatives_check):
            o.addWidget(box)
        o.addWidget(self.finalize_button)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        for panel in (audio, transcript, output):
            splitter.addWidget(panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setStretchFactor(2, 4)
        layout = QHBoxLayout(self)
        layout.addWidget(splitter)

    # ----- the steps -----
    def start_recording(self) -> None:
        if not self._step():
            return
        try:
            self.controller.start_recording()
        except Exception as exc:
            self._show_error(exc)
            return
        self._meter.start()
        self.refresh()

    def stop_recording(self) -> None:
        if not self._step():
            return
        self._meter.stop()
        # Stopping also transcribes, which can take a minute or two: run it in the background.
        self._run("Turning speech into text...", self.controller.stop_recording, self._on_text)

    def type_transcript(self) -> None:
        """Start without recording. The typed text is approved and screened like spoken text."""
        if not self._step():
            return
        try:
            self.controller.start_typed_transcript()
        except Exception as exc:
            self._show_error(exc)
            return
        self._clear_all()
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

    def _on_text(self, text: str) -> None:
        self.transcript_box.setPlainText(text)
        self.check_medicines()
        info = self._services.plan.last_info
        if info is not None:
            self.asr_label.setText(
                f"Language: {info.language}   Speech-to-text confidence: "
                f"{info.confidence:.0%} (a hint, not accuracy)"
            )

    def approve_and_draft(self) -> None:
        if not self._step():
            return
        try:
            if self.controller.state is State.TRANSCRIBED:
                # Gate 1: the edited text, approved by the clinician, is all the model will see.
                self.controller.approve_transcript(
                    self.transcript_box.toPlainText(), self._user_id()
                )
        except Exception as exc:
            self._show_error(exc)
            return
        self._pieces = 0
        self._run("Drafting the note...", self.controller.generate_draft, self._show_draft)

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

    def reopen_transcript(self) -> None:
        if not self._step():
            return
        self.controller.reopen_transcript()
        self._clear_note()
        self.refresh()

    def finalize(self) -> None:
        if not self._step():
            return
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

    def discard(self) -> None:
        if self.controller.state is State.IDLE or not self._step():
            return
        if not self._confirm("Discard this consultation? The transcript and note will be lost."):
            return
        self._meter.stop()
        self.controller.discard()
        self._clear_all()
        self.refresh()

    def new_consultation(self) -> None:
        if self.controller.state is State.FINALIZED:
            self.controller.reset()
        self._clear_all()
        self.refresh()

    # ----- drawing -----
    def refresh(self) -> None:
        """Enable exactly the buttons the controller would accept in its current state."""
        state, busy = self.controller.state, bool(self._busy)
        idle_or_done = state in (State.IDLE, State.FINALIZED)
        self.session_label.setText("Session: " + (self.controller.session_id or "-")[:8].upper())
        self.status_label.setText("Status: " + (self._busy or _STATUS[state]))
        self.start_button.setEnabled(not busy and state is State.IDLE)
        self.type_button.setEnabled(not busy and state is State.IDLE)
        self.stop_button.setEnabled(not busy and state is State.RECORDING)
        self.discard_button.setEnabled(not busy and not idle_or_done)
        self.new_button.setEnabled(not busy and state is State.FINALIZED)

        editing = state is State.TRANSCRIBED and not busy
        self.transcript_box.setReadOnly(not editing)
        self.approve_button.setEnabled(not busy and state in (State.TRANSCRIBED, State.APPROVED))
        self.manual_button.setEnabled(
            not busy and state in (State.TRANSCRIBED, State.APPROVED, State.GENERATION_FAILED)
        )
        self.reopen_button.setEnabled(
            not busy and state in (State.APPROVED, State.DRAFTED, State.GENERATION_FAILED)
        )

        failed = state is State.GENERATION_FAILED
        self.retry_button.setVisible(failed)
        self.retry_button.setEnabled(not busy and self.controller.attempts < 2)
        self.error_label.setVisible(bool(self._last_error))
        self.progress_bar.setVisible(busy)
        self.progress_label.setVisible(busy)

        drafted = state is State.DRAFTED and not busy
        for box in (self.subjective_box, self.objective_box, self.assessment_box, self.plan_box):
            box.setReadOnly(not drafted)
        self.copy_ai_button.setEnabled(drafted and bool(self.ai_assessment_box.toPlainText()))
        for box in (self.allergies_check, self.medications_check, self.negatives_check):
            box.setEnabled(drafted)
        ready = (
            drafted
            and bool(self.assessment_box.toPlainText().strip())
            and self.allergies_check.isChecked()
            and self.medications_check.isChecked()
            and self.negatives_check.isChecked()
        )
        self.finalize_button.setEnabled(ready)

    def _show_draft(self, draft: Draft) -> None:
        self._last_error = ""
        self.error_label.clear()
        self.subjective_box.setPlainText(draft.subjective)
        self.objective_box.setPlainText(draft.objective)
        self.plan_box.setPlainText(draft.plan)
        self.assessment_box.clear()  # always blank: the clinician writes it (FR-14)
        stated = draft.ai_assessment.strip()
        if not stated or stated.lower().rstrip(".") == "not stated":
            self.ai_assessment_box.clear()
            self.ai_assessment_box.setPlaceholderText(NO_AI_ASSESSMENT)
        else:
            self.ai_assessment_box.setPlainText(stated)
        self.flags_list.clear()
        for flag in draft.flags:
            kind, _, detail = flag.partition(":")
            text = FLAG_TEXT.get(kind, kind) + (f": {detail}" if detail else "")
            self.flags_list.addItem(text)
        if not draft.flags:
            self.flags_list.addItem(
                "No advisory flags. Still read the note against the transcript."
            )
        self.suggestions_list.clear()
        for s in draft.suggestions:
            item = QListWidgetItem(f"{s.rank}. {s.diagnosis}  ({s.rationale}; {s.management})")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.suggestions_list.addItem(item)
        count = len(draft.suggestions)
        self.tabs.setTabText(1, f"Diagnostics ({count})" if count else "Diagnostics")
        self.refresh()

    def _copy_ai_assessment(self) -> None:
        self.assessment_box.setPlainText(self.ai_assessment_box.toPlainText())

    def _update_meter(self) -> None:
        mic = self._services.microphone
        seconds = int(getattr(mic, "seconds", 0))
        h, rem = divmod(seconds, 3600)
        self.duration_label.setText(f"Duration: {h:02d}:{rem // 60:02d}:{rem % 60:02d}")
        # Normal speech peaks around 0.1 to 0.3, so the bar is scaled up four times.
        self.level_bar.setValue(min(int(getattr(mic, "level", 0.0) * 400), 100))

    def _on_progress_from_worker(self, pieces: int) -> None:
        # Called on the worker thread; only store the number. The timer below draws it.
        self._pieces = pieces

    # ----- helpers -----
    def _run(self, label: str, fn, on_done) -> None:
        self._busy = label
        self._last_error = ""
        self.error_label.clear()
        self.progress_label.setText(label)
        self._progress_timer = QTimer(self)
        self._progress_timer.setInterval(250)
        self._progress_timer.timeout.connect(
            lambda: self.progress_label.setText(
                f"{label} ({self._pieces} pieces received)" if self._pieces else label
            )
        )
        self._progress_timer.start()
        self.refresh()

        def done(result) -> None:
            self._finish()
            on_done(result)
            self.refresh()

        def failed(exc: Exception) -> None:
            self._finish()
            self._show_error(exc)

        run_in_background(fn, done, failed)

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

    def _show_error(self, exc: Exception) -> None:
        self._last_error = error_code(exc)
        self.error_label.setText(message_for(self._last_error))
        self.refresh()

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

    def _clear_all(self) -> None:
        self._clear_note()
        self.transcript_box.clear()
        self.asr_label.clear()
        self.medicine_label.clear()
        self._last_error = ""
        self.error_label.clear()
        self.level_bar.setValue(0)
        self.duration_label.setText("Duration: 00:00:00")

    def _ask(self, question: str) -> bool:
        answer = QMessageBox.question(self, "Please confirm", question)
        return answer == QMessageBox.StandardButton.Yes


_STATUS = {
    State.IDLE: "Ready",
    State.RECORDING: "Recording",
    State.TRANSCRIBED: "Check and approve the transcript",
    State.APPROVED: "Transcript approved",
    State.DRAFTED: "Review the note, write your assessment, tick the checklist",
    State.GENERATION_FAILED: "The model could not draft the note",
    State.FINALIZED: "Saved",
}
