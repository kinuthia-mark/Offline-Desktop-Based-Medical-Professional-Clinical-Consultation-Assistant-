"""The look of the whole program: one stylesheet, in a light and a dark version.

The version follows the Windows setting (light or dark mode) and switches when the setting
changes. Colours come from one small table per version, so every screen uses the same teal
brand colour, the same panels and the same buttons.

Buttons mark their role with a property instead of their own styles:
    kind = "primary"   the main step on a screen (Start recording, Approve, Finalize and save)
    kind = "danger"    an action that throws work away (Discard consultation)
Everything else is a normal button. `mark(button, kind)` sets it.

Labels whose colour carries a meaning say which one with `tone(label, name)`:
    "ai"      AI-generated text (amber)       "error"   something needs attention (red)
    "ok"      a check passed (green)          "warn"    a check needs a look (amber)
    "quiet"   secondary information (grey)
Each has its own shade in each version, so it stays readable on both (ADR-018).

Every text colour here meets WCAG 2.1 AA contrast (at least 4.5:1) on the backgrounds it is
used on, and the outline of text boxes and buttons at least 3:1; `tests/test_ui.py` measures
this from the colour tables, so a change that breaks it fails a test.
"""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication

LIGHT = {
    "bg": "#eef3f3",
    "surface": "#ffffff",
    "input": "#ffffff",
    "text": "#1d2a2a",
    "muted": "#5f7070",
    "border": "#cddbdb",
    "primary": "#0f6e6e",
    "primary_hover": "#0b5959",
    "primary_text": "#ffffff",
    "danger": "#b3261e",
    "selection": "#cfe8e6",
    "control_border": "#6f8584",  # outline of text boxes and buttons: at least 3:1 (WCAG 1.4.11)
    "primary_button": "#0f6e6e",  # behind white button text: at least 4.5:1
    "ai": "#8a5a00",
    "error": "#b3261e",
    "ok": "#1e7a33",
    "warn": "#8a5a00",
    "quiet": "#5f7070",
}
DARK = {
    "bg": "#161d1f",
    "surface": "#1f282a",
    "input": "#182022",
    "text": "#e4ecec",
    "muted": "#93a6a6",
    "border": "#33413f",
    "primary": "#2a9d8f",
    "primary_hover": "#238579",
    "primary_text": "#ffffff",
    "danger": "#ef6b64",
    "selection": "#264845",
    "control_border": "#6f8583",
    # The brand teal is too light behind white text in the dark version (3.3:1), so buttons use
    # a deeper teal (5.5:1); titles and tabs keep the brand teal, which passes as text.
    "primary_button": "#1c756b",
    "ai": "#e0a33a",
    "error": "#f07a73",
    "ok": "#4cc26a",
    "warn": "#e0a33a",
    "quiet": "#93a6a6",
}
TONES = ("ai", "error", "ok", "warn", "quiet")


