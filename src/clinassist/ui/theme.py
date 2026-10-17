"""The look of the whole program: one stylesheet, in a light and a dark version.

The version follows the Windows setting (light or dark mode) and switches when the setting
changes. Colours come from one small table per version, so every screen uses the same teal
brand colour, the same panels and the same buttons.

Buttons mark their role with a property instead of their own styles:
    kind = "primary"   the main step on a screen (Start recording, Approve, Finalize and save)
    kind = "danger"    an action that throws work away (Discard consultation)
Everything else is a normal button. `mark(button, kind)` sets it.

Text colours with a meaning (AI-generated amber, error red, network status) stay on the labels
that use them; they were chosen to be readable on both versions.
"""

from __future__ import annotations

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
}


def stylesheet(c: dict) -> str:
    return f"""
QWidget {{ font-size: 10pt; color: {c["text"]}; }}
QMainWindow, QDialog {{ background: {c["bg"]}; }}

#appHeader {{ background: {c["surface"]}; border-bottom: 3px solid {c["primary"]}; }}
#appTitle {{ font-size: 13pt; font-weight: 700; color: {c["primary"]}; }}
#appUser {{ color: {c["muted"]}; }}

QGroupBox {{
    background: {c["surface"]}; border: 1px solid {c["border"]}; border-radius: 8px;
    margin-top: 16px; padding: 12px 10px 10px 10px; font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin; left: 12px; padding: 0 4px; color: {c["primary"]};
}}
QGroupBox QLabel {{ font-weight: normal; }}

QPushButton {{
    background: {c["surface"]}; border: 1px solid {c["border"]}; border-radius: 6px;
    padding: 6px 14px; min-height: 18px;
}}
QPushButton:hover {{ border-color: {c["primary"]}; }}
QPushButton:pressed {{ background: {c["selection"]}; }}
QPushButton:disabled {{ color: {c["muted"]}; background: {c["bg"]}; border-color: {c["border"]}; }}
QPushButton[kind="primary"] {{
    background: {c["primary"]}; color: {c["primary_text"]}; border: 1px solid {c["primary"]};
    font-weight: 600;
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
    background: {c["input"]}; border: 1px solid {c["border"]}; border-radius: 6px;
    padding: 4px; selection-background-color: {c["selection"]}; selection-color: {c["text"]};
}}
QPlainTextEdit:focus, QTextEdit:focus, QLineEdit:focus, QComboBox:focus {{
    border: 1px solid {c["primary"]};
}}
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


def is_dark() -> bool:
    hints = QGuiApplication.styleHints()
    return hints.colorScheme() == Qt.ColorScheme.Dark


def apply_theme(app) -> None:
    """Style the whole program now, and again whenever Windows switches light or dark mode."""

    def restyle(*_) -> None:
        app.setStyleSheet(stylesheet(DARK if is_dark() else LIGHT))

    restyle()
    QGuiApplication.styleHints().colorSchemeChanged.connect(restyle)


def mark(button, kind: str) -> None:
    """Give a button its role ("primary" or "danger"); the stylesheet does the rest."""
    button.setProperty("kind", kind)
