"""Reports for clinicians: how the facility's clinical work is going, as counts and times.

The clinicians in charge of a facility need to know how many consultations were documented, how
often the AI's draft was used, how often a clinician kept the AI's text as it was, how long
drafting takes and which conditions are seen. Reading that needs a clinical background, so the
report is for clinicians, not the system administrator (AMD-50). It still never shows patient
text: a report may be printed or sent to the county as a spreadsheet. So this module reads only
these columns, never the transcript, the note sections or the diagnosis text:

    sessions:     session_id, created_at, finalized_by, draft_source, assessment_origin,
                  generation_attempts, guardrail_flags (counted, not shown), asr_model,
                  model_version
    suggestions:  session_id, accepted
    audit_logs:   ts, event, session_id, user_id
    users:        user_id, display_name, role

To show which conditions the facility sees (disease surveillance, as in the monthly MOH 705
return), the clinician's final assessment and the suggestions they accepted are also READ, but
never shown: each is matched against the fixed list of conditions in CONDITIONS, and only that
list's own label is counted. Text that matches nothing counts as "Other". A condition with fewer
than SMALL_COUNT cases in the period is folded into "Other" too, so a rare case cannot point to
one patient (small-cell suppression, as health statistics offices do).

`tests/test_reports.py` puts a marker word in every clinical column and checks it never
reaches a report or its CSV file.
"""

# This file turns the stored consultations and audit log into the clinician report screen.
# It only counts things (notes, times, conditions) and never copies patient text out.
# The same Report object feeds both the on-screen summary and the CSV export.
from __future__ import annotations

import csv
import io
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from statistics import median

# The periods offered on the screen, in days; None means everything stored.
PERIODS: dict[str, int | None] = {"Last 7 days": 7, "Last 30 days": 30, "All time": None}

# Common primary-care conditions, after the categories of Kenya's outpatient morbidity summary
# (MOH 705). Each label is counted when one of its words appears in a saved note's assessment or
# an accepted suggestion. Only these labels ever leave this module, never the note's own words.
CONDITIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Malaria", ("malaria",)),
    (
        "Upper respiratory tract infection",
        ("upper respiratory", "urti", "common cold", "pharyngitis", "tonsillitis", "sinusitis"),
    ),
    ("Pneumonia", ("pneumonia",)),
    ("Bronchitis or other chest infection", ("bronchitis", "chest infection", "lower respiratory")),
    ("Tuberculosis", ("tuberculosis", "tb")),
    ("Diarrhoea or gastroenteritis", ("diarrhoea", "diarrhea", "gastroenteritis")),
    ("Urinary tract infection", ("urinary tract infection", "uti", "cystitis", "pyelonephritis")),
    ("Hypertension", ("hypertension", "high blood pressure")),
    ("Diabetes", ("diabetes",)),
    ("Asthma", ("asthma",)),
    ("Skin infection", ("cellulitis", "skin infection", "abscess", "impetigo", "wound infection")),
    ("Typhoid", ("typhoid",)),
    ("Anaemia", ("anaemia", "anemia")),
)
# One ready-made regex per condition, built once when the module loads (not on every report).
_CONDITION_PATTERNS = [
    # Word-boundary marks in the pattern mean whole words only, so "tb" does not match inside
    # another word. re.escape stops any symbol in a word acting as regex syntax.
    (label, re.compile(r"\b(" + "|".join(re.escape(w) for w in words) + r")\b", re.IGNORECASE))
    for label, words in CONDITIONS
]
OTHER = "Other conditions"
# This is the small-cell suppression limit explained at the top.
SMALL_COUNT = 3  # fewer cases than this in a period are folded into OTHER
# Same order as date.weekday(), where Monday is 0.
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def conditions_in(texts) -> set[str]:
    """The CONDITIONS labels found in `texts`; OTHER when none is found. Never the texts."""
    # A set, so a condition named twice in one consultation is counted once.
    found = {
        label for label, pattern in _CONDITION_PATTERNS for t in texts if t and pattern.search(t)
    }
    # An empty set is falsy, so "or" gives OTHER when nothing matched.
    return found or {OTHER}


# A consultation starts with one of these events; its first one gives the start time.
START_EVENTS = frozenset({"recording_started", "typed_transcript_started"})


# One finished report: all counts and times for a period. frozen means it cannot be changed by
# mistake. Every count starts at 0.
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
    # When the facility is busiest, and what it sees (for staffing and disease surveillance)
    per_hour: dict[int, int] = field(default_factory=dict)  # hour of day 0-23 -> saved notes
    per_weekday: dict[str, int] = field(default_factory=dict)  # "Mon".."Sun" -> saved notes
    conditions: dict[str, int] = field(default_factory=dict)  # CONDITIONS label -> consultations