def stylesheet(c: dict) -> str:
    return f"""
QWidget {{ font-size: 10pt; color: {c["text"]}; }}
QMainWindow, QDialog {{ background: {c["bg"]}; }}

#appHeader {{ background: {c["surface"]}; border-bottom: 3px solid {c["primary"]}; }}
#appTitle {{ font-size: 13pt; font-weight: 700; color: {c["primary"]}; }}
#appUser {{
    color: {c["text"]}; background: {c["bg"]}; border: 1px solid {c["control_border"]};
    border-radius: 11px; padding: 3px 10px;
}}
#toast, #notice {{
    color: {c["text"]}; background: {c["surface"]}; border: 1px solid {c["primary"]};
    border-left: 5px solid {c["primary"]}; border-radius: 6px; padding: 10px 14px;
    font-weight: 600;
}}

QGroupBox {{
    background: {c["surface"]}; border: 1px solid {c["border"]}; border-radius: 8px;
    margin-top: 16px; padding: 12px 10px 10px 10px; font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin; left: 12px; padding: 0 4px; color: {c["primary"]};
}}
QGroupBox QLabel {{ font-weight: normal; }}

QPushButton {{
    background: {c["surface"]}; border: 1px solid {c["control_border"]}; border-radius: 6px;
    padding: 6px 14px; min-height: 18px;
}}
QPushButton:hover {{ border-color: {c["primary"]}; }}
QPushButton:pressed {{ background: {c["selection"]}; }}
QPushButton:disabled {{ color: {c["muted"]}; background: {c["bg"]}; border-color: {c["border"]}; }}
QPushButton[kind="primary"] {{
    background: {c["primary_button"]}; color: {c["primary_text"]};
    border: 1px solid {c["primary_button"]}; font-weight: 600;
}}
QPushButton[kind="primary"]:hover {{ background: {c["primary_hover"]}; }}
QPushButton[kind="primary"]:disabled {{
    background: {c["border"]}; color: {c["muted"]}; border-color: {c["border"]};
}}
QPushButton[kind="danger"] {{ color: {c["danger"]}; border-color: {c["danger"]}; }}
QPushButton[kind="danger"]:disabled {{ color: {c["muted"]}; border-color: {c["border"]}; }}

QTabWidget::pane {{
    border: 1px solid {c["border"]}; border-radius: 8px; background: {c["bg"]}; top: -1px;
}}
QTabBar::tab {{
    background: {c["bg"]}; color: {c["muted"]}; padding: 8px 18px; margin-right: 2px;
    border: 1px solid {c["border"]}; border-bottom: none;
    border-top-left-radius: 6px; border-top-right-radius: 6px;
}}
QTabBar::tab:selected {{
    background: {c["surface"]}; color: {c["primary"]}; font-weight: 600;
    border-top: 3px solid {c["primary"]};
}}
QTabBar::tab:hover:!selected {{ color: {c["text"]}; }}

QPlainTextEdit, QTextEdit, QLineEdit, QListWidget, QTableWidget, QComboBox {{
    background: {c["input"]}; border: 1px solid {c["control_border"]}; border-radius: 6px;
    padding: 4px; selection-background-color: {c["selection"]}; selection-color: {c["text"]};
}}
QPlainTextEdit:focus, QTextEdit:focus, QLineEdit:focus, QComboBox:focus,
QListWidget:focus, QTableWidget:focus {{
    border: 2px solid {c["primary"]};
}}
QPushButton:focus {{ border: 2px solid {c["primary"]}; }}
QPushButton[kind="primary"]:focus {{ border: 2px solid {c["text"]}; }}
QCheckBox:focus, QTabBar::tab:focus {{ outline: 2px solid {c["primary"]}; }}
/* The history checklist is the second clinician gate, so its boxes must be easy to see: the
   default box was a pale outline on the panel. The outline uses the control colour (at least
   3:1, WCAG 1.4.11) and a ticked box fills with the brand teal, which stays at least 3:1 against
   the panel in both versions (the darker button teal does not in the dark one). */
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px; border: 2px solid {c["control_border"]}; border-radius: 3px;
    background: {c["input"]};
}}
QCheckBox::indicator:hover {{ border-color: {c["primary"]}; }}
QCheckBox::indicator:checked {{
    background: {c["primary"]}; border-color: {c["primary"]};
}}
QCheckBox::indicator:disabled {{ border-color: {c["border"]}; background: {c["bg"]}; }}
QLabel[tone="ai"] {{ color: {c["ai"]}; font-weight: 600; }}
QLabel[tone="error"] {{ color: {c["error"]}; }}
QLabel[tone="ok"] {{ color: {c["ok"]}; }}
QLabel[tone="warn"] {{ color: {c["warn"]}; }}
QLabel[tone="quiet"] {{ color: {c["quiet"]}; }}
QPlainTextEdit[readOnly="true"] {{ background: {c["bg"]}; }}
QHeaderView::section {{
    background: {c["bg"]}; color: {c["muted"]}; padding: 5px; border: none;
    border-bottom: 1px solid {c["border"]}; font-weight: 600;
}}
QTableWidget {{ gridline-color: {c["border"]}; }}

QProgressBar {{
    border: 1px solid {c["border"]}; border-radius: 5px; background: {c["input"]};
    text-align: center; min-height: 14px;
}}
QProgressBar::chunk {{ background: {c["primary"]}; border-radius: 4px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {c["border"]}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {c["muted"]}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {c["border"]}; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QSplitter::handle {{ background: {c["bg"]}; width: 6px; }}
QToolTip {{
    background: {c["surface"]}; color: {c["text"]}; border: 1px solid {c["border"]};
}}
"""


# The user's choice of look, shown in the header: follow Windows, or always light or dark.
CHOICES = {"system": "Follow Windows", "light": "Light", "dark": "Dark"}
APPEARANCE_FILE = "appearance.json"  # beside settings.json in the data folder
_current = {"choice": "system", "app": None}


def is_dark() -> bool:
    """Whether the dark version is showing: the user's choice, or Windows' own setting."""
    choice = _current["choice"]
    if choice != "system":
        return choice == "dark"
    hints = QGuiApplication.styleHints()
    return hints.colorScheme() == Qt.ColorScheme.Dark


def _restyle(*_) -> None:
    app = _current["app"]
    if app is not None:
        app.setStyleSheet(stylesheet(DARK if is_dark() else LIGHT))


def apply_theme(app, choice: str = "system") -> None:
    """Style the whole program now, and again whenever Windows switches light or dark mode
    (which matters only while the choice is "system")."""
    _current["app"] = app
    _current["choice"] = choice if choice in CHOICES else "system"
    _restyle()
    QGuiApplication.styleHints().colorSchemeChanged.connect(_restyle)


def set_choice(choice: str) -> None:
    """Switch the look at once, for every open window."""
    if choice not in CHOICES:
        raise ValueError("unknown_theme")
    _current["choice"] = choice
    _restyle()


def current_choice() -> str:
    return _current["choice"]


def load_choice(folder) -> str:
    """The saved choice, or "system" if there is none or the file cannot be read. A look is
    not worth refusing to start over, so a damaged file is ignored."""
    try:
        data = json.loads((Path(folder) / APPEARANCE_FILE).read_text(encoding="utf-8"))
        choice = data.get("theme", "system")
    except (OSError, ValueError, AttributeError):
        return "system"
    return choice if choice in CHOICES else "system"


def save_choice(folder, choice: str) -> None:
    if choice not in CHOICES:
        raise ValueError("unknown_theme")
    path = Path(folder) / APPEARANCE_FILE
    path.write_text(json.dumps({"theme": choice}) + "\n", encoding="utf-8")


def tone(label, name: str) -> None:
    """Give a label a meaning colour ("ai", "error", "ok", "warn", "quiet"); "" removes it. The
    stylesheet picks the shade for the light or dark version."""
    if name and name not in TONES:
        raise ValueError("unknown_tone")
    label.setProperty("tone", name)
    label.style().unpolish(label)  # re-apply the stylesheet now that the property changed
    label.style().polish(label)


def mark(button, kind: str) -> None:
    """Give a button its role ("primary" or "danger"); the stylesheet does the rest."""
    button.setProperty("kind", kind)
