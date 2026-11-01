"""Шапка окна: место под логотип, разделитель и шелкография «DRUM MIDI / NOTE REMAPPER». Только рисование."""

from PySide6.QtCore import QRectF, QSize
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QSizePolicy, QWidget

from . import text, theme
from .theme import qcolor

LINES = ("DRUM MIDI", "NOTE REMAPPER")


class BrandBlock(QWidget):
    """Слот логотипа 144×22 (пустой), вертикальный разделитель 1×28 с тенью справа и две строки шелкографии."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._spec = text.label(theme.BRAND_FONT, spacing=theme.BRAND_SPACING)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def _silk_width(self) -> float:
        return max(text.text_width(line, self._spec) for line in LINES)

    def sizeHint(self) -> QSize:
        w, _h = theme.LOGO_SIZE
        return QSize(int(w + 2 * theme.HEADER_GAP + 1 + self._silk_width() + 1), theme.HEADER_H - theme.RECESS_EDGE_TOP)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        gap, mid = theme.HEADER_GAP, theme.HEADER_H / 2
        x = theme.LOGO_SIZE[0] + gap
        h = theme.BRAND_DIVIDER_H
        p.fillRect(QRectF(x + 1, mid - h / 2, 1, h), qcolor(theme.BRAND_DIVIDER_SHADOW))  # тень 1px вправо
        p.fillRect(QRectF(x, mid - h / 2, 1, h), qcolor(theme.BRAND_DIVIDER))
        x += 1 + gap
        line = text.line_height(self._spec)
        step = theme.BRAND_FONT * theme.BRAND_LINE
        top = mid - step
        for i, content in enumerate(LINES):
            rect = QRectF(x, top + i * step + (step - line) / 2, self._silk_width() + 2, line)
            text.draw_text(p, rect, content, self._spec, theme.SILK_TEXT)