# Old rows may have no time zone, so UTC is assumed. Then all times can be compared.
def _parse(ts: str) -> datetime:
    value = datetime.fromisoformat(ts)
    return value if value.tzinfo else value.replace(tzinfo=UTC)


# Percentage text for the report. Shows "-" instead of dividing by zero when there is nothing to
# measure.
def _percent(part: int, whole: int) -> str:
    return f"{100 * part / whole:.0f}%" if whole else "-"


# Main function of this file: reads the vault once and works out every number in the report.
def build_report(vault, period: str, now: datetime | None = None, tz=None) -> Report:
    """Count what happened in `period` (a key of PERIODS), up to `now`. Days are counted in
    `tz`, by default this computer's time zone (Nairobi time on a clinic PC), so the counts
    per day match the clinic's own register."""
    if period not in PERIODS:
        raise ValueError("unknown_period")
    # astimezone(tz) moves the time to the clinic's zone, so the day and hour are the local ones.
    end = (now or datetime.now(UTC)).astimezone(tz)
    days = PERIODS[period]
    # No days means "All time", so there is no start limit.
    start = end - timedelta(days=days) if days else None

    # Helper used for both sessions and audit events, so both use the same period rule.
    def in_period(ts: datetime) -> bool:
        return (start is None or ts >= start) and ts <= end

    with vault.connect() as conn:
        # Only the columns listed in the module docstring are read, never the transcript.
        sessions = conn.execute(
            "SELECT session_id, created_at, finalized_by, draft_source, assessment_origin,"
            " generation_attempts, guardrail_flags, asr_model, model_version FROM sessions"
        ).fetchall()
        suggestions = conn.execute("SELECT session_id, accepted FROM suggestions").fetchall()
        # Read only to be matched against CONDITIONS below; never copied into the report.
        assessments = dict(
            conn.execute(
                "SELECT session_id, assessment FROM notes WHERE kind = 'clinician_final'"
            ).fetchall()
        )
        # Accepted diagnosis texts per session, kept only to be matched against CONDITIONS.
        accepted_dx: dict[str, list[str]] = {}
        for sid, dx in conn.execute(
            "SELECT session_id, diagnosis FROM suggestions WHERE accepted = 1"
        ).fetchall():
            # setdefault starts an empty list for a new session, then adds to it.
            accepted_dx.setdefault(sid, []).append(dx)
        events = conn.execute(
            "SELECT ts, event, session_id, user_id FROM audit_logs ORDER BY seq"
        ).fetchall()
        names = dict(conn.execute("SELECT user_id, display_name FROM users").fetchall())

    # Counter is a dictionary that counts. A missing key starts at 0.
    counts: Counter[str] = Counter()
    per_day: Counter[str] = Counter()
    per_clinician: Counter[str] = Counter()
    models: Counter[str] = Counter()
    per_hour: Counter[int] = Counter()
    per_weekday: Counter[str] = Counter()
    conditions: Counter[str] = Counter()
    saved: set[str] = set()
    # One loop over saved sessions. The names are the columns selected above, in order.
    for sid, created, by, source, origin, attempts, flags, asr, llm in sessions:
        if not in_period(_parse(created)):
            continue
        # Remember which sessions are in the period, so their suggestions can be counted later.
        saved.add(sid)
        counts["finalized"] += 1
        counts["from_model_draft" if source == "model" else "written_by_hand"] += 1
        # Picks the counter named for how the assessment was written (written, edited or
        # kept as the AI's).
        counts[
            {
                "clinician_manual": "assessment_by_clinician",
                "clinician_edited": "assessment_edited",
                "ai_text_accepted_verbatim": "assessment_ai_verbatim",
            }[origin]
        ] += 1
        # A second attempt only makes sense for model drafts.
        if source == "model" and attempts > 1:
            counts["drafts_retried"] += 1
        # Flags are stored as JSON text. Only how many there are is used, never what they say.
        n_flags = len(json.loads(flags or "[]"))
        if n_flags:
            counts["notes_with_flags"] += 1
            counts["flags_total"] += n_flags
        # Use clinic-local time so the day, hour and weekday match the clinic's own register.
        local = _parse(created).astimezone(tz)
        per_day[local.date().isoformat()] += 1
        per_hour[local.hour] += 1
        per_weekday[WEEKDAYS[local.weekday()]] += 1
        # Only labels from CONDITIONS go in, never the note's own words.
        conditions.update(conditions_in([assessments.get(sid, ""), *accepted_dx.get(sid, [])]))
        # If the user account was deleted, show a fixed label instead of failing.
        per_clinician[names.get(by, "(account removed)")] += 1
        models[f"{asr or 'typed'} / {llm or 'written by hand'}"] += 1

    # Count suggestions only for notes saved in this period.
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
    # The log is read in order (ORDER BY seq above), so "last approved" really is the latest.
    for ts_text, event, sid, _user in events:
        ts = _parse(ts_text)
        # Keep only the first start event, so a later event does not move the start time.
        if event in START_EVENTS and sid not in first_seen:
            first_seen[sid] = ts
        if event == "transcript_approved":
            approved_at[sid] = ts
        # Times were recorded for every event, but only events inside the period are counted.
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
        # Drafting time: from transcript approval to the draft being ready.
        elif event == "draft_generated" and sid in approved_at:
            draft_times.append((ts - approved_at[sid]).total_seconds())
        # Whole consultation: from start to saved note, converted from seconds to minutes.
        elif event == "finalized" and sid in first_seen:
            consult_times.append((ts - first_seen[sid]).total_seconds() / 60)

    return Report(
        period=period,
        start=start,
        end=end,
        # median is not pulled up by one very slow case, unlike the average.
        median_draft_seconds=median(draft_times) if draft_times else None,
        median_consultation_minutes=median(consult_times) if consult_times else None,
        per_day=dict(sorted(per_day.items())),
        per_clinician=dict(per_clinician.most_common()),
        models=dict(models.most_common()),
        # Fill all 24 hours (and 7 days below), including zeros, so the charts have no gaps.
        per_hour={h: per_hour[h] for h in range(24)},
        per_weekday={d: per_weekday[d] for d in WEEKDAYS},
        conditions=_suppress_small(conditions),
        # Pass the counters by name into the Report fields.
        **{k: v for k, v in counts.items()},
    )


