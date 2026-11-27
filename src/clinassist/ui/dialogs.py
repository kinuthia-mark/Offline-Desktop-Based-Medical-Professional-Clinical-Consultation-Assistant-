"""The windows shown before the main screen: readiness, the vault, and login.

Order at start-up: readiness checks -> create or unlock the vault -> first administrator (only
on a new vault) -> login. Each dialog only collects input; the work is done by the functions
passed in, so the dialogs can be tested without a real vault.
"""

# This file holds every pop-up window shown before the main screen opens: the start-up
# checks, creating or unlocking the encrypted vault, the first admin account, login and
# password changes. Each class is one window. A window only collects what the user types
# and shows errors; the checks and the real work are in the functions it is given.
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
from clinassist.ui.theme import mark
from clinassist.ui.workers import error_code

# Short words for each check result. Words are used, not colours alone, so the list is
# readable by everyone.
_ICON = {"ok": "OK", "warn": "Warning", "fail": "Problem"}


# A password box that shows dots instead of the typed text. Used by every dialog below.
def _password_field() -> QLineEdit:
    field = QLineEdit()
    field.setEchoMode(QLineEdit.EchoMode.Password)
    return field


# The first window: shows whether this computer is ready (model present, firewall set and so on).
class ReadinessDialog(QDialog):
    """Shows the startup checks (NFR-07). Continue is only possible when nothing failed.

    If the firewall rules are missing, a button asks Windows to set them: the user sees the usual
    "allow this app to make changes?" prompt and clicks Yes, with no command line (ADR-010).
    `recheck()` runs the checks again and returns (checks, can_start)."""

    def __init__(self, checks, can_start: bool, recheck=None, fix_network=None) -> None:
        super().__init__()
        self.setWindowTitle("Checking this computer")
        # Keep the two optional functions; they are None in tests or when not needed.
        self._recheck, self._fix_network = recheck, fix_network
        self.items = QListWidget()
        # Whole sentences, not cut off mid-word behind a sideways scroll bar.
        self.items.setWordWrap(True)
        self.setMinimumWidth(560)
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.fix_button = QPushButton("Turn on offline protection")
        self.fix_button.clicked.connect(self.fix)
        self.check_again_button = QPushButton("Check again")
        self.check_again_button.clicked.connect(self.check_again)
        # Continue and Quit buttons. AcceptRole and RejectRole tell Qt which closes the dialog
        # with OK and which with Cancel.
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

    # Redraw the list of checks. Used on the first draw and after every "Check again".
    def show_checks(self, checks, can_start: bool) -> None:
        self.items.clear()
        for c in checks:
            # `c.status` is ok, warn or fail; `check_message` turns the code into plain words.
            self.items.addItem(f"{_ICON[c.status]}: {check_message(c.code)}")
        # Continue is allowed only when no check failed.
        self.continue_button.setEnabled(can_start)
        # Offer the fix button only when the firewall rule is missing and a fixing function exists.
        missing = any(c.code == "firewall_rule_missing" for c in checks)
        self.fix_button.setVisible(missing and self._fix_network is not None)
        self.check_again_button.setVisible(self._recheck is not None)

    # Ask Windows to set the firewall rules. Needs the user to click Yes on the Windows prompt.
    def fix(self) -> None:
        if self._fix_network and self._fix_network():
            self.note.setText(
                "Windows will ask for permission. Click Yes, wait a few seconds, then press "
                "Check again."
            )
        else:
            self.note.setText("Windows did not start the change. Ask an administrator.")

    # Run the checks again after the user has fixed something. `*` unpacks the (checks, can_start)
    # pair into show_checks.
    def check_again(self) -> None:
        if self._recheck:
            self.note.clear()
            self.show_checks(*self._recheck())


# Shown once, on a brand new install, to choose the passphrase that encrypts the vault.
class CreateVaultDialog(QDialog):
    """First run: choose the vault passphrase. `create(passphrase)` returns the recovery code."""

    def __init__(self, create: Callable[[str], str]) -> None:
        super().__init__()
        self.setWindowTitle("Create the encrypted store")
        self._create = create
        # Filled in by submit() so the caller can show the code afterwards.
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

    # Runs when Create is pressed: check both boxes match, then create the vault.
    def submit(self) -> None:
        if self.passphrase.text() != self.repeat.text():
            self.message.setText("The two passphrases do not match.")
            return
        # The vault service raises an error with a code if the passphrase is too weak. The code
        # becomes a plain message.
        try:
            self.recovery_code = self._create(self.passphrase.text())
        except Exception as exc:
            self.message.setText(message_for(error_code(exc)))
            return
        # accept() closes the dialog with an OK result.
        self.accept()


