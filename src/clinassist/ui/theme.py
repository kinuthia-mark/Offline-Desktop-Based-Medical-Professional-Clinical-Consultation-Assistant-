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

# The identity comes from the clinic itself: register green (the colour of the MOH registers and
# facility signage) for actions, and record ink (a deep blue-slate) for the sidebar and headings,
# on a cool clinic grey. Amber is kept for AI-generated text only.
LIGHT = {
    "bg": "#eef2f4",
    "surface": "#ffffff",
    "input": "#ffffff",
    "text": "#13262f",
    "muted": "#526570",
    "border": "#d3dde2",
    "primary": "#0a6b47",
    "primary_hover": "#08583a",
    "primary_text": "#ffffff",
    "danger": "#b42318",
    "selection": "#d6ebe1",
    "control_border": "#6b7f89",  # outline of text boxes and buttons: at least 3:1 (WCAG 1.4.11)
    "primary_button": "#0a6b47",  # behind white button text: at least 4.5:1
    "ai": "#8a5a00",
    "error": "#b42318",
    "ok": "#0a6b47",
    "warn": "#8a5a00",
    "quiet": "#526570",
    # The sidebar, in record ink
    "ink": "#12303f",
    "ink_text": "#e6eef2",
    "ink_muted": "#a9bdc7",
    "ink_selected": "#1f4659",
    "ink_mark": "#5cc79a",  # the selected item's edge: register green, lightened for the ink
}
DARK = {
    "bg": "#0f1a20",
    "surface": "#16242c",
    "input": "#121e25",
    "text": "#e3ecef",
    "muted": "#9ab0ba",
    "border": "#2b3d47",
    "primary": "#46b98a",
    "primary_hover": "#3aa37a",
    "primary_text": "#ffffff",
    "danger": "#f2766c",
    "selection": "#1f4a3a",
    "control_border": "#6d8591",
    # The light green is too pale behind white text in the dark version, so buttons use a deeper
    # green (over 4.5:1); titles and marks keep the lighter green, which passes as text.
    "primary_button": "#1d7350",
    "ai": "#e0a33a",
    "error": "#f2766c",
    "ok": "#4cc28a",
    "warn": "#e0a33a",
    "quiet": "#9ab0ba",
    "ink": "#09141a",
    "ink_text": "#dbe6eb",
    "ink_muted": "#8fa6b1",
    "ink_selected": "#17323f",
    "ink_mark": "#46b98a",
}
TONES = ("ai", "error", "ok", "warn", "quiet")


def stylesheet(c: dict) -> str:
    return f"""
QWidget {{ font-family: "Segoe UI"; font-size: 10pt; color: {c["text"]}; }}
QMainWindow, QDialog {{ background: {c["bg"]}; }}

/* Header: plain white strip with the name in the signage face; no coloured bar. */
#appHeader {{ background: {c["surface"]}; border-bottom: 1px solid {c["border"]}; }}
#appTitle {{
    font-family: "Bahnschrift"; font-size: 14pt; font-weight: 600; color: {c["text"]};
}}
#appUser {{
    color: {c["text"]}; background: {c["bg"]}; border: 1px solid {c["border"]};
    border-radius: 3px; padding: 3px 10px;
}}
#toast, #notice {{
    color: {c["text"]}; background: {c["surface"]}; border: 1px solid {c["border"]};
    border-left: 5px solid {c["primary"]}; border-radius: 3px; padding: 10px 14px;
    font-weight: 600;
}}

/* The sidebar: record ink, like the index tabs of a patient file. */
#sideNav {{ background: {c["ink"]}; }}
#sideNav QLabel {{ color: {c["ink_muted"]}; font-size: 9pt; }}
#navItem {{
    font-family: "Bahnschrift"; font-size: 11pt; text-align: left;
    color: {c["ink_text"]}; background: transparent; border: none;
    border-left: 4px solid transparent; border-radius: 0; padding: 11px 16px;
}}
#navItem:hover {{ background: {c["ink_selected"]}; }}
#navItem:checked {{
    background: {c["ink_selected"]}; color: #ffffff; border-left: 4px solid {c["ink_mark"]};
}}
#navItem:focus {{ border: 2px solid {c["ink_mark"]}; }}
QTabWidget#mainTabs::pane {{ border: none; background: transparent; }}

/* Panels are flat sheets with a hairline edge, titled in the signage face. */
QGroupBox {{
    background: {c["surface"]}; border: 1px solid {c["border"]}; border-radius: 4px;
    margin-top: 20px; padding: 14px 10px 10px 10px;
}}
QGroupBox::title {{
    subcontrol-origin: margin; left: 2px; padding: 0 2px; color: {c["text"]};
    font-family: "Bahnschrift"; font-size: 11pt; font-weight: 600;
}}
QGroupBox QLabel {{ font-weight: normal; }}

QPushButton {{
    font-family: "Bahnschrift"; font-size: 10pt;
    background: {c["surface"]}; border: 1px solid {c["control_border"]}; border-radius: 4px;
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

/* Tabs inside a panel (SOAP note, Diagnostics): an underline, not a folder tab. */
QTabWidget::pane {{
    border: 1px solid {c["border"]}; border-radius: 4px; background: {c["surface"]}; top: -1px;
}}
QTabBar::tab {{
    font-family: "Bahnschrift"; background: transparent; color: {c["muted"]};
    padding: 7px 16px; margin-right: 4px; border: none; border-bottom: 3px solid transparent;
}}
QTabBar::tab:selected {{ color: {c["text"]}; border-bottom: 3px solid {c["primary"]}; }}
QTabBar::tab:hover:!selected {{ color: {c["text"]}; }}

QPlainTextEdit, QTextEdit, QLineEdit, QListWidget, QTableWidget, QComboBox {{
    background: {c["input"]}; border: 1px solid {c["control_border"]}; border-radius: 4px;
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
/* Row numbers and the corner above them took Qt's default dark fill in both themes. */
QTableCornerButton::section {{ background: {c["bg"]}; border: none; }}
QHeaderView::section:vertical {{ border-bottom: none; border-right: 1px solid {c["border"]}; }}

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
