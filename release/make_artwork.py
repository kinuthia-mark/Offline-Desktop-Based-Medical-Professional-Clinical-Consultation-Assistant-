"""Draw the installer's side panel, header logo and the program icon (ADR-012).

    python release/make_artwork.py

Writes release/art/: wizard-100.bmp and wizard-200.bmp (the tall panel on the first and last
installer pages, at normal and double screen scaling), small-100.bmp and small-200.bmp (the logo
at the top right of the other pages), and clinassist.ico (the program's icon). Drawn with Qt so
they can be regenerated after any change of colour or name.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import (  # noqa: E402
    QColor,
    QFont,
    QGuiApplication,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
)

OUT = Path(__file__).resolve().parent / "art"
TEAL_DARK = QColor("#0b4f57")
TEAL = QColor("#138591")
WHITE = QColor("#ffffff")
MIST = QColor("#cfe9ec")


def _cross(p: QPainter, cx: float, cy: float, size: float, colour: QColor) -> None:
    """A rounded medical cross centred on (cx, cy)."""
    arm = size / 3
    radius = arm * 0.22
    # Two bars filled one after the other: a single path would leave the overlap empty.
    for rect in (
        QRectF(cx - arm / 2, cy - size / 2, arm, size),
        QRectF(cx - size / 2, cy - arm / 2, size, arm),
    ):
        bar = QPainterPath()
        bar.addRoundedRect(rect, radius, radius)
        p.fillPath(bar, colour)


def _background(p: QPainter, w: int, h: int) -> None:
    gradient = QLinearGradient(0, 0, 0, h)
    gradient.setColorAt(0, TEAL)
    gradient.setColorAt(1, TEAL_DARK)
    p.fillRect(0, 0, w, h, gradient)


def wizard(scale: int) -> QImage:
    w, h = 164 * scale, 314 * scale
    image = QImage(w, h, QImage.Format.Format_RGB32)
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    _background(p, w, h)
    _cross(p, w / 2, h * 0.30, w * 0.38, WHITE)
    p.setPen(WHITE)
    p.setFont(QFont("Segoe UI", 15 * scale, QFont.Weight.DemiBold))
    p.drawText(QRectF(0, h * 0.50, w, 30 * scale), Qt.AlignmentFlag.AlignCenter, "ClinAssist")
    p.setPen(MIST)
    p.setFont(QFont("Segoe UI", 8 * scale))
    p.drawText(
        QRectF(10 * scale, h * 0.50 + 32 * scale, w - 20 * scale, 40 * scale),
        Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap,
        "Offline clinical consultation assistant",
    )
    p.end()
    return image


def badge(px: int, background: bool = True) -> QImage:
    image = QImage(px, px, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    if background:
        tile = QPainterPath()
        tile.addRoundedRect(QRectF(0, 0, px, px), px * 0.2, px * 0.2)
        gradient = QLinearGradient(0, 0, 0, px)
        gradient.setColorAt(0, TEAL)
        gradient.setColorAt(1, TEAL_DARK)
        p.fillPath(tile, gradient)
    _cross(p, px / 2, px / 2, px * 0.58, WHITE)
    p.end()
    return image


def _flatten(image: QImage) -> QImage:
    """BMP has no transparency: put the badge on white, as on the installer's header."""
    flat = QImage(image.size(), QImage.Format.Format_RGB32)
    flat.fill(WHITE)
    p = QPainter(flat)
    p.drawImage(0, 0, image)
    p.end()
    return flat


def main() -> int:
    QGuiApplication.instance() or QGuiApplication(sys.argv)
    OUT.mkdir(exist_ok=True)
    for scale in (1, 2):
        wizard(scale).save(str(OUT / f"wizard-{scale}00.bmp"))
        _flatten(badge(55 * scale)).save(str(OUT / f"small-{scale}00.bmp"))
    badge(256).save(str(OUT / "clinassist.ico"))
    badge(256).save(str(OUT / "clinassist.png"))
    print("artwork written to", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