# Small-cell suppression: hides rare conditions so one patient cannot be picked out.
def _suppress_small(counts: Counter) -> dict[str, int]:
    """Most common first; a condition with fewer than SMALL_COUNT cases joins OTHER."""
    kept: Counter[str] = Counter()
    for label, n in counts.items():
        # Rare labels (and OTHER itself) are added into OTHER, others keep their own label.
        kept[label if n >= SMALL_COUNT and label != OTHER else OTHER] += n
    # Take OTHER out so it can be put last, whatever its size.
    other = kept.pop(OTHER, 0)
    result = dict(kept.most_common())
    if other:
        result[OTHER] = other
    return result


# Turns a Report into plain rows. The screen and the CSV file both use this list, so they always
# agree.
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
            # Shows the count and its percentage of all saved notes.
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
            # A dash when there is nothing to measure.
            "-"
            if r.median_consultation_minutes is None
            else f"{r.median_consultation_minutes:.1f} min",
        ),
    ]
    # Variable-length sections go after the fixed ones.
    rows += [("Notes per clinician", name, str(n)) for name, n in r.per_clinician.items()]
    rows += [("Notes per model (speech / language)", m, str(n)) for m, n in r.models.items()]
    rows += [("Notes per day", day, str(n)) for day, n in r.per_day.items()]
    rows += [("Conditions seen", c, str(n)) for c, n in r.conditions.items()]
    # Skip empty days and hours so the lists stay short.
    rows += [("Busiest days", d, str(n)) for d, n in r.per_weekday.items() if n]
    rows += [
        ("Busiest hours", f"{h:02d}:00-{h:02d}:59", str(n)) for h, n in r.per_hour.items() if n
    ]
    return rows


# One line saying which dates the report covers.
def period_text(r: Report) -> str:
    # Small helper so the date format is the same in both places below.
    def day(d: date) -> str:
        return d.isoformat()

    since = "the first record" if r.start is None else day(r.start.date())
    return f"{r.period}: from {since} to {day(r.end.date())} (this computer's time)"


# Builds the CSV file text for export to a spreadsheet.
def to_csv(r: Report) -> str:
    """The report as CSV, for a spreadsheet. Counts and times only, like the screen."""
    # The CSV is built in memory and returned as text, not written to disk here.
    out = io.StringIO()
    # Unix line ends, so the file looks the same on any computer.
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["Clinical Consultation Assistant: system report"])
    writer.writerow([period_text(r)])
    writer.writerow([])
    writer.writerow(["Section", "Measure", "Value"])
    writer.writerows(summary_rows(r))
    return out.getvalue()
