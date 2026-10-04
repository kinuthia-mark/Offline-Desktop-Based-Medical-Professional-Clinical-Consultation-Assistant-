"""The windows shown before the main screen: readiness, the vault, and login.

Order at start-up: readiness checks -> create or unlock the vault -> first administrator (only
on a new vault) -> login. Each dialog only collects input; the work is done by the functions
passed in, so the dialogs can be tested without a real vault.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QVBoxLayout,
)

from clinassist.ui.messages import check_message, message_for
from clinassist.ui.workers import error_code

_ICON = {"ok": "OK", "warn": "Warning", "fail": "Problem"}


def _password_field() -> QLineEdit:
    field = QLineEdit()
    field.setEchoMode(QLineEdit.EchoMode.Password)
    return field


class ReadinessDialog(QDialog):
    """Shows the startup checks (NFR-07). Continue is only possible when nothing failed.

    If the firewall rules are missing, a button asks Windows to set them: the user sees the usual
    "allow this app to make changes?" prompt and clicks Yes, with no command line (ADR-010).
    `recheck()` runs the checks again and returns (checks, can_start)."""

    def __init__(self, checks, can_start: bool, recheck=None, fix_network=None) -> None:
        super().__init__()
        self.setWindowTitle("Checking this computer")
        self._recheck, self._fix_network = recheck, fix_network
        self.items = QListWidget()
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.fix_button = QPushButton("Turn on offline protection")
        self.fix_button.clicked.connect(self.fix)
        self.check_again_button = QPushButton("Check again")
        self.check_again_button.clicked.connect(self.check_again)
        buttons = QDialogButtonBox()
        self.continue_button = buttons.addButton("Continue", QDialogButtonBox.ButtonRole.AcceptRole)
        quit_button = buttons.addButton("Quit", QDialogButtonBox.ButtonRole.RejectRole)
        self.continue_button.clicked.connect(self.accept)
        quit_button.clicked.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Before the first consultation:"))
        layout.addWidget(self.items)
        layout.addWidget(self.fix_button)
        layout.addWidget(self.note)
        layout.addWidget(self.check_again_button)
        layout.addWidget(buttons)
        self.show_checks(checks, can_start)

    def show_checks(self, checks, can_start: bool) -> None:
        self.items.clear()
        for c in checks:
            self.items.addItem(f"{_ICON[c.status]}: {check_message(c.code)}")
        self.continue_button.setEnabled(can_start)
        missing = any(c.code == "firewall_rule_missing" for c in checks)
        self.fix_button.setVisible(missing and self._fix_network is not None)
        self.check_again_button.setVisible(self._recheck is not None)

    def fix(self) -> None:
        if self._fix_network and self._fix_network():
            self.note.setText(
                "Windows will ask for permission. Click Yes, wait a few seconds, then press "
                "Check again."
            )
        else:
            self.note.setText("Windows did not start the change. Ask an administrator.")

    def check_again(self) -> None:
        if self._recheck:
            self.note.clear()
            self.show_checks(*self._recheck())


class CreateVaultDialog(QDialog):
    """First run: choose the vault passphrase. `create(passphrase)` returns the recovery code."""

    def __init__(self, create: Callable[[str], str]) -> None:
        super().__init__()
        self.setWindowTitle("Create the encrypted store")
        self._create = create
        self.recovery_code = ""
        self.passphrase = _password_field()
        self.repeat = _password_field()
        self.message = QLabel(
            "Choose a passphrase of at least 12 characters. A few unrelated words work well."
        )
        self.message.setWordWrap(True)
        create_button = QPushButton("Create")
        create_button.clicked.connect(self.submit)
        form = QFormLayout(self)
        form.addRow(self.message)
        form.addRow("Passphrase", self.passphrase)
        form.addRow("Repeat it", self.repeat)
        form.addRow(create_button)

    def submit(self) -> None:
        if self.passphrase.text() != self.repeat.text():
            self.message.setText("The two passphrases do not match.")
            return
        try:
            self.recovery_code = self._create(self.passphrase.text())
        except Exception as exc:
            self.message.setText(message_for(error_code(exc)))
            return
        self.accept()


class RecoveryCodeDialog(QDialog):
    """Shows the recovery code once. Closing needs a tick that it has been written down."""

    def __init__(self, code: str) -> None:
        super().__init__()
        self.setWindowTitle("Recovery code: write it down now")
        text = QLabel(
            "If the passphrase is ever forgotten, this code is the only way back into the "
            "records. It will not be shown again. Write it on paper and keep it locked away, "
            "not on this computer."
        )
        text.setWordWrap(True)
        self.code_label = QLabel(code)
        self.code_label.setStyleSheet("font: bold 16pt 'Consolas';")
        self.written = QCheckBox("I have written the code down and stored it safely")
        self.done_button = QPushButton("Done")
        self.done_button.setEnabled(False)
        self.written.toggled.connect(self.done_button.setEnabled)
        self.done_button.clicked.connect(self.accept)
        layout = QVBoxLayout(self)
        for w in (text, self.code_label, self.written, self.done_button):
            layout.addWidget(w)


class UnlockDialog(QDialog):
    """Unlock with the passphrase, or set a new passphrase with the recovery code."""

    def __init__(self, unlock: Callable[[str], object], recover: Callable[[str, str], object]):
        super().__init__()
        self.setWindowTitle("Unlock the encrypted store")
        self._unlock, self._recover = unlock, recover
        self.vault = None
        self.passphrase = _password_field()
        self.recovery = QLineEdit()
        self.new_passphrase = _password_field()
        self.message = QLabel()
        self.message.setWordWrap(True)
        unlock_button = QPushButton("Unlock")
        recover_button = QPushButton("Use recovery code and set a new passphrase")
        unlock_button.clicked.connect(self.submit)
        recover_button.clicked.connect(self.submit_recovery)
        form = QFormLayout(self)
        form.addRow("Passphrase", self.passphrase)
        form.addRow(unlock_button)
        form.addRow(QLabel("Forgotten passphrase:"))
        form.addRow("Recovery code", self.recovery)
        form.addRow("New passphrase", self.new_passphrase)
        form.addRow(recover_button)
        form.addRow(self.message)

    def submit(self) -> None:
        self._attempt(lambda: self._unlock(self.passphrase.text()))

    def submit_recovery(self) -> None:
        self._attempt(lambda: self._recover(self.recovery.text(), self.new_passphrase.text()))

    def _attempt(self, fn) -> None:
        try:
            self.vault = fn()
        except Exception as exc:
            self.message.setText(message_for(error_code(exc)))
            self.passphrase.clear()
            return
        self.accept()


class FirstAdminDialog(QDialog):
    """A new vault has no accounts yet; the first one is an administrator."""

    def __init__(self, create: Callable[[str, str, str], object]) -> None:
        super().__init__()
        self.setWindowTitle("Create the administrator account")
        self._create = create
        self.username = QLineEdit()
        self.display_name = QLineEdit()
        self.password = _password_field()
        self.message = QLabel("This account can create the clinicians' accounts.")
        self.message.setWordWrap(True)
        button = QPushButton("Create")
        button.clicked.connect(self.submit)
        form = QFormLayout(self)
        form.addRow(self.message)
        form.addRow("Username", self.username)
        form.addRow("Full name", self.display_name)
        form.addRow("Password", self.password)
        form.addRow(button)

    def submit(self) -> None:
        try:
            self._create(self.username.text(), self.password.text(), self.display_name.text())
        except Exception as exc:
            self.message.setText(message_for(error_code(exc)))
            return
        self.accept()


class LoginDialog(QDialog):
    """`login(username, password)` returns the session or raises with a code."""

    def __init__(self, login: Callable[[str, str], object], notice: str = "") -> None:
        super().__init__()
        self.setWindowTitle("Log in")
        self._login = login
        self.session = None
        self.username = QLineEdit()
        self.password = _password_field()
        self.message = QLabel(notice)
        self.message.setWordWrap(True)
        button = QPushButton("Log in")
        button.clicked.connect(self.submit)
        self.password.returnPressed.connect(self.submit)
        form = QFormLayout(self)
        form.addRow("Username", self.username)
        form.addRow("Password", self.password)
        form.addRow(button)
        form.addRow(self.message)

    def submit(self) -> None:
        try:
            self.session = self._login(self.username.text(), self.password.text())
        except Exception as exc:
            self.message.setText(message_for(error_code(exc)))
            self.password.clear()
            return
        self.accept()
