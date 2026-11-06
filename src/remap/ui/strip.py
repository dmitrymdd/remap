"""Каркас верхней полосы вкладки: утопленный блок 836×64 (лицо в 32 px от краёв окна, сразу под шапкой; с `stretch` —
на всю ширину страницы, не уже 836), внутри — панель в 6 px от краёв блока, лица виджетов — в 15 px от краёв панели. Одна геометрия у полос всех вкладок; что
лежит в панели, решает наследник. Только виджеты и размеры из макета."""

from PySide6.QtCore import QMargins, QRectF, QSize
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QSizePolicy, QWidget

from . import theme
from .metal import Panel, RecessedBlock
from .theme import qcolor

SLOT_H = theme.STRIP_H - 2 * theme.RECESS_PAD  # высота панели: полоса, по центру которой стоят лица


def section_width(block_w: int) -> int:
    """Ширина секции полосы (от лица первого виджета до лица последнего) над блоком экрана шириной block_w: по 21 px с
    каждой стороны — у края полосы это поле блока и панели, у прорези — половина её лишней ширины
    (STRIP_SEP_W = SCREEN_GAP + 2 × STRIP_INSET)."""
    return block_w - 2 * theme.STRIP_INSET


class StripSeparator(QWidget):
    """Вертикальная прорезь панели: тёмная линия 1 px и светлая справа от неё; сверху и снизу по 10 px."""

    def __init__(self, before: int, after: int, parent: QWidget | None = None, *, width: int = theme.STRIP_SEP_W) -> None:
        """before / after — поля соседних виджетов под тень и обод: прорезь занимает `width` px между ЛИЦАМИ, линия —
        посередине."""
        super().__init__(parent)
        self._before, self._span = before, width
        self.setFixedWidth(width - before - after)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

    def sizeHint(self) -> QSize:
        return QSize(self.width(), 0)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        x, top, height = (self._span - 1) // 2 - self._before, 10, self.height() - 20
        p.fillRect(QRectF(x + 1, top, 1, height), qcolor(theme.STRIP_SEP))
        p.fillRect(QRectF(x, top, 1, height), qcolor(theme.STRIP_SEP_DARK))


class StripFrame(RecessedBlock):
    """Блок полосы с панелью: `panel` (её `panel.body` — горизонтальный layout для содержимого). Полоса с секциями
    задаёт `_left` / `_right` (контейнеры секций в панели) и `_extra` (поля их крайних виджетов под тень и обод)."""

    _left: QWidget
    _right: QWidget
    _extra: tuple[int, int]

    def __init__(self, parent: QWidget | None = None, *, stretch: bool = False) -> None:
        """stretch — полоса тянется на ширину страницы (секции ставит наследник по ряду экранов под ней)."""
        super().__init__(parent)
        height = theme.STRIP_H + theme.RECESS_EDGE_TOP + theme.RECESS_EDGE_BOTTOM
        if stretch:
            self.setFixedHeight(height)
            self.setMinimumWidth(theme.STRIP_W)
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        else:
            self.setFixedSize(theme.STRIP_W, height)
        self.panel = Panel()
        self.body.addWidget(self.panel)

    def set_face_inset(self, left: int, right: int) -> None:
        """left / right — поля крайних виджетов под тень и обод: их ЛИЦА встают в 15 px от краёв панели."""
        self.panel.body.setContentsMargins(QMargins(theme.STRIP_PAD_X - left, 0, theme.STRIP_PAD_X - right, 0))

    def set_sections(self, left: int, right: int) -> None:
        """Ширины секций от лица первого виджета до лица последнего (`section_width()` блоков экранов)."""
        self.apply_sections(left, right)

    def apply_sections(self, left: int, right: int, *inner: QWidget) -> None:
        """Ширины секций и сразу их положение: layout'ы — изнутри наружу (`inner` — контейнеры внутри секций, чьё
        содержимое поменялось), затем панель. Не по отложенному LayoutRequest: setFixedWidth меняет ширину секции
        сразу, а x ей даёт только раскладка панели — до неё секция новой ширины стоит на старом месте, и полоса
        дрожит за ручкой ряда и краем окна."""
        self._left.setFixedWidth(left + self._extra[0])
        self._right.setFixedWidth(right + self._extra[1])
        for w in (*inner, self._left, self._right, self.panel):
            w.layout().activate()

    def section_widths(self) -> tuple[int, int]:
        return self._left.width() - self._extra[0], self._right.width() - self._extra[1]
