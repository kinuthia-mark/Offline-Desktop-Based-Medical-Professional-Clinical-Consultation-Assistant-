# ADR-009: The desktop interface

- Status: accepted
- Date: 2026-10-04
- Requirement IDs: FR-03, FR-06, FR-08, FR-10a, FR-10d, FR-13, FR-14, FR-15, FR-16
- Evidence: `tests/test_ui.py`, `docs/screenshots/workspace.png`

## Context
The proposal's wireframe (Figure 4.8) shows one screen with three panels (session and audio,
transcript editor, clinical output with SOAP and Diagnostics tabs) and navigation to Session
Records and Audit and System Logs. The cross-check (`docs/proposal/CROSSCHECK.md`, section 5)
listed what the wireframe lacks: login, the history checklist, the clinician's own assessment, the
failure state, progress while drafting, advisory flags, a discard confirmation and the recovery
code at set-up. Section 3.5 allows Tkinter or PyQt6; Figure 4.5 says PyQt6.

## Options considered
1. **PyQt6.** Matches Figure 4.5. GPL licence: anyone given the installer may ask for the full
   source under the GPL.
2. **PySide6.** The official Qt for Python, same widgets and nearly the same code. LGPL licence:
   the installer can be given to clinics without placing the whole application under the GPL.
3. **Tkinter.** Built into Python, but weaker text editing and layout for a three-panel screen.

## Decision
PySide6 (decided with the author, 2026-10-04), recorded as an update to AMD-09.

- One window. Tabs: Consultation, Session records, and Audit and accounts (administrators only).
- The consultation screen follows Figure 4.8, plus the missing items above. It holds no rules of
  its own: after every action it redraws from the controller's state, so a button is enabled only
  when the controller would accept the action.
- The clinician's assessment box always starts empty. The model's assessment is shown below it,
  read-only, labelled "AI-generated. Not part of your note unless you copy it." Copying it is a
  deliberate click, and the stored record then says the assessment was accepted verbatim.
- Finalize is enabled only with an assessment and all three history ticks; the controller and the
  database check the same things again.
- Speech-to-text, drafting and unlocking run on a worker thread, so the window never freezes;
  a moving bar and a count of pieces received show that drafting is progressing.
- Every error code has a plain sentence (`ui/messages.py`); a test fails if a code the program can
  raise has no sentence.
- Start-up order: readiness checks, then create or unlock the vault (the recovery code is shown
  once and needs a tick that it was written down), the first administrator on a new vault, then
  login.
- Idle timeout: any key press or mouse click counts as activity; after 10 minutes the login dialog
  covers the window. If a different person logs in, the open consultation is discarded first.
- Only `ui/main.py` builds real parts. A test fails if any other screen imports an adapter or a
  security module directly.

## Evidence
`tests/test_ui.py` drives the real screens off-screen by clicking their buttons, with a fake
microphone, Whisper and Ollama, and the real controller, input guard, generator, vault, store and
audit log. It covers the whole consultation from the screen, the blank assessment and the separate
AI text, the finalize conditions, the failure state with retry and writing by hand, a transcript
aimed at the AI (the model is never called), a failed speech-to-text, discard confirmation, an
expired login, the records view, the administrator's screen, the readiness, recovery-code and login
dialogs, a different user after a timeout, and the import rule. The tests passed six runs in a
row after a timing problem in one test was fixed (it read the screen before the result arrived).

Mutation checks, all 9 caught: Finalize enabled without the checklist; the assessment pre-filled
with the AI text; the AI text editable; the transcript locked after speech-to-text; the model given
the unedited text; discard without asking; the login not checked before a step; another user seeing
the open consultation; the administrator tab shown to clinicians.

Building the screen exposed one controller defect, now fixed: a failed speech-to-text left the
session in "recording" with the microphone already off. It now moves on with an empty transcript
the clinician can type, and the failure is audited.

`docs/screenshots/workspace.png` shows the screen with a synthetic consultation: the clinician's
assessment, the separate AI text, and Finalize still disabled because one history box is unticked.

## Limits
- Tested off-screen, not yet with clinicians. Usability (task time, errors, satisfaction) needs a
  short study with a few clinicians or students, which is part of the evaluation (AMD-30).
- The header does not show an "Air-Gapped" label. The wireframe has one, but it must reflect a real
  check (FR-18), which comes with the air-gap enforcement module.
- "Export / Save" from the wireframe is not built; its behaviour is still to be decided (AMD-36).
- What the input guard masked is not shown yet; the verdict carries it.
- Session ids are shown as the first 8 characters of the random id, not as `SESS-YYYYMMDD-NN`
  (AMD-34).

## Consequences
- AMD-09: PySide6 rather than PyQt6; no web server. FR-03, FR-06 and FR-16 built. The interface
  parts of FR-13 to FR-15, FR-10a and FR-10d are built.
- Figure 4.8 is redrawn from the real screen for the final report (AMD-14).
