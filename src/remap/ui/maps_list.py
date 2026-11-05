"""Список карт вкладки Maps: встроенные шаблоны и карты пользователя, записи в две строки (имя и источник)."""
from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QStyle, QStyledItemDelegate

from . import plates
from .maps_text import MapRef, wrapped_tooltip

REF_ROLE = Qt.ItemDataRole.UserRole
SUBTITLE_ROLE = Qt.ItemDataRole.UserRole + 1
HEADER_ROLE = Qt.ItemDataRole.UserRole + 2


class MapListDelegate(QStyledItemDelegate):
    """Две строки: имя карты и (приглушённо) статус/источник; заголовки групп — мелкими капителями."""

    def sizeHint(self, option, index) -> QSize:
        return QSize(200, 30 if index.data(HEADER_ROLE) else 46)

    def paint(self, p, option, index) -> None:
        r = QRectF(option.rect)
        if index.data(HEADER_ROLE):
            plates.paint_group_header(p, r.adjusted(4, 0, -4, 0), index.data() or "", variant="scene", caret=False)
            return
        enabled = bool(index.flags() & Qt.ItemFlag.ItemIsEnabled)
        plates.paint_map_entry(p, r.adjusted(0, 2, 0, -2), index.data() or "", index.data(SUBTITLE_ROLE) or "",
                               selected=bool(option.state & QStyle.StateFlag.State_Selected),
                               hover=bool(option.state & QStyle.StateFlag.State_MouseOver), enabled=enabled)


class MapList(QListWidget):
    """Записи карт с заголовками секций; у записи — `MapRef` (None — запись-сообщение, не выбирается)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setItemDelegate(MapListDelegate(self))
        self.setMouseTracking(True)

    def add_header(self, text: str) -> None:
        item = QListWidgetItem(text)
        item.setData(HEADER_ROLE, True)
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        self.addItem(item)

    def add_entry(self, title: str, subtitle: str, ref: MapRef | None, tooltip: str = "") -> None:
        item = QListWidgetItem(title)
        item.setData(SUBTITLE_ROLE, subtitle)
        item.setData(REF_ROLE, ref)
        # подзаголовок в списке обрезается по ширине — в подсказке текст целиком
        item.setToolTip(wrapped_tooltip(tooltip or f"{title}\n{subtitle}"))
        if ref is None:
            item.setFlags(Qt.ItemFlag.NoItemFlags)
        self.addItem(item)

    def row_of(self, ref: MapRef) -> int:
        """Строка записи с этой картой; -1 — нет."""
        for i in range(self.count()):
            if self.item(i).data(REF_ROLE) == ref:
                return i
        return -1
