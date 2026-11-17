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

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from clinassist.domain import ADMIN, CLINICIAN, ROLE_LABELS
from clinassist.ui import theme
from clinassist.ui.admin import AdminView
from clinassist.ui.database import DatabaseView
from clinassist.ui.dialogs import (
    ChangePasswordDialog,
    CreateVaultDialog,
    FirstAdminDialog,
    LoginDialog,
    ReadinessDialog,
    RecoveryCodeDialog,
    UnlockDialog,
)
from clinassist.ui.messages import message_for
from clinassist.ui.overview import OverviewView
from clinassist.ui.records import RecordsView
from clinassist.ui.reports import ReportsView
from clinassist.ui.theme import apply_theme, tone
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
        self,
        services,
        session,
        login_again,
        checks_summary: str = "",
        network=("warn", ""),
        confirm_close=None,
    ) -> None:
        """`login_again(notice)` shows the login dialog and returns a session or None."""
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self._services, self.session, self._login_again = services, session, login_again
        self._confirm_close = confirm_close or self._ask_close  # tests replace the dialog
        self._closing = False  # set when the program closes itself and must not ask
        auth = services.auth

        self.user_label = QLabel()
        # The toast: a notice at the top right, beside the tabs (show_toast).
        self.toast = QLabel(self)
        self.toast.setObjectName("toast")
        # Clicks pass through it, so it never covers a button the clinician needs.
        self.toast.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.toast.hide()
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self.toast.hide)
        self.status_label = QLabel(checks_summary)
        # FR-18: the network label says only what the start-up check found (ADR-010).
        status, label = network
        self.network_label = QLabel(label)
        # Readable on light and dark Windows themes.
        # The words say what the check found; the colour repeats it (WCAG 1.4.1).
        tone(self.network_label, {"ok": "ok", "warn": "warn", "fail": "error"}.get(status, "quiet"))
        self.network_label.setStyleSheet("font-weight: bold;")
        logout = QPushButton("Log out")
        logout.clicked.connect(self.log_out)
        self.password_button = QPushButton("Change password")
        self.password_button.clicked.connect(self.change_password)
        # Light, dark, or follow Windows; remembered on this PC for everyone (appearance.json).
        self.theme_box = QComboBox()
        for key, name in theme.CHOICES.items():
            self.theme_box.addItem(name, key)
        self.theme_box.setCurrentIndex(list(theme.CHOICES).index(theme.current_choice()))
        self.theme_box.setToolTip("Appearance: light, dark, or the same as Windows")
        self.theme_box.setAccessibleName("Appearance")
        self.theme_box.currentIndexChanged.connect(self._theme_chosen)
        # The header bar: icon and title on the left; network status, user and account buttons
        # on the right. Styled by ui/theme.py through its object names.
        header_bar = QFrame()
        header_bar.setObjectName("appHeader")
        header = QHBoxLayout(header_bar)
        header.setContentsMargins(14, 8, 14, 8)
        icon_path = window_icon_path()
        if icon_path.is_file():
            logo = QLabel()
            logo.setPixmap(QIcon(str(icon_path)).pixmap(28, 28))
            header.addWidget(logo)
        title = QLabel(APP_TITLE)
        title.setObjectName("appTitle")
        header.addWidget(title)
        self.user_label.setObjectName("appUser")
        header.addStretch(1)
        header.addWidget(self.network_label)
        header.addWidget(self.status_label)
        header.addWidget(self.password_button)
        header.addWidget(logout)

        # Each role gets its own tabs and its own landing page (AMD-41). Clinicians see patient
        # work only; administrators see the system only, never patient notes (data
        # minimisation). The consultation and records actions also check the role themselves,
        # so hiding a tab is not the only protection.
        self.overview = OverviewView(
            auth,
            services.auditor,
            services.store,
            admin_session=lambda: self.session,
            checks_summary=checks_summary,
            network=network,
            go_to=self._go_to,
        )
        self.workspace = ConsultationWorkspace(
            services, user_id=lambda: self.session.user_id, before_action=self.require_clinician
        )
        self.records = RecordsView(
            services.store,
            before_action=self.require_clinician,
            export=self.export_note,
            name_of=lambda user_id: auth.display_name(self.session, user_id),
        )
        self.tabs = QTabWidget()
        self.overview_index = self.tabs.addTab(self.overview, "Overview")
        self.workspace_index = self.tabs.addTab(self.workspace, "Consultation")
        self.records_index = self.tabs.addTab(self.records, "Session records")
        self.admin = AdminView(
            services.auditor,
            auth,
            admin_session=lambda: self.session,
            backups=services.backups,
            models=services.models,
            protection=services.protection,
            on_restored=self._restored,
        )
        self.admin_index = self.tabs.addTab(self.admin, "Audit and accounts")
        self.database = DatabaseView(services.database, auth, admin_session=lambda: self.session)
        self.database_index = self.tabs.addTab(self.database, "Database")
        self.reports = ReportsView(services.reports, auth, session=lambda: self.session)
        self.reports_index = self.tabs.addTab(self.reports, "Reports")
        self.tabs.currentChanged.connect(self._tab_opened)

        # Navigation is a sidebar, like the index tabs of a patient file. The tab widget stays
        # underneath (its bar hidden), so which screens a role sees is decided in one place.
        self.tabs.setObjectName("mainTabs")
        self.tabs.tabBar().hide()
        side = QFrame()
        side.setObjectName("sideNav")
        side.setFixedWidth(200)
        nav = QVBoxLayout(side)
        nav.setContentsMargins(0, 14, 0, 14)
        nav.setSpacing(2)
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: list[QPushButton] = []
        for index in range(self.tabs.count()):
            button = QPushButton(self.tabs.tabText(index))
            button.setObjectName("navItem")
            button.setCheckable(True)
            # Focus only from the keyboard (Tab): a mouse click left a focus box that clashed
            # with the green edge; keyboard users still see where they are.
            button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            button.clicked.connect(lambda _=False, i=index: self.tabs.setCurrentIndex(i))
            self.nav_group.addButton(button)
            self.nav_buttons.append(button)
            nav.addWidget(button)
        nav.addStretch(1)
        # Who is logged in, and the light or dark choice, live at the foot of the sidebar: one
        # place, instead of a badge in the header as well.
        self.role_label = QLabel()
        self.role_label.setWordWrap(True)
        self.role_label.setContentsMargins(16, 0, 12, 6)
        nav.addWidget(self.role_label)
        self.user_label.hide()  # kept for the tests and screen readers; the sidebar shows the user
        theme_row = QHBoxLayout()
        theme_row.setContentsMargins(12, 0, 12, 0)
        theme_row.addWidget(self.theme_box)
        nav.addLayout(theme_row)
        self.tabs.currentChanged.connect(
            lambda i: (
                self.nav_buttons[i].setChecked(True) if 0 <= i < len(self.nav_buttons) else None
            )
        )

        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(header_bar)
        row = QHBoxLayout()
        row.setSpacing(0)
        row.addWidget(side)
        content = QVBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.addWidget(self.tabs, 1)
        row.addLayout(content, 1)
        layout.addLayout(row, 1)
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

    def require_clinician(self) -> None:
        """Before every consultation and records action: also refuses a non-clinician."""
        self._services.auth.require(self.session, "clinician")

    def _touch(self) -> None:
        if not self.session.expired(datetime.now(UTC)):
            self.session.last_active = datetime.now(UTC)

    def check_idle(self) -> None:
        if self.workspace.keeps_session_alive and not self.session.ended:
            # Recording, transcribing or drafting: the clinician is working even without
            # touching the keyboard, so a hands-free consultation is not locked half-way.
            self.session.last_active = datetime.now(UTC)
            return
        if self.session.expired(datetime.now(UTC)):
            self.lock_screen(message_for("session_expired"))

    def lock_screen(self, notice: str) -> None:
        # The idle check is paused while the login dialog is open: the ended session counts
        # as expired, and the timer would otherwise open another login dialog every 15 s.
        self.idle_timer.stop()
        self._services.auth.logout(self.session)
        previous = self.session.user_id
        self.hide()
        session = self._login_again(notice)
        if session is None:
            self._closing = True  # nobody is logged in: close without asking
            self.close()
            return
        if session.user_id != previous and self.workspace.in_progress:
            # Never show one clinician another's consultation, including a draft that was
            # still being written when the screen locked.
            self.workspace.abandon()
        self.session = session
        self._show_user()
        self.show()
        self.idle_timer.start()

    def log_out(self) -> None:
        # The login window that opens says the logout worked, so a clinician leaving the PC
        # can see they are no longer logged in.
        self.lock_screen(f"{self.session.display_name} logged out. Log in to continue.")

    def _theme_chosen(self, _index: int) -> None:
        choice = self.theme_box.currentData()
        theme.set_choice(choice)
        try:
            theme.save_choice(self._services.config.data_dir, choice)
        except OSError:
            self.show_toast("The look changed, but could not be saved for next time.")

    def show_toast(self, text: str, milliseconds: int = 4000) -> None:
        """A short notice at the top right, beside the tabs, that closes by itself, so it never
        stops the clinician (for example "Logged in as Dr A (clinician)")."""
        self.toast.setText(text)
        self.toast.adjustSize()
        self._place_toast()
        self.toast.raise_()
        self.toast.show()
        # At login the window is not laid out yet; place it again once it is.
        QTimer.singleShot(0, self._place_toast)
        self._toast_timer.start(milliseconds)

    def _place_toast(self) -> None:
        # Level with the tab bar, whose right side is empty: the bottom corner covered
        # "Finalize and save".
        margin = 20
        tabs = getattr(self, "tabs", None)
        top = tabs.mapTo(self, tabs.rect().topLeft()).y() if tabs is not None else margin
        self.toast.move(self.width() - self.toast.width() - margin, top)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt's name
        super().resizeEvent(event)
        self._place_toast()

    def export_note(self, session_id: str, path: str, include_transcript: bool) -> str:
        """Write one saved consultation as a PDF (FR-17) and record the export in the audit
        log. Returns where the file was saved."""
        from clinassist.ui.export import ExportDetails, note_html, write_pdf

        auth, store = self._services.auth, self._services.store
        self.require_clinician()
        record = store.load(session_id)
        details = ExportDetails(
            saved_at=store.saved_at(session_id),
            finalized_by=auth.display_name(self.session, record.finalized_by),
            exported_by=self.session.display_name,
            exported_at=datetime.now(UTC).isoformat(timespec="seconds"),
            include_transcript=include_transcript,
        )
        saved = write_pdf(note_html(record, details), path)
        event = "note_exported_with_transcript" if include_transcript else "note_exported"
        self._services.auditor.record(event, session_id, self.session.user_id)
        return str(saved)

    def change_password(self) -> None:
        auth = self._services.auth
        ChangePasswordDialog(lambda old, new: auth.change_password(self.session, old, new)).exec()

    def _show_user(self) -> None:
        """Show the tabs of the logged-in role and open its landing page."""
        label = ROLE_LABELS.get(self.session.role, self.session.role)
        who = f"{self.session.display_name} ({label})"
        self.user_label.setText(f"Logged in as {who}")
        self.show_toast(f"Logged in as {who}")
        # Each role sees only its own screens: clinicians the consultations and the facility's
        # reports, which need a clinical background to read; the system administrator the
        # technical side only (accounts, audit, database). Nobody but a clinician sees notes.
        role = self.session.role
        tabs_for = {
            CLINICIAN: (self.workspace_index, self.records_index, self.reports_index),
            ADMIN: (self.overview_index, self.admin_index, self.database_index),
        }
        mine = tabs_for.get(role, ())
        for index in range(self.tabs.count()):
            self.tabs.setTabVisible(index, index in mine)
            self.nav_buttons[index].setVisible(index in mine)
        self.role_label.setText(f"{self.session.display_name}\n{label}")
        landing = mine[0] if mine else self.workspace_index
        self.nav_buttons[landing].setChecked(True)  # also when it is already the open page
        if self.tabs.currentIndex() == landing:
            self._tab_opened(landing)  # already open: still refresh it for this user
        else:
            self.tabs.setCurrentIndex(landing)

    def _go_to(self, name: str) -> None:
        self.tabs.setCurrentIndex(
            {"accounts": self.admin_index, "database": self.database_index}[name]
        )

    def _tab_opened(self, index: int) -> None:
        role, widget = self.session.role, self.tabs.widget(index)
        if widget is self.overview and role == ADMIN:
            self.overview.reload()
        elif widget is self.records and role == CLINICIAN:
            self.records.reload()
        elif widget is self.admin and role == ADMIN:
            self.admin.reload()
        elif widget is self.database and role == ADMIN:
            self.database.reload()
        elif widget is self.reports and role == CLINICIAN:
            self.reports.reload()

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
        # Closing the window with a consultation on screen would lose it without a word.
        if (
            not self._closing
            and self.workspace.in_progress
            and not self._confirm_close(
                "A consultation is not saved yet. Close the program and discard it?"
            )
        ):
            event.ignore()
            return
        if self.workspace.in_progress:
            self.workspace.abandon()  # releases the microphone and audits the discard
        self.idle_timer.stop()
        QApplication.instance().removeEventFilter(self._activity)
        super().closeEvent(event)

    def _ask_close(self, question: str) -> bool:
        answer = QMessageBox.question(self, "Please confirm", question)
        return answer == QMessageBox.StandardButton.Yes


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


RESET_NOTICE = (
    "An administrator reset your password. Choose a new one that only you know before "
    "continuing. Type the temporary password as the current password."
)


def replace_reset_password(auth, session, run=lambda dialog: dialog.exec()):
    """After login: if an administrator reset this password, the user must replace it before
    the main screen opens. Returns the session, or None (and logs out) if they decline."""
    if not session.must_change_password:
        return session
    dialog = ChangePasswordDialog(
        lambda old, new: auth.change_password(session, old, new), RESET_NOTICE
    )
    if run(dialog) == ChangePasswordDialog.DialogCode.Accepted:
        return session
    auth.logout(session)
    return None


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
    # The saved look applies from the first window (start-up checks, unlock, login).
    apply_theme(app, theme.load_choice(config.data_dir))

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
        dialog = LoginDialog(services.auth.login, notice, recover=services.auth.recover_password)
        if dialog.exec() != LoginDialog.DialogCode.Accepted:
            return None
        return replace_reset_password(services.auth, dialog.session)

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
