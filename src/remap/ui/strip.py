"""Каркас верхней полосы вкладки: утопленный блок 836×64 (лицо в 32 px от краёв окна, сразу под шапкой), внутри —
панель в 6 px от краёв блока, лица виджетов — в 15 px от краёв панели. Одна геометрия у полос всех вкладок; что
лежит в панели, решает наследник. Только виджеты и размеры из макета."""

from PySide6.QtCore import QMargins, QRectF, QSize
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QSizePolicy, QWidget

from . import theme
from .metal import Panel, RecessedBlock
from .theme import qcolor

SLOT_H = theme.STRIP_H - 2 * theme.RECESS_PAD  # высота панели: полоса, по центру которой стоят лица


class StripSeparator(QWidget):
    """Вертикальная прорезь панели: тёмная линия 1 px и светлая справа от неё; сверху и снизу по 10 px."""

    def __init__(self, before: int, after: int, parent: QWidget | None = None) -> None:
        """before / after — поля соседних виджетов под тень и обод: прорезь занимает 54 px между ЛИЦАМИ."""
        super().__init__(parent)
        self._before = before
        self.setFixedWidth(theme.STRIP_SEP_W - before - after)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

    def sizeHint(self) -> QSize:
        return QSize(self.width(), 0)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        x, top, height = (theme.STRIP_SEP_W - 1) // 2 - self._before, 10, self.height() - 20
        p.fillRect(QRectF(x + 1, top, 1, height), qcolor(theme.STRIP_SEP))
        p.fillRect(QRectF(x, top, 1, height), qcolor(theme.STRIP_SEP_DARK))


class StripFrame(RecessedBlock):
    """Блок полосы с панелью: `panel` (её `panel.body` — горизонтальный layout для содержимого)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(theme.STRIP_W, theme.STRIP_H + theme.RECESS_EDGE_TOP + theme.RECESS_EDGE_BOTTOM)
        self.panel = Panel()
        self.body.addWidget(self.panel)

    def set_face_inset(self, left: int, right: int) -> None:
        """left / right — поля крайних виджетов под тень и обод: их ЛИЦА встают в 15 px от краёв панели."""
        self.panel.body.setContentsMargins(QMargins(theme.STRIP_PAD_X - left, 0, theme.STRIP_PAD_X - right, 0))
