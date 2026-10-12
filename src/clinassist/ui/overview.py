"""The administrator's landing page: the state of the system at a glance (AMD-41).

Administrators run the system; they do not see patient notes (data minimisation, section 25 of
the Kenya Data Protection Act 2019). So this page shows only what running the system needs:

- the start-up checks and the network status found when the program started;
- accounts: how many clinicians and administrators, which are turned off or locked;
- the audit log: how many entries, and whether the whole chain checks out;
- backups: when the last one was made, with a reminder if it is old or there is none;
- how many consultations are stored, as a number only.

Buttons lead to the tabs where the work is done. Nothing here changes anything.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from clinassist.ui.messages import message_for
from clinassist.ui.workers import error_code

OK, WARN, FAIL = "#2e9e44", "#c98a00", "#e0484d"  # readable on light and dark themes
BACKUP_REMINDER = timedelta(days=1)  # a clinic should back up at the end of each day


class OverviewView(QWidget):
    def __init__(
        self,
        auth,
        auditor,
        store,
        admin_session: Callable[[], object],
        checks_summary: str = "",
        network=("warn", ""),
        go_to: Callable[[str], None] = lambda name: None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        """`go_to(name)` opens another tab: "accounts" or "database"."""
        super().__init__()
        self._auth, self._auditor, self._store = auth, auditor, store
        self._admin, self._clock = admin_session, clock

        self.system_label = _label()
        status, text = network
        self.system_label.setText(f"{text}\n{checks_summary}".strip())
        self.system_label.setStyleSheet(f"color: {_colour(status)};")
        self.accounts_label = _label()
        self.audit_label = _label()
        self.backup_label = _label()
        self.records_label = _label()
        self.message = _label()

        accounts_button = QPushButton("Manage accounts and the audit log")
        accounts_button.clicked.connect(lambda: go_to("accounts"))
        backup_button = QPushButton("Make a backup")
        backup_button.clicked.connect(lambda: go_to("accounts"))
        database_button = QPushButton("Look inside the database")
        database_button.clicked.connect(lambda: go_to("database"))
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.reload)

        grid = QGridLayout()
        boxes = (
            ("This computer", self.system_label),
            ("Accounts", self.accounts_label),
            ("Audit log", self.audit_label),
            ("Backups", self.backup_label),
            ("Stored consultations", self.records_label),
        )
        for i, (title, label) in enumerate(boxes):
            box = QGroupBox(title)
            QVBoxLayout(box).addWidget(label)
            grid.addWidget(box, i // 2, i % 2)
        buttons = QHBoxLayout()
        for b in (accounts_button, backup_button, database_button, refresh):
            buttons.addWidget(b)
        buttons.addStretch(1)

        layout = QVBoxLayout(self)
        heading = QLabel("Administration overview")
        heading.setStyleSheet("font-size: 16pt; font-weight: bold;")
        layout.addWidget(heading)
        note = QLabel(
            "Administrators manage accounts, the audit log and backups. Patient notes are only "
            "shown to clinicians."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addLayout(grid)
        layout.addLayout(buttons)
        layout.addWidget(self.message)
        layout.addStretch(1)

    def reload(self) -> None:
        try:
            self._auth.require(self._admin(), "admin")
            users = self._auth.list_users(self._admin())
            result = self._auditor.verify()
            events = self._auditor.events(1000)
            stored = len(self._store.session_ids())
        except Exception as exc:
            self.message.setText(message_for(error_code(exc)))
            return
        self.message.clear()

        clinicians = [u for u in users if u["role"] == "clinician"]
        admins = [u for u in users if u["role"] == "admin"]
        off = [u["username"] for u in users if not u["active"]]
        locked = [u["username"] for u in users if u["locked"]]
        lines = [f"{len(clinicians)} clinician(s), {len(admins)} administrator(s)"]
        if off:
            lines.append("Turned off: " + ", ".join(off))
        if locked:
            lines.append("Locked after wrong passwords: " + ", ".join(locked))
        self.accounts_label.setText("\n".join(lines))
        self.accounts_label.setStyleSheet(f"color: {WARN if locked else OK};")

        if result.ok:
            self.audit_label.setText(f"Intact: all {result.checked} entries check out.")
            self.audit_label.setStyleSheet(f"color: {OK};")
        else:
            self.audit_label.setText(
                f"Changed at entry {result.first_bad_seq} ({result.problem.replace('_', ' ')})."
            )
            self.audit_label.setStyleSheet(f"color: {FAIL};")

        last = next((ts for _, ts, event, _, _ in events if event == "backup_created"), None)
        if last is None:
            self.backup_label.setText("No backup has been made yet. Make one today.")
            self.backup_label.setStyleSheet(f"color: {WARN};")
        else:
            age = self._clock() - datetime.fromisoformat(last)
            text = f"Last backup: {last[:16].replace('T', ' ')} UTC"
            if age > BACKUP_REMINDER:
                text += f"\n{age.days} day(s) ago. Make a new one."
            self.backup_label.setText(text)
            self.backup_label.setStyleSheet(f"color: {WARN if age > BACKUP_REMINDER else OK};")

        self.records_label.setText(
            f"{stored} saved consultation(s), encrypted. Their content is only shown to clinicians."
        )


def _label() -> QLabel:
    label = QLabel()
    label.setWordWrap(True)
    return label


def _colour(status: str) -> str:
    return {"ok": OK, "warn": WARN, "fail": FAIL}.get(status, WARN)
