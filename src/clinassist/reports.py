"""System reports for administrators: how the program is being used, as counts and times only.

A clinic manager or supervisor needs to know how many consultations were documented, how often
the AI's draft was used, how often a clinician kept the AI's text as it was, how long drafting
takes and whether there were failed logins. None of that needs patient text, and
administrators are not allowed to see it (data minimisation, AMD-41). So this module reads only
these columns, never the transcript, the note sections or the diagnosis text:

    sessions:     session_id, created_at, finalized_by, draft_source, assessment_origin,
                  generation_attempts, guardrail_flags (counted, not shown), asr_model,
                  model_version
    suggestions:  session_id, accepted
    audit_logs:   ts, event, session_id, user_id
    users:        user_id, display_name, role

`tests/test_reports.py` puts a marker word in every clinical column and checks it never
reaches a report or its CSV file.
"""

from __future__ import annotations

import csv
import io
import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from statistics import median

# The periods offered on the screen, in days; None means everything stored.
PERIODS: dict[str, int | None] = {"Last 7 days": 7, "Last 30 days": 30, "All time": None}

# A consultation starts with one of these events; its first one gives the start time.
START_EVENTS = frozenset({"recording_started", "typed_transcript_started"})


@dataclass(frozen=True)
class Report:
    period: str
    start: datetime | None  # None: from the first record
    end: datetime
    # Activity
    started: int = 0
    finalized: int = 0
    discarded: int = 0
    drafts_failed: int = 0
    quarantined: int = 0
    # How the saved notes were written
    from_model_draft: int = 0
    written_by_hand: int = 0
    assessment_by_clinician: int = 0
    assessment_edited: int = 0
    assessment_ai_verbatim: int = 0
    drafts_retried: int = 0  # the first attempt failed and a second one gave the note
    notes_with_flags: int = 0
    flags_total: int = 0
    # Diagnosis suggestions
    suggestions_shown: int = 0
    suggestions_accepted: int = 0
    # Times (None when there is nothing to measure)
    median_draft_seconds: float | None = None
    median_consultation_minutes: float | None = None
    # Breakdowns
    per_day: dict[str, int] = field(default_factory=dict)  # finalized notes per date
    per_clinician: dict[str, int] = field(default_factory=dict)  # display name -> finalized
    models: dict[str, int] = field(default_factory=dict)  # "speech / language" -> notes
    # Accounts
    failed_logins: int = 0
    lockouts: int = 0


def _parse(ts: str) -> datetime:
    value = datetime.fromisoformat(ts)
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _percent(part: int, whole: int) -> str:
    return f"{100 * part / whole:.0f}%" if whole else "-"


def build_report(vault, period: str, now: datetime | None = None, tz=None) -> Report:
    """Count what happened in `period` (a key of PERIODS), up to `now`. Days are counted in
    `tz`, by default this computer's time zone (Nairobi time on a clinic PC), so the counts
    per day match the clinic's own register."""
    if period not in PERIODS:
        raise ValueError("unknown_period")
    end = (now or datetime.now(UTC)).astimezone(tz)
    days = PERIODS[period]
    start = end - timedelta(days=days) if days else None

    def in_period(ts: datetime) -> bool:
        return (start is None or ts >= start) and ts <= end

    with vault.connect() as conn:
        sessions = conn.execute(
            "SELECT session_id, created_at, finalized_by, draft_source, assessment_origin,"
            " generation_attempts, guardrail_flags, asr_model, model_version FROM sessions"
        ).fetchall()
        suggestions = conn.execute("SELECT session_id, accepted FROM suggestions").fetchall()
        events = conn.execute(
            "SELECT ts, event, session_id, user_id FROM audit_logs ORDER BY seq"
        ).fetchall()
        names = dict(conn.execute("SELECT user_id, display_name FROM users").fetchall())

    counts: Counter[str] = Counter()
    per_day: Counter[str] = Counter()
    per_clinician: Counter[str] = Counter()
    models: Counter[str] = Counter()
    saved: set[str] = set()
    for sid, created, by, source, origin, attempts, flags, asr, llm in sessions:
        if not in_period(_parse(created)):
            continue
        saved.add(sid)
        counts["finalized"] += 1
        counts["from_model_draft" if source == "model" else "written_by_hand"] += 1
        counts[
            {
                "clinician_manual": "assessment_by_clinician",
                "clinician_edited": "assessment_edited",
                "ai_text_accepted_verbatim": "assessment_ai_verbatim",
            }[origin]
        ] += 1
        if source == "model" and attempts > 1:
            counts["drafts_retried"] += 1
        n_flags = len(json.loads(flags or "[]"))
        if n_flags:
            counts["notes_with_flags"] += 1
            counts["flags_total"] += n_flags
        per_day[_parse(created).astimezone(tz).date().isoformat()] += 1
        per_clinician[names.get(by, "(account removed)")] += 1
        models[f"{asr or 'typed'} / {llm or 'written by hand'}"] += 1

    for sid, accepted in suggestions:
        if sid in saved:
            counts["suggestions_shown"] += 1
            counts["suggestions_accepted"] += int(accepted)

    # Walk the audit log once, keeping per consultation when it started and when its transcript
    # was last approved, so each draft and each saved note can be timed.
    first_seen: dict[str, datetime] = {}
    approved_at: dict[str, datetime] = {}
    draft_times: list[float] = []
    consult_times: list[float] = []
    for ts_text, event, sid, _user in events:
        ts = _parse(ts_text)
        if event in START_EVENTS and sid not in first_seen:
            first_seen[sid] = ts
        if event == "transcript_approved":
            approved_at[sid] = ts
        if not in_period(ts):
            continue
        if event in START_EVENTS:
            counts["started"] += 1
        elif event == "session_discarded":
            counts["discarded"] += 1
        elif event == "generation_failed":
            counts["drafts_failed"] += 1
        elif event == "quarantined":
            counts["quarantined"] += 1
        elif event == "login_failed":
            counts["failed_logins"] += 1
        elif event == "account_locked":
            counts["lockouts"] += 1
            counts["failed_logins"] += 1  # the wrong password that locked the account
        elif event == "draft_generated" and sid in approved_at:
            draft_times.append((ts - approved_at[sid]).total_seconds())
        elif event == "finalized" and sid in first_seen:
            consult_times.append((ts - first_seen[sid]).total_seconds() / 60)

    return Report(
        period=period,
        start=start,
        end=end,
        median_draft_seconds=median(draft_times) if draft_times else None,
        median_consultation_minutes=median(consult_times) if consult_times else None,
        per_day=dict(sorted(per_day.items())),
        per_clinician=dict(per_clinician.most_common()),
        models=dict(models.most_common()),
        **{k: v for k, v in counts.items()},
    )


