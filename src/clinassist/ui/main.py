"""The desktop application: start-up sequence and main window.

    python -m clinassist.ui

Start-up: readiness checks -> create or unlock the vault -> first administrator (new vault only)
-> login -> main window. This file and app.py are the only places that build real parts; the
screens receive them ready-made.

Idle timeout (FR-08): any key press or mouse click counts as activity. After 10 minutes without
activity the window is covered by the login dialog. If the same person logs back in, they carry on
where they were; if someone else logs in, the open consultation is discarded first, so one
clinician never sees another's unfinished notes.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from clinassist.controller import State
from clinassist.ui.admin import AdminView
from clinassist.ui.dialogs import (
    CreateVaultDialog,
    FirstAdminDialog,
    LoginDialog,
    ReadinessDialog,
    RecoveryCodeDialog,
    UnlockDialog,
)
from clinassist.ui.messages import message_for
from clinassist.ui.records import RecordsView
from clinassist.ui.workspace import ConsultationWorkspace

APP_TITLE = "Offline Clinical Consultation Assistant"


class _ActivityFilter(QObject):
    """Counts any key press or mouse click anywhere in the app as activity."""

    def __init__(self, on_activity) -> None:
        super().__init__()
        self._on_activity = on_activity

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 - Qt's name
        if event.type() in (QEvent.Type.KeyPress, QEvent.Type.MouseButtonPress):
            self._on_activity()
        return False  # never swallow the event


class MainWindow(QMainWindow):
    def __init__(
        self, services, session, login_again, checks_summary: str = "", network=("warn", "")
    ) -> None:
        """`login_again(notice)` shows the login dialog and returns a session or None."""
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self._services, self.session, self._login_again = services, session, login_again
        auth = services.auth

        self.user_label = QLabel()
        self.status_label = QLabel(checks_summary)
        # FR-18: the network label says only what the start-up check found (ADR-010).
        status, label = network
        self.network_label = QLabel(label)
        # Readable on light and dark Windows themes.
        colour = {"ok": "#2e9e44", "warn": "#c98a00", "fail": "#e0484d"}.get(status, "#888")
        self.network_label.setStyleSheet(f"color: {colour}; font-weight: bold;")
        logout = QPushButton("Log out")
        logout.clicked.connect(self.log_out)
        header = QHBoxLayout()
        title = QLabel(APP_TITLE)
        title.setStyleSheet("font-weight: bold;")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.network_label)
        header.addWidget(self.status_label)
        header.addWidget(self.user_label)
        header.addWidget(logout)

        self.workspace = ConsultationWorkspace(
            services, user_id=lambda: self.session.user_id, before_action=self.require
        )
        self.records = RecordsView(services.store, before_action=self.require)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.workspace, "Consultation")
        self.tabs.addTab(self.records, "Session records")
        self.admin = AdminView(
            services.auditor,
            auth,
            admin_session=lambda: self.session,
            backups=services.backups,
            on_restored=self._restored,
        )
        self.admin_index = self.tabs.addTab(self.admin, "Audit and accounts")
        self.tabs.currentChanged.connect(self._tab_opened)

        body = QWidget()
        layout = QVBoxLayout(body)
        layout.addLayout(header)
        layout.addWidget(self.tabs, 1)
        self.setCentralWidget(body)
        self._show_user()

        self._activity = _ActivityFilter(self._touch)
        QApplication.instance().installEventFilter(self._activity)
        # Check for idleness every 15 seconds; the timeout itself is 10 minutes.
        self.idle_timer = QTimer(self)
        self.idle_timer.setInterval(15_000)
        self.idle_timer.timeout.connect(self.check_idle)
        self.idle_timer.start()

    # ----- login state -----
    def require(self) -> None:
        """Called before every action; raises session_expired after the idle timeout."""
        self._services.auth.require(self.session)

    def _touch(self) -> None:
        if not self.session.expired(datetime.now(UTC)):
            self.session.last_active = datetime.now(UTC)

    def check_idle(self) -> None:
        if self.session.expired(datetime.now(UTC)):
            self.lock_screen(message_for("session_expired"))

    def lock_screen(self, notice: str) -> None:
        self._services.auth.logout(self.session)
        previous = self.session.user_id
        self.hide()
        session = self._login_again(notice)
        if session is None:
            self.close()
            return
        if session.user_id != previous and self.workspace.controller.state not in (
            State.IDLE,
            State.FINALIZED,
        ):
            self.workspace.controller.discard()  # never show one clinician another's notes
            self.workspace.new_consultation()
        self.session = session
        self._show_user()
        self.show()

    def log_out(self) -> None:
        self.lock_screen("")

    def _show_user(self) -> None:
        self.user_label.setText(f"{self.session.display_name} ({self.session.role})")
        self.tabs.setTabVisible(self.admin_index, self.session.role == "admin")

    def _tab_opened(self, index: int) -> None:
        if self.tabs.widget(index) is self.records:
            self.records.reload()
        elif self.tabs.widget(index) is self.admin and self.session.role == "admin":
            self.admin.reload()

    def _restored(self) -> None:
        """After a restore the open vault no longer matches the files on disk, so the program
        closes. Starting it again opens the restored vault."""
        QMessageBox.information(
            self,
            "Backup restored",
            "The backup was restored. The program will now close. Start it again and unlock "
            "with the passphrase the vault had when the backup was made, or the recovery code.",
        )
        self._services.backups.close_vault()
        QApplication.instance().quit()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt's name
        QApplication.instance().removeEventFilter(self._activity)
        super().closeEvent(event)


def window_icon_path() -> Path:
    """The program's icon: bundled beside the program once installed, in release/art from source."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / "art" / "clinassist.png"
    return Path(__file__).resolve().parents[3] / "release" / "art" / "clinassist.png"


