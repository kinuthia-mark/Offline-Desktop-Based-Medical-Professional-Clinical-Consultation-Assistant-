"""Composition root: the one place where the real parts are built and connected.

Everything else in the program receives its parts from here, which is why each part can be
tested on its own with fakes. The interface asks this module for a controller and never imports
an adapter itself.

Memory plan for an 8 GB PC (NFR-04, AMD-07, ADR-007). The speech model and the language model
are never in memory together:

    recording starts  -> free the language model, then load Whisper in the background
                         (it takes 1 to 2 s and the clinician is talking anyway)
    recording stops   -> transcribe, then free Whisper at once
    draft requested   -> Ollama loads MedGemma into the memory Whisper gave back
"""

# This file builds the whole running program. It creates each real part (recorder, Whisper,
# MedGemma, vault, audit log) and hands them to the screens in one Services bundle. Other
# files never create these parts themselves, so tests can swap in fakes. It also holds the
# small helper classes the admin screen calls, so the screens never import security code.
from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

from clinassist.config import AppConfig
from clinassist.controller import ConsultationController
from clinassist.ports import Auditor, InputGuard, NoteGenerator, Recorder, SessionStore


# Sits between the controller and the two models. The controller just calls record and
# transcribe; this class quietly loads and unloads models so only one is in memory at a time.
class SequentialModels:
    """Wraps the recorder, transcriber and generator so the memory plan above happens without
    the controller knowing about it. `log` records the order of steps, for the tests."""

    # Keep both models but do not load either here. They load and unload on demand.
    def __init__(self, transcriber, generator) -> None:
        self._transcriber = transcriber
        self._generator = generator
        # The background thread that loads Whisper while the clinician is speaking (None if not
        # started).
        self._preload: threading.Thread | None = None
        self.log: list[str] = []

    # Called when recording starts. Frees MedGemma, then loads Whisper in the background.
    def before_recording(self) -> None:
        self._generator.unload()  # free MedGemma first
        self.log.append("llm_unloaded")
        # Load Whisper while the clinician speaks. A failure here (for example a missing model)
        # is not lost: transcribe() calls load() again and raises the proper error then.
        # daemon=True so this thread cannot keep the program open when the user closes the window.
        self._preload = threading.Thread(target=self._safe_preload, daemon=True)
        self._preload.start()

    @property
    # The transcriber's model name for the screen. getattr gives "" if a fake has no such field.
    def model_name(self) -> str:
        return getattr(self._transcriber, "model_name", "")

    @property
    def last_info(self):
        """Facts about the last transcription (language, confidence hint), for the screen."""
        return getattr(self._transcriber, "last_info", None)

    # Runs in the background thread. A failed load is only logged here, never raised.
    def _safe_preload(self) -> None:
        try:
            self._transcriber.load()
            self.log.append("whisper_loaded")
        except Exception:
            self.log.append("whisper_preload_failed")

    # Turns the recorded audio into text. Waits for the background load first, then frees Whisper.
    def transcribe(self, audio: bytes) -> str:
        # If a background load was started, wait for it to finish before using the model.
        if self._preload is not None:
            self._preload.join()
            self._preload = None
        try:
            text = self._transcriber.transcribe(audio)
            self.log.append("transcribed")
            return text
        finally:
            self._transcriber.unload()  # always give the memory back, even after an error
            self.log.append("whisper_unloaded")


# Wraps the real recorder so the controller does not need to know about the memory plan.
class _PlannedRecorder:
    """The real recorder, with the memory plan's first step run before it starts."""

    def __init__(self, recorder: Recorder, plan: SequentialModels) -> None:
        self._recorder, self._plan = recorder, plan

    # Run the memory plan first (free MedGemma, load Whisper), then start the real recording.
    def start(self) -> None:
        self._plan.before_recording()
        self._recorder.start()

    def stop(self) -> bytes:
        return self._recorder.stop()


