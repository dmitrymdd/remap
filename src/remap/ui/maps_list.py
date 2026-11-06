"""Экран списка карт вкладки Maps: секции BUILT-IN TEMPLATES (замок в заголовке) и MY MAPS, записи в две строки
(имя и источник/заметки). Всё рисуется само (`plates.paint_group_header`, `plates.paint_map_entry`); числа — из макета.

Выбор одиночный: клик, ↑/↓, Home/End. Список сам текущую запись не меняет — он просит (`chosen`), а страница решает
(несохранённые правки могут оставить прежнюю карту) и ставит текущую `set_current()`. Кольцо фокуса — только при
фокусе с клавиатуры."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QEvent, QRectF, Qt, Signal
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from . import plates, theme
from .convert_input import screen_list
from .glass import Screen
from .maps_text import MapRef
from .metal import RecessedBlock
from .theme import qcolor

HEADER_H = 30  # заголовок секции (с линией снизу)
HEADER_AFTER = 2  # margin-bottom заголовка сверх общего зазора
ENTRY_GAP = 6  # зазор между элементами колонки
SECTION_GAP = 10  # margin-top второй и следующих секций
KEYBOARD_FOCUS = (Qt.FocusReason.TabFocusReason, Qt.FocusReason.BacktabFocusReason, Qt.FocusReason.ShortcutFocusReason)


@dataclass(frozen=True)
class MapEntry:
    """Запись: `ref` — карта (None — запись-сообщение, не выбирается); `tip` — HTML подсказки."""
    name: str
    sub: str
    ref: MapRef | None
    tip: str = ""


@dataclass(frozen=True)
class MapSection:
    label: str
    entries: tuple[MapEntry, ...]
    lock: bool = False


@dataclass(frozen=True)
class _Item:
    rect: QRectF
    section: MapSection | None = None  # заголовок
    entry: MapEntry | None = None


def layout_items(sections: list[MapSection], width: float) -> tuple[list[_Item], float]:
    """Заголовки и записи сверху вниз; вторая колонка — общая высота содержимого."""
    items, y = [], 0.0
    for i, section in enumerate(sections):
        if i:
            y += ENTRY_GAP + SECTION_GAP
        items.append(_Item(QRectF(0, y, width, HEADER_H), section=section))
        y += HEADER_H + HEADER_AFTER
        for entry in section.entries:
            y += ENTRY_GAP
            items.append(_Item(QRectF(0, y, width, theme.MAP_ENTRY_H), entry=entry))
            y += theme.MAP_ENTRY_H
    return items, y


class _ListBody(QWidget):
    """Содержимое прокрутки: рисует заголовки и записи, мышь, клавиатура и подсказки."""

    def __init__(self, owner: MapListScreen) -> None:
        super().__init__()
        self._owner = owner
        self.items: list[_Item] = []
        self.hover: MapEntry | None = None
        self._focus_visible = False
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def relayout(self) -> None:
        self.items, height = layout_items(self._owner.sections, self.width())
        self.setFixedHeight(round(height))
        self.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if event.size().width() != event.oldSize().width():
            self.relayout()

    def entry_at(self, y: float) -> _Item | None:
        return next((it for it in self.items if it.entry is not None and it.rect.top() <= y <= it.rect.bottom()), None)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        current = self._owner.current
        visible = QRectF(event.rect())
        for it in self.items:
            if not it.rect.intersects(visible):
                continue
            if it.section is not None:
                plates.paint_group_header(p, it.rect, it.section.label, variant="scene", align="center", caret=False,
                                          icon="lock" if it.section.lock else None, inset=0)
                continue
            e = it.entry
            selected = e.ref is not None and e.ref == current
            plates.paint_map_entry(p, it.rect, e.name, e.sub, selected=selected, hover=e is self.hover,
                                   enabled=e.ref is not None)
            if selected and self._focus_visible and self.hasFocus():
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                p.setPen(QPen(qcolor(theme.KEY_FOCUS_RING), 1))
                p.setBrush(Qt.BrushStyle.NoBrush)
                inner = it.rect.adjusted(2.5, 2.5, -2.5, -2.5)
                p.drawRoundedRect(inner, theme.PLATE_RADIUS - 2, theme.PLATE_RADIUS - 2)

    def mouseMoveEvent(self, event) -> None:
        it = self.entry_at(event.position().y())
        entry = it.entry if it is not None and it.entry.ref is not None else None
        if entry is not self.hover:
            self.hover = entry
            self.update()

    def leaveEvent(self, _event) -> None:
        if self.hover is not None:
            self.hover = None
            self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        it = self.entry_at(event.position().y())
        if it is not None and it.entry.ref is not None:
            self._owner.choose(it.entry.ref)

    def keyPressEvent(self, event) -> None:
        refs = self._owner.refs()
        if not refs:
            return super().keyPressEvent(event)
        cur = self._owner.current
        i = refs.index(cur) if cur in refs else -1
        key = event.key()
        if key == Qt.Key.Key_Up:
            target = refs[max(i - 1, 0)] if i >= 0 else refs[-1]
        elif key == Qt.Key.Key_Down:
            target = refs[min(i + 1, len(refs) - 1)]
        elif key == Qt.Key.Key_Home:
            target = refs[0]
        elif key == Qt.Key.Key_End:
            target = refs[-1]
        else:
            return super().keyPressEvent(event)
        if target != cur:
            self._owner.choose(target)

    def focusInEvent(self, event) -> None:
        self._focus_visible = event.reason() in KEYBOARD_FOCUS
        self.update()
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:
        self._focus_visible = False
        self.update()
        super().focusOutEvent(event)

    def event(self, e) -> bool:
        if e.type() == QEvent.Type.ToolTip:
            it = self.entry_at(e.pos().y())
            if it is not None and it.entry.tip:
                QToolTip.showText(e.globalPos(), it.entry.tip, self, it.rect.toRect())
            else:
                QToolTip.hideText()
                e.ignore()
            return True
        return super().event(e)


class MapListScreen(RecessedBlock):
    """Блок с экраном списка карт. `chosen(ref)` — пользователь выбрал другую карту; текущую ставит страница."""

    chosen = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(theme.POOL_W)  # ширину задаёт ряд экранов (SplitRow)
        self.sections: list[MapSection] = []
        self.current: MapRef | None = None
        self.screen = Screen()
        self.body.addWidget(self.screen)
        self._body = _ListBody(self)
        self.area = screen_list(self._body)
        self.screen.body.addWidget(self.area)
        self.bar = self.screen.attach(self.area)

    def set_sections(self, sections: list[MapSection]) -> None:
        self.sections = sections
        self._body.hover = None
        self._body.relayout()

    def entries(self) -> list[MapEntry]:
        return [e for s in self.sections for e in s.entries]

    def refs(self) -> list[MapRef]:
        return [e.ref for e in self.entries() if e.ref is not None]

    def entry(self, ref: MapRef) -> MapEntry | None:
        return next((e for e in self.entries() if e.ref == ref), None)

    def choose(self, ref: MapRef) -> None:
        if ref != self.current:
            self.chosen.emit(ref)

    def set_current(self, ref: MapRef | None) -> None:
        """Текущая карта (выделенная запись); запись прокручивается в видимую область. Сигнала нет."""
        self.current = ref
        item = next((it for it in self._body.items if it.entry is not None and it.entry.ref == ref), None)
        if item is not None:
            self.area.ensureVisible(0, round(item.rect.center().y()), 0, round(item.rect.height() / 2) + ENTRY_GAP)
        self._body.update()
