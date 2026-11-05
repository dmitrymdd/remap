"""Ряд из двух экранов с перетаскиваемым зазором: главный экран забирает лишнюю ширину окна, боковая колонка держит
свою, пока зазор не перетащат.

Свой виджет, а не QSplitter: QSplitter сам перераспределяет ширину при смене размера, рисует системную ручку и не
помнит ширину колонки, которую пришлось ужать узким окном. Здесь ширина боковой колонки — одно число: `saved` —
выбранная пользователем (ui.ini), `side_width()` — действующая (saved, ужатая под текущую ширину ряда). Окно сузилось и
снова расширилось — колонка возвращается к saved.

Ручка — сам зазор на всю высоту ряда, ничего не рисует (виден металл корпуса), только курсор. Двойной клик — ширина
по умолчанию (макет). В ui.ini ширина пишется по отпусканию ручки и по двойному клику.
"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QWidget

from . import theme


class SplitHandle(QWidget):
    """Зазор между экранами: нажатие и протяжка меняют ширину боковой колонки."""

    def __init__(self, row: SplitRow) -> None:
        super().__init__(row)
        self._row = row
        self._press: tuple[float, int] | None = None  # (x курсора на экране, ширина колонки) в момент нажатия
        self.setCursor(Qt.CursorShape.SplitHCursor)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return
        self._press = (event.globalPosition().x(), self._row.side_width())

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._press is None:
            return
        x0, width0 = self._press
        dx = round(event.globalPosition().x() - x0)
        self._row.drag_to(width0 + dx if self._row.side_first else width0 - dx)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._press is not None:
            self._press = None
            self._row.store()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._press = None
            self._row.reset()


class SplitRow(QWidget):
    """main | side (или side | main при `side_first`) через зазор `gap`. Ширины — внешние размеры виджетов экранов
    (утопленных блоков), высота у всех — высота ряда."""

    layout_changed = Signal()  # геометрия экранов поменялась (по ней полоса над экранами ставит свои секции)

    def __init__(self, main: QWidget, side: QWidget, *, side_first: bool, side_min: int, main_min: int,
                 side_default: int | None = None, gap: int = theme.SCREEN_GAP, settings=None, key: str | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.main, self.side, self.side_first = main, side, side_first
        self.side_min, self.main_min, self.gap = side_min, main_min, gap
        self.side_default = side_min if side_default is None else side_default
        self._settings, self._key = settings, key
        self.saved = self.side_default
        if settings is not None and key is not None:
            value = settings.value(key, self.side_default, type=int)
            self.saved = max(side_min, value)
        for w in (main, side):
            w.setParent(self)
        self.handle = SplitHandle(self)
        self._geometry: tuple | None = None

    # --- ширины ---

    def side_max(self) -> int:
        """Шире колонка быть не может: главному экрану нужно не меньше main_min."""
        return max(self.side_min, self.width() - self.gap - self.main_min)

    def side_width(self) -> int:
        """Действующая ширина боковой колонки: saved, ужатая под текущую ширину ряда."""
        return min(self.saved, self.side_max())

    def drag_to(self, width: int) -> None:
        """Протяжка ручки: новая выбранная ширина (в пределах ряда); в ui.ini — по отпусканию (`store()`)."""
        self.saved = max(self.side_min, min(width, self.side_max()))
        self._relayout()

    def reset(self) -> None:
        """Двойной клик по ручке: ширина по умолчанию."""
        self.saved = self.side_default
        self._relayout()
        self.store()

    def store(self) -> None:
        if self._settings is not None and self._key is not None:
            self._settings.setValue(self._key, self.saved)

    # --- раскладка ---

    def minimumSizeHint(self) -> QSize:
        height = max(self.main.minimumSizeHint().height(), self.side.minimumSizeHint().height(), 0)
        return QSize(self.side_min + self.gap + self.main_min, height)

    def sizeHint(self) -> QSize:
        return QSize(self.side_default + self.gap + self.main_min, self.minimumSizeHint().height())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._relayout()

    def _relayout(self) -> None:
        height, side_w = self.height(), self.side_width()
        main_w = max(0, self.width() - self.gap - side_w)
        if self.side_first:
            spans = ((self.side, 0, side_w), (self.handle, side_w, self.gap), (self.main, side_w + self.gap, main_w))
        else:
            spans = ((self.main, 0, main_w), (self.handle, main_w, self.gap), (self.side, main_w + self.gap, side_w))
        for w, x, width in spans:
            w.setGeometry(x, 0, width, height)
        geometry = (self.width(), height, side_w)
        if geometry != self._geometry:
            self._geometry = geometry
            self.layout_changed.emit()