# Shows the recovery code. It is the only way in if the passphrase is forgotten, so the
# user must tick that it is written down before Done is enabled.
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
        # Big fixed-width font so letters and digits are easy to copy by hand. (A style string.)
        self.code_label.setStyleSheet("font: bold 16pt 'Consolas';")
        self.written = QCheckBox("I have written the code down and stored it safely")
        self.done_button = QPushButton("Done")
        # Disabled until the tick box is ticked; the next line links the two.
        self.done_button.setEnabled(False)
        self.written.toggled.connect(self.done_button.setEnabled)
        self.done_button.clicked.connect(self.accept)
        layout = QVBoxLayout(self)
        for w in (text, self.code_label, self.written, self.done_button):
            layout.addWidget(w)


# Opens an existing vault, or sets a new passphrase using the recovery code.
class UnlockDialog(QDialog):
    """Unlock with the passphrase, or set a new passphrase with the recovery code."""

    def __init__(self, unlock: Callable[[str], object], recover: Callable[[str, str], object]):
        super().__init__()
        self.setWindowTitle("Unlock the encrypted store")
        self._unlock, self._recover = unlock, recover
        # Set when unlock works, so the caller can use the opened vault.
        self.vault = None
        self.passphrase = _password_field()
        self.recovery = QLineEdit()
        self.new_passphrase = _password_field()
        self.message = QLabel()
        self.message.setWordWrap(True)
        unlock_button = QPushButton("Unlock")
        # `mark` tags the button so the theme styles it as the main button.
        mark(unlock_button, "primary")
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

    # Normal unlock path. The lambda delays the call until _attempt runs it inside its try block.
    def submit(self) -> None:
        self._attempt(lambda: self._unlock(self.passphrase.text()))

    # Recovery path: the recovery code proves who they are and sets a new passphrase.
    def submit_recovery(self) -> None:
        self._attempt(lambda: self._recover(self.recovery.text(), self.new_passphrase.text()))

    # Shared by both paths: run the function, and on failure show the message and clear the
    # passphrase so it is not left on screen.
    def _attempt(self, fn) -> None:
        try:
            self.vault = fn()
        except Exception as exc:
            self.message.setText(message_for(error_code(exc)))
            self.passphrase.clear()
            return
        self.accept()


# Creates the first administrator, so there is someone who can make the clinicians' accounts.
class FirstAdminDialog(QDialog):
    """A new vault has no accounts yet; the first one is an administrator."""

    def __init__(self, create: Callable[[str, str, str], object]) -> None:
        super().__init__()
        self.setWindowTitle("Create the System Administrator account")
        self._create = create
        self.username = QLineEdit()
        self.display_name = QLineEdit()
        self.password = _password_field()
        self.message = QLabel(
            "The System Administrator runs the system for the facility and creates the "
            "clinicians' accounts."
        )
        self.message.setWordWrap(True)
        button = QPushButton("Create")
        button.clicked.connect(self.submit)
        form = QFormLayout(self)
        form.addRow(self.message)
        form.addRow("Username", self.username)
        form.addRow("Full name", self.display_name)
        form.addRow("Password", self.password)
        form.addRow(button)

    # Create the account. Errors such as a weak password come back as a code.
    def submit(self) -> None:
        try:
            self._create(self.username.text(), self.password.text(), self.display_name.text())
        except Exception as exc:
            self.message.setText(message_for(error_code(exc)))
            return
        self.accept()