def summary_rows(r: Report) -> list[tuple[str, str, str]]:
    """(section, measure, value) rows: what the screen shows and the CSV file holds."""
    rows = [
        ("Activity", "Consultations started", str(r.started)),
        ("Activity", "Notes finalized and saved", str(r.finalized)),
        ("Activity", "Consultations discarded", str(r.discarded)),
        ("Activity", "Drafts that failed", str(r.drafts_failed)),
        ("Activity", "Transcripts held back by the input check", str(r.quarantined)),
        ("How notes were written", "From the AI's draft", str(r.from_model_draft)),
        ("How notes were written", "Written by hand", str(r.written_by_hand)),
        (
            "How notes were written",
            "Drafts that needed a second attempt",
            str(r.drafts_retried),
        ),
        (
            "How notes were written",
            "Notes the checks flagged for review",
            f"{r.notes_with_flags} ({r.flags_total} flags)",
        ),
        ("Clinician's assessment", "Written by the clinician", str(r.assessment_by_clinician)),
        ("Clinician's assessment", "AI text edited by the clinician", str(r.assessment_edited)),
        (
            "Clinician's assessment",
            "AI text kept as it was",
            f"{r.assessment_ai_verbatim} ({_percent(r.assessment_ai_verbatim, r.finalized)})",
        ),
        ("Diagnosis suggestions", "Shown on saved notes", str(r.suggestions_shown)),
        (
            "Diagnosis suggestions",
            "Accepted by the clinician",
            f"{r.suggestions_accepted} ({_percent(r.suggestions_accepted, r.suggestions_shown)})",
        ),
        (
            "Time",
            "Median time to draft a note",
            "-" if r.median_draft_seconds is None else f"{r.median_draft_seconds:.0f} s",
        ),
        (
            "Time",
            "Median consultation, start to saved note",
            "-"
            if r.median_consultation_minutes is None
            else f"{r.median_consultation_minutes:.1f} min",
        ),
        ("Accounts", "Failed logins", str(r.failed_logins)),
        ("Accounts", "Accounts locked", str(r.lockouts)),
    ]
    rows += [("Notes per clinician", name, str(n)) for name, n in r.per_clinician.items()]
    rows += [("Notes per model (speech / language)", m, str(n)) for m, n in r.models.items()]
    rows += [("Notes per day", day, str(n)) for day, n in r.per_day.items()]
    return rows


def period_text(r: Report) -> str:
    def day(d: date) -> str:
        return d.isoformat()

    since = "the first record" if r.start is None else day(r.start.date())
    return f"{r.period}: from {since} to {day(r.end.date())} (this computer's time)"


def to_csv(r: Report) -> str:
    """The report as CSV, for a spreadsheet. Counts and times only, like the screen."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["Clinical Consultation Assistant: system report"])
    writer.writerow([period_text(r)])
    writer.writerow([])
    writer.writerow(["Section", "Measure", "Value"])
    writer.writerows(summary_rows(r))
    return out.getvalue()
