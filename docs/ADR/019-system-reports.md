# ADR-019: System reports for administrators, from counts and times only

- Status: accepted
- Date: 2026-10-22
- Requirement IDs: AMD-43 (new), AMD-41 (administrators never see patient notes)
- Evidence: `src/clinassist/reports.py`, `src/clinassist/ui/reports.py`, `tests/test_reports.py`,
  the Reports tests in `tests/test_ui.py`

## Context
The course outline for IS Project II asks for system reports in weeks 9 and 10. The proposal
has no reports: the administrator's use cases are accounts, model update, backup and the audit
log. A clinic manager still needs to know how the program is used: how many consultations were
documented, how often the AI's draft was used and changed, how long drafting takes, and whether
someone is guessing passwords.

Administrators must not see patient notes (AMD-41, data minimisation). A report built from the
notes themselves, for example the most common diagnoses, would show clinical content to them.

## Decision
- A **Reports** tab for administrators only. It shows the last 7 days, the last 30 days or
  everything, and can be saved as a CSV file for a spreadsheet; saving is written to the audit
  log (`report_exported`).
- Every figure comes from columns that hold **no patient text**:
  - from `sessions`: when, who finalized, model or manual draft, how the assessment was
    written, attempts, the number of check flags and the model names;
  - from `suggestions`: only whether each one was accepted;
  - the audit log's event names and times;
  - users' display names.
  The transcript, the note sections and the diagnosis, rationale and management text are
  never read.
- The report shows:
  - consultations started, saved and discarded, failed drafts, and transcripts held back by
    the input check;
  - how the notes were written (from the AI's draft or by hand), drafts that needed a second
    attempt, and notes the checks flagged;
  - how the assessment was written (by the clinician, AI text edited, or AI text kept as it
    was);
  - diagnosis suggestions shown and accepted;
  - the median time to draft a note (transcript approved to draft generated) and the median
    consultation (start to saved note), both from the audit log;
  - notes per clinician, per model and per day;
  - failed logins and locked accounts.
- **No diagnosis statistics.** They would need clinical text, so they stay out of the
  administrator's view.

## Evidence
- `test_no_patient_text_reaches_the_report_or_its_csv` puts a marker in every clinical column
  and checks it is in neither the report nor the CSV. Reading the transcript into the report
  on purpose makes the test fail.
- The counts, medians, period filter, an empty vault, the CSV layout and the role check each
  have a test.

## Limits
- Times come from the audit log of this computer, so a report covers one installation only.
- "AI text kept as it was" counts notes where the clinician's assessment matches the AI's text.
  It does not say whether that assessment was right.
- Notes saved before an update keep their old values; nothing is recalculated.