# Lets the admin install a newer MedGemma from a folder (for example a USB stick), with no internet.
class ModelUpdates:
    """Offline language-model update for the admin screen (FR-10b, model_update.py)."""

    def __init__(self, config, auditor, generator) -> None:
        self._config, self._auditor, self._generator = config, auditor, generator

    @property
    def model(self) -> str:
        return self._config.llm_model

    # Looks at the update folder and reports what it holds, without changing anything.
    def check(self, folder: str):
        from clinassist.model_update import check_update

        return check_update(folder, self._config.llm_model)

    # Installs the update, then writes an audit entry (unless the model was already there).
    def apply(self, folder: str, user_id: str):
        from clinassist.model_update import apply_update

        # Free the model's memory first, so Ollama loads the new files on the next note.
        # Not every generator has unload (fakes may not), so look for it instead of assuming.
        unload = getattr(self._generator, "unload", None)
        if unload:
            unload()
        result = apply_update(folder, self._config.llm_model)
        if not result.already_installed:
            self._auditor.record("language_model_updated", "", user_id)
        return result


# Lets the admin make, check and restore encrypted backups of the vault.
class Backups:
    """Backup and restore for the admin screen (FR-10c, security/backup.py). It lives here so
    the screens never import the security package themselves."""

    # Keep the vault and the audit log; the backup code does the actual work.
    def __init__(self, vault, auditor) -> None:
        self._vault, self._auditor = vault, auditor

    # Suggests a file name for a new backup.
    def default_name(self) -> str:
        from clinassist.security.backup import default_name

        return default_name()

    # Writes a backup of the vault to `path` and records it in the audit log.
    def make(self, path: str, user_id: str):
        from clinassist.security.backup import make_backup

        return make_backup(self._vault, path, user_id, self._auditor)

    # Tests a backup file with the secret, without restoring it, so a bad backup is found early.
    def check(self, path: str, secret: str):
        from clinassist.security.backup import check_backup

        return check_backup(path, secret)

    # Replaces the vault files with the backup. This is audited by the backup code.
    def restore(self, path: str, secret: str, user_id: str):
        from clinassist.security.backup import restore_backup

        return restore_backup(path, self._vault.directory, secret, user_id, self._auditor)

    def close_vault(self) -> None:
        """After a restore the open vault no longer matches the files; forget its key."""
        self._vault.lock()