# The login window. It does not check passwords itself; it calls `login` and keeps the
# session it returns.
class LoginDialog(QDialog):
    """`login(username, password)` returns the session or raises with a code."""

    def __init__(
        self,
        login: Callable[[str, str], object],
        notice: str = "",
        recover: Callable[[str, str, str], None] | None = None,
    ) -> None:
        """`recover(username, recovery_code, new_password)` enables "Forgot password?"."""
        super().__init__()
        self.setWindowTitle("Log in")
        self._login = login
        self._recover = recover
        self.session = None
        self.username = QLineEdit()
        self.password = _password_field()
        # A notice from the program (logged out, timed out) stands out at the top; problems
        # with what was typed appear at the bottom.
        self.notice = QLabel(notice)
        self.notice.setObjectName("notice")
        self.notice.setWordWrap(True)
        self.notice.setVisible(bool(notice))
        self.message = QLabel()
        self.message.setWordWrap(True)
        button = QPushButton("Log in")
        mark(button, "primary")
        button.clicked.connect(self.submit)
        # Pressing Enter in the password box does the same as clicking Log in.
        self.password.returnPressed.connect(self.submit)
        form = QFormLayout(self)
        form.addRow(self.notice)
        form.addRow("Username", self.username)
        form.addRow("Password", self.password)
        form.addRow(button)
        self.forgot_button = QPushButton("Forgot password?")
        self.forgot_button.clicked.connect(self.forgot)
        self.forgot_button.setVisible(recover is not None)
        form.addRow(self.forgot_button)
        form.addRow(self.message)

    # Open the Forgot password window. `run` can be replaced in tests so no real window opens.
    def forgot(self, run=lambda dialog: dialog.exec()) -> None:
        dialog = RecoverPasswordDialog(self._recover, self.username.text())
        # If the user set a new password, fill the username back in and show a short message.
        if run(dialog) == RecoverPasswordDialog.DialogCode.Accepted:
            self.username.setText(dialog.username.text())
            self.password.clear()
            self.message.setText("Password set. Log in with the new password.")

    # Try the login. On failure show why and clear the password.
    def submit(self) -> None:
        try:
            self.session = self._login(self.username.text(), self.password.text())
        except Exception as exc:
            self.message.setText(message_for(error_code(exc)))
            self.password.clear()
            return
        self.accept()


# Lets a signed-in user change their own password.
class ChangePasswordDialog(QDialog):
    """Choose a new password. Shown from the header, and straight after login when an
    administrator has reset the password (the user must replace the temporary one)."""

    def __init__(self, change: Callable[[str, str], None], notice: str = "") -> None:
        """`change(current, new)` changes the password or raises with a code."""
        super().__init__()
        self.setWindowTitle("Change your password")
        self._change = change
        self.current = _password_field()
        self.new = _password_field()
        self.repeat = _password_field()
        self.message = QLabel(notice)
        self.message.setWordWrap(True)
        button = QPushButton("Change password")
        button.clicked.connect(self.submit)
        self.repeat.returnPressed.connect(self.submit)
        form = QFormLayout(self)
        form.addRow(self.message)
        form.addRow("Current password", self.current)
        form.addRow("New password", self.new)
        form.addRow("New password again", self.repeat)
        form.addRow(button)

    # Both new boxes must match before the change is tried.
    def submit(self) -> None:
        if self.new.text() != self.repeat.text():
            self.message.setText(message_for("passwords_do_not_match"))
            return
        try:
            self._change(self.current.text(), self.new.text())
        except Exception as exc:
            self.message.setText(message_for(error_code(exc)))
            return
        self.accept()


# Self-service reset using the recovery code, for when no administrator can help.
class RecoverPasswordDialog(QDialog):
    """Forgotten login password, with nobody else to reset it: the vault's recovery code (shown
    once when the vault was created) lets the user set a new password, fully offline."""

    def __init__(self, recover: Callable[[str, str, str], None], username: str = "") -> None:
        super().__init__()
        self.setWindowTitle("Forgot password")
        self._recover = recover
        self.username = QLineEdit(username)
        self.recovery = QLineEdit()
        self.new = _password_field()
        self.repeat = _password_field()
        self.message = QLabel(
            "Ask an administrator to reset your password. If that is not possible, enter the "
            "recovery code that was shown when this program was first set up."
        )
        self.message.setWordWrap(True)
        button = QPushButton("Set new password")
        button.clicked.connect(self.submit)
        form = QFormLayout(self)
        form.addRow(self.message)
        form.addRow("Username", self.username)
        form.addRow("Recovery code", self.recovery)
        form.addRow("New password", self.new)
        form.addRow("New password again", self.repeat)
        form.addRow(button)

    # Same match check as above, then the recovery function sets the new password.
    def submit(self) -> None:
        if self.new.text() != self.repeat.text():
            self.message.setText(message_for("passwords_do_not_match"))
            return
        try:
            self._recover(self.username.text(), self.recovery.text(), self.new.text())
        except Exception as exc:
            self.message.setText(message_for(error_code(exc)))
            return
        self.accept()