# The name the installer looks for (AppMutex in release/clinassist.iss). Keep the two the same.
RUNNING_MARKER = "ClinAssistRunning"


def hold_running_marker() -> int | None:
    """Tell the installer the program is open, so it asks the user to close it first.

    Windows' automatic "close the applications" step hung the installer on the reference PC
    after the program had already closed. Instead, the program holds a named Windows mutex while
    it runs, and the installer and uninstaller wait until it is gone. Windows releases the mutex
    when the program exits, even after a crash, so there is nothing to clean up."""
    if sys.platform != "win32":
        return None
    import ctypes

    return ctypes.windll.kernel32.CreateMutexW(None, False, RUNNING_MARKER) or None


def main() -> int:
    from clinassist.airgap import LABELS, install_network_guard, request_firewall_rules

    install_network_guard()  # first, before any part of the program can open a connection
    hold_running_marker()
    from clinassist.app import build
    from clinassist.config import AppConfig
    from clinassist.security.vault import KEYRING, Vault
    from clinassist.startup import can_start, run_checks

    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    icon = window_icon_path()
    if icon.is_file():
        app.setWindowIcon(QIcon(str(icon)))
    data_dir = Path(AppConfig().data_dir)
    config = AppConfig.load(data_dir / "settings.json")

    checks = run_checks(config)
    latest = {"checks": checks}

    def recheck():
        latest["checks"] = run_checks(config)
        return latest["checks"], can_start(latest["checks"])

    readiness = ReadinessDialog(checks, can_start(checks), recheck, request_firewall_rules)
    if readiness.exec() != ReadinessDialog.DialogCode.Accepted:
        return 1
    checks = latest["checks"]
    warnings = [c for c in checks if c.status == "warn"]
    summary = f"{len(warnings)} warning(s) at start-up" if warnings else "All checks passed"
    net = next((c for c in checks if c.name == "network"), None)
    network = (
        (net.status, LABELS.get(net.code, net.code)) if net else ("warn", "Network: not checked")
    )

    vault_dir = Path(config.data_dir) / "vault"
    if (vault_dir / KEYRING).exists():
        unlock = UnlockDialog(
            unlock=lambda p: Vault.unlock(vault_dir, p),
            recover=lambda code, new: Vault.recover(vault_dir, code, new),
        )
        if unlock.exec() != UnlockDialog.DialogCode.Accepted:
            return 1
        vault = unlock.vault
    else:
        made = {}

        def create(passphrase: str) -> str:
            made["vault"], code = Vault.create(vault_dir, passphrase)
            return code

        dialog = CreateVaultDialog(create)
        if dialog.exec() != CreateVaultDialog.DialogCode.Accepted:
            return 1
        RecoveryCodeDialog(dialog.recovery_code).exec()
        vault = made["vault"]

    services = build(config, vault)
    if not services.auth.has_users():
        first = FirstAdminDialog(services.auth.create_first_admin)
        if first.exec() != FirstAdminDialog.DialogCode.Accepted:
            return 1

    def login(notice: str = ""):
        dialog = LoginDialog(services.auth.login, notice)
        return dialog.session if dialog.exec() == LoginDialog.DialogCode.Accepted else None

    session = login()
    if session is None:
        return 1
    window = MainWindow(services, session, login, summary, network)
    window.resize(1400, 850)
    window.show()
    code = app.exec()
    vault.lock()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