# Shows the admin how the database is stored (file header, tables, rows) while hiding secrets.
class DatabaseInspector:
    """A read-only view of the vault database for the admin "Database" tab, so the structure and
    the encryption can be shown (for example to an examiner) without any outside database tool.

    It never writes to the database. Password hashes are never shown, and neither is clinical
    text: the tab is for administrators, who run the system but have no need to read patient
    notes (data minimisation, AMD-41). Viewing a table's rows is still written to the audit log."""

    PLAIN_SQLITE_HEADER = b"SQLite format 3\x00"  # how every unencrypted SQLite file begins
    HIDDEN_COLUMNS = frozenset({"password_hash"})
    # Columns holding what was said or written about a patient.
    CLINICAL_COLUMNS = frozenset(
        {"transcript", "subjective", "objective", "assessment", "plan", "diagnosis", "rationale",
         "management"}
    )  # fmt: skip
    # Only the newest 50 rows are fetched per table, so the screen stays quick.
    MAX_ROWS = 50
    MAX_CHARS = 80  # long text is cut short in the row view

    def __init__(self, vault, auditor) -> None:
        self._vault, self._auditor = vault, auditor

    # Reads the first 16 bytes of the file. An unencrypted SQLite file starts with a known text
    # header; an encrypted one looks like random bytes. That is the proof the vault is encrypted.
    def summary(self) -> dict:
        """Facts about the file on disk, read straight from it."""
        from clinassist.security.schema import current_version
        from clinassist.security.vault import DATABASE

        path = self._vault.directory / DATABASE
        with open(path, "rb") as fh:
            first = fh.read(16)
        with self._vault.connect() as conn:
            version = current_version(conn)
            # SQLCipher is the encryption layer for SQLite; this asks which version is loaded.
            cipher = conn.execute("PRAGMA cipher_version").fetchone()
        return {
            "path": str(path),
            "size_bytes": path.stat().st_size,
            "first_bytes_hex": first.hex(" "),
            "plain_header_hex": self.PLAIN_SQLITE_HEADER.hex(" "),
            "readable_without_key": first == self.PLAIN_SQLITE_HEADER,
            "schema_version": version,
            "cipher_version": cipher[0] if cipher else "",
        }

    # Lists all real tables. The sqlite_ ones are SQLite's own and are left out.
    def tables(self) -> list[dict]:
        """Every table: name, row count, columns and the statement that created it."""
        with self._vault.connect() as conn:
            found = conn.execute(
                "SELECT name, sql FROM sqlite_master WHERE type = 'table'"
                " AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
            result = []
            for name, sql in found:
                # The name comes from sqlite_master itself, never from the screen, so it is safe
                # to quote into the statement.
                count = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
                columns = [(row[1], row[2]) for row in conn.execute(f'PRAGMA table_info("{name}")')]
                result.append({"name": name, "rows": count, "columns": columns, "sql": sql})
        return result

    # Returns the column names and rows of one table, with secrets and clinical text replaced.
    def rows(self, table: str, user_id: str) -> tuple[list[str], list[tuple]]:
        """The first rows of `table`, newest first where the table has an order, text cut short
        and password hashes hidden. Only a table that exists can be asked for."""
        # Only table names found in the database are accepted, which stops anyone passing a made-up
        # name into the SQL below.
        known = {t["name"]: t for t in self.tables()}
        if table not in known:
            raise ValueError("unknown_table")
        # Looking at rows is itself recorded in the audit log.
        self._auditor.record("database_rows_viewed", "", user_id)
        columns = [c[0] for c in known[table]["columns"]]
        # ORDER BY rowid DESC puts the newest rows first.
        with self._vault.connect() as conn:
            raw = conn.execute(
                f'SELECT * FROM "{table}" ORDER BY rowid DESC LIMIT {self.MAX_ROWS}'
            ).fetchall()
        # Build each row, replacing hidden and clinical columns with a placeholder before display.
        shown = [
            tuple(
                "(hidden)"
                if col in self.HIDDEN_COLUMNS
                else "(clinical text: not shown)"
                if col in self.CLINICAL_COLUMNS
                else self._short(value)
                for col, value in zip(columns, row, strict=True)
            )
            for row in raw
        ]
        return columns, shown

    # Shortens one cell: None becomes empty text, line breaks are squashed, long text is cut.
    def _short(self, value) -> str:
        text = "" if value is None else str(value)
        text = " ".join(text.split())  # one line per cell
        return text if len(text) <= self.MAX_CHARS else text[: self.MAX_CHARS - 1] + "\u2026"


# Gives the admin counts and times (not patient text) for the Reports tab.
class Reports:
    """System reports for the admin "Reports" tab: counts and times only, never patient text
    (reports.py). Saving one as a CSV file is written to the audit log."""

    def __init__(self, vault, auditor) -> None:
        self._vault, self._auditor = vault, auditor

    # Builds the report for the chosen period.
    def build(self, period: str):
        from clinassist.reports import build_report

        return build_report(self._vault, period)

    # Saves a report to a CSV file and records that in the audit log.
    def save_csv(self, report, path: str, user_id: str) -> None:
        from clinassist.reports import to_csv

        # utf-8-sig so Excel on Windows reads names with accents correctly.
        Path(path).write_text(to_csv(report), encoding="utf-8-sig", newline="")
        self._auditor.record("report_exported", "", user_id)


# Carries progress from the generator to the screen. The generator is built before the screen
# exists, so this object is the link: the screen sets `listener` later.
class ProgressRelay:
    """Passes the generator's progress (a growing count of pieces received) to whoever is
    listening, usually the interface's progress bar."""

    def __init__(self) -> None:
        self.listener = None

    # Calling the relay passes the number on, if a screen is listening.
    def __call__(self, pieces: int) -> None:
        if self.listener is not None:
            self.listener(pieces)


# Switches the Windows Firewall rules off and on from the admin screen.
class OfflineProtection:
    """The Windows Firewall rules, switched off and on from the admin screen (NFR-01, ADR-010).

    Turning them off lets other programs on the PC use the internet, for example to install
    software. The application's own network guard is not affected, so the app stays offline
    either way. Each request is audited; Windows asks the administrator to confirm."""

    # `request` and `read_rules` can be replaced in tests so no real firewall is touched.
    def __init__(self, auditor, request=None, read_rules=None) -> None:
        from clinassist.airgap import firewall_rules, request_firewall_rules

        self._auditor = auditor
        self._request = request or request_firewall_rules
        self._read = read_rules or firewall_rules

    # True if a firewall rule for this program exists.
    def is_on(self) -> bool:
        """Whether the rule for this program is set (the Ollama rules are not checked here)."""
        return bool(self._read())

    # Sets or removes the rules, and records the request in the audit log.
    def switch(self, on: bool, user_id: str) -> bool:
        """Ask Windows to set (on) or delete (off) the rules. True if Windows took the request.
        The audit entry says which: requested, or refused (Windows would not run it)."""
        sent = self._request(remove=not on)
        outcome = "requested" if sent else "refused"
        self._auditor.record(f"offline_protection_{'on' if on else 'off'}_{outcome}", "", user_id)
        return sent


# A plain data holder (dataclass): every part the screens need, made once after login.
@dataclass
class Services:
    """Everything the interface needs, built once after the vault is unlocked."""

    config: AppConfig
    recorder: Recorder
    microphone: object  # the unwrapped recorder: level meter and elapsed time for the screen
    progress: ProgressRelay
    plan: SequentialModels
    guard: InputGuard
    generator: NoteGenerator
    store: SessionStore
    auditor: Auditor
    auth: object  # AuthService; typed loosely to keep this module free of the security imports
    backups: Backups | None = None  # backup and restore, for the admin screen (FR-10c)
    models: ModelUpdates | None = None  # offline model update, for the admin screen (FR-10b)
    database: DatabaseInspector | None = None  # read-only view for the Database tab
    reports: Reports | None = None  # usage counts for the Reports tab
    protection: OfflineProtection | None = None  # firewall rules off and on, for the admin screen

    # Makes one new controller for each consultation, so no state leaks between patients.
    def new_controller(self) -> ConsultationController:
        """A fresh controller for each consultation."""
        return ConsultationController(
            recorder=self.recorder,
            transcriber=self.plan,
            guard=self.guard,
            generator=self.generator,
            store=self.store,
            auditor=self.auditor,
        )


# The composition root function. Called after the vault is unlocked.
def build(config: AppConfig, vault, *, recorder=None, transcriber=None, generator=None):
    """Connect the real parts. The keyword arguments replace a part, for tests and for the
    scripted evaluation (for example a recorder that plays a WAV file)."""
    from clinassist.adapters.input_guard import PatternInputGuard
    from clinassist.adapters.soap_generator import GeneratorSettings, SoapGenerator
    from clinassist.adapters.store import VaultSessionStore
    from clinassist.security.audit import HashChainAuditor
    from clinassist.security.auth import AuthService

    # Without a supplied recorder, use the real microphone one. Imported here so tests that
    # pass a fake do not need the sound library.
    if recorder is None:
        from clinassist.adapters.recorder import SoundDeviceRecorder

        recorder = SoundDeviceRecorder(device=config.microphone)
    # Same for the speech model: only import Whisper when it is really used.
    if transcriber is None:
        from clinassist.adapters.transcriber import WhisperTranscriber

        transcriber = WhisperTranscriber(config.whisper_dir())
    progress = ProgressRelay()
    # The progress relay is passed to the generator so the screen can show a progress bar.
    if generator is None:
        generator = SoapGenerator(
            GeneratorSettings(
                model=config.llm_model,
                host=config.ollama_host,
                include_suggestions=config.ai_suggestions,
            ),
            progress=progress,
        )

    plan = SequentialModels(transcriber, generator)
    auditor = HashChainAuditor(vault)
    # recorder is wrapped so the memory plan runs; microphone keeps the raw one for the level meter.
    return Services(
        config=config,
        recorder=_PlannedRecorder(recorder, plan),
        microphone=recorder,
        progress=progress,
        plan=plan,
        guard=PatternInputGuard(),
        generator=generator,
        store=VaultSessionStore(vault),
        auditor=auditor,
        auth=AuthService(vault, auditor),
        backups=Backups(vault, auditor),
        models=ModelUpdates(config, auditor, generator),
        protection=OfflineProtection(auditor),
        database=DatabaseInspector(vault, auditor),
        reports=Reports(vault, auditor),
    )


# A stand-in recorder for demos and tests: it returns a WAV file instead of using a microphone.
class WavFileRecorder:
    """A Recorder that "records" by returning a WAV file. Used by the scripted evaluation and
    demonstrations with synthetic audio; never by the real interface."""

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)

    def start(self) -> None:
        return None

    def stop(self) -> bytes:
        return self._path.read_bytes()
