"""Экран нот вкладки Maps: модель над рабочей копией карты, фильтр (поиск, «только с именем», свёрнутые группы) и вид.

Вид — QTableView без QSS и без собственного фона: всё рисует делегат функциями `plates.py` (строка ноты 28 px, заголовок
группы 30 px), над таблицей — поиск, флажок NAMED ONLY и строка заголовков NOTE / NAME, под ней — строка итогов. Имя
правится настоящим QLineEdit в поле 22 px поверх строки (Enter — сохранить, Esc — отменить). Числа — из макета Maps.
"""
from __future__ import annotations

from PySide6.QtCore import (
    QAbstractTableModel, QEvent, QModelIndex, QPersistentModelIndex, QPointF, QRectF, QSortFilterProxyModel, Qt, Signal,
)
from PySide6.QtGui import QColor, QFont, QKeySequence, QPainter, QPainterPath, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QLineEdit, QSizePolicy, QStyledItemDelegate, QTableView,
    QToolTip, QWidget,
)

from ..core.notemap import NoteMap, articulations, normalize_name, set_note_name
from ..core.pitch import note_tip, pitch_name
from . import plates, text, theme
from .field import ScreenCheck, SearchField
from .glass import Screen
from .maps_text import (
    COL_NAME, COL_NOTE, COLUMNS, EDIT_HINT, EDIT_TIP, GROUP_TIP, NAMED_ONLY, NAMED_ONLY_TIP, READ_ONLY_HINT,
    SEARCH_PLACEHOLDER, LayoutRow, badge_tip, group_rows, sort_tip,
)
from .metal import RecessedBlock
from .selection import Selection
from .tips import tip

OTHERS_ROLE = Qt.ItemDataRole.UserRole + 4  # сколько ещё нот карты с этим именем (бейдж «+N»)


class NoteTableModel(QAbstractTableModel):
    """Ноты 0–127 (с заголовками групп инструментов) над рабочей копией карты; правит её на месте.

    Раскладка строк пересчитывается при смене карты, фильтра и после сохранения, но не при правке имени:
    строка не уезжает из-под курсора.
    """

    edited = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.map: NoteMap | None = None
        self.read_only = True
        self._groups: dict[str, list[int]] = {}
        self.rows: list[LayoutRow] = []
        self.sort: tuple[int, bool] | None = None  # (колонка, по убыванию); None — по группам инструментов
        self._note_rows: dict[int, int] = {}
        self._members: dict[str | None, list[int]] = {}

    def set_map(self, m: NoteMap | None, read_only: bool) -> None:
        self.beginResetModel()
        self.map, self.read_only = m, read_only
        self._regroup()
        self._layout()
        self.endResetModel()

    def relayout(self) -> None:
        self.beginResetModel()
        self._regroup()
        self._layout()
        self.endResetModel()

    def set_sort(self, sort: tuple[int, bool] | None) -> None:
        """Сортировка (колонка, по убыванию) — все ноты без заголовков групп; None — по группам инструментов."""
        if sort != self.sort:
            self.sort = sort
            self.relayout()

    def _sorted_notes(self) -> list[int]:
        """Ноты 0–127 по колонке сортировки. NOTE — по номеру; NAME —
        по имени (без учёта регистра), равные — по номеру; ноты без имени — всегда в конце."""
        col, desc = self.sort
        notes = list(range(128))
        if col != COL_NAME:
            return notes[::-1] if desc else notes
        names = self.map.names
        named = sorted((n for n in notes if n in names), key=lambda n: (normalize_name(names[n]), n), reverse=desc)
        return named + [n for n in notes if n not in names]

    def _layout(self) -> None:
        if self.map is None:
            self.rows = []
        elif self.sort is not None:
            self.rows = [LayoutRow(None, n) for n in self._sorted_notes()]
        else:
            self.rows = group_rows(self.map.names, list(range(128)))
        self._note_rows = {r.note: i for i, r in enumerate(self.rows) if not r.is_header}
        self._members = {}
        for i, r in enumerate(self.rows):
            if not r.is_header:
                self._members.setdefault(r.group, []).append(i)

    def row_at(self, row: int) -> LayoutRow:
        return self.rows[row]

    def members(self, group: str | None) -> list[int]:
        """Строки нот группы."""
        return self._members.get(group, [])

    def note_index(self, note: int, col: int) -> QModelIndex:
        return self.index(self._note_rows[note], col)

    def note_at(self, row: int) -> int | None:
        return self.rows[row].note if 0 <= row < len(self.rows) else None

    @property
    def grouped(self) -> bool:
        return any(r.is_header for r in self.rows)

    def refresh(self) -> None:
        """Карта изменилась снаружи (например, после сохранения) — перерисовать всё."""
        self._regroup()
        if self.rows:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self.rows) - 1, len(COLUMNS) - 1))

    def _regroup(self) -> None:
        self._groups = articulations(self.map) if self.map is not None else {}

    def group(self, note: int) -> list[int]:
        """Ноты с тем же (нормализованным) именем; [] — нота не в карте."""
        name = self.map.names.get(note) if self.map is not None else None
        return self._groups.get(normalize_name(name), []) if name is not None else []

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: B008 — сигнатура Qt
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()) -> int:  # noqa: B008 — сигнатура Qt
        return 0 if parent.isValid() else len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal:
            if role == Qt.ItemDataRole.DisplayRole:
                return COLUMNS[section]
            if role == Qt.ItemDataRole.ToolTipRole:
                tip_text = sort_tip(self.sort, section)
                return tip_text + "\n" + EDIT_TIP if section == COL_NAME and not self.read_only else tip_text
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or self.map is None:
            return None
        row = self.rows[index.row()]
        if row.is_header:
            return row.label.upper() if role == Qt.ItemDataRole.DisplayRole and index.column() == 0 else None
        n, col = row.note, index.column()
        name = self.map.names.get(n)
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return str(n) if col == COL_NOTE else name or ""
        if role == OTHERS_ROLE and col == COL_NAME:
            return max(0, len(self.group(n)) - 1)
        if role == Qt.ItemDataRole.ToolTipRole and col == COL_NOTE:
            return note_tip([n])
        return None

    def badge_tip(self, note: int) -> str:
        """Подсказка бейджа «+N» ноты: остальные номера с её именем."""
        return badge_tip(note, self.group(note))

    def flags(self, index):
        if not index.isValid() or self.map is None:
            return Qt.ItemFlag.NoItemFlags
        row = self.rows[index.row()]
        if row.is_header:
            return Qt.ItemFlag.ItemIsEnabled
        f = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.column() == COL_NAME and not self.read_only:
            f |= Qt.ItemFlag.ItemIsEditable
        return f

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole) -> bool:
        if not index.isValid() or self.map is None or self.read_only:
            return False
        n, col = self.rows[index.row()].note, index.column()
        if n is None:
            return False
        if col == COL_NAME and role == Qt.ItemDataRole.EditRole:
            return self.set_name(n, str(value or ""))
        return False

    def set_name(self, n: int, label: str) -> bool:
        """Пустое имя — нота удаляется из карты; смена артикуляции снимает с ноты primary (core set_note_name)."""
        if not set_note_name(self.map, n, label):
            return False
        self._changed()
        return True

    def clear_names(self, notes: list[int]) -> bool:
        """Стереть имена нот одним шагом (одно обновление вида и одна отметка правки)."""
        changed = [n for n in notes if set_note_name(self.map, n, "")]
        if changed:
            self._changed()
        return bool(changed)

    def _changed(self) -> None:
        self.refresh()  # меняются счётчики и подсветка всех нот затронутых артикуляций
        self.edited.emit()


class NoteFilter(QSortFilterProxyModel):
    """«Только ноты с именем» + поиск по имени, номеру ноты или названию высоты + свёрнутые группы.
    Заголовок группы виден, если поиску и «только с именем» отвечает хотя бы одна нота группы (даже свёрнутой).

    Фильтр не пересчитывается при правке (dynamicSortFilter выключен): строка, у которой стёрли имя,
    не исчезает из-под курсора. Пересчёт — при смене фильтра, карты или свёрнутых групп.
    """

    def __init__(self) -> None:
        super().__init__()
        self.named_only = True
        self.query = ""
        self.collapsed: set[str] = set()  # ключи свёрнутых групп (на всё время работы вкладки, для любой карты)
        self.setDynamicSortFilter(False)

    def set_filter(self, named_only: bool, query: str) -> None:
        self.beginFilterChange()
        self.named_only, self.query = named_only, query
        self.endFilterChange()

    def toggle_group(self, key: str) -> None:
        self.beginFilterChange()
        self.collapsed ^= {key}
        self.endFilterChange()

    def source_row(self, row: int) -> LayoutRow | None:
        """Строка раскладки под строкой фильтра `row`."""
        index = self.mapToSource(self.index(row, 0))
        return self.sourceModel().row_at(index.row()) if index.isValid() else None

    def note_rows(self) -> list[int]:
        """Видимые ноты (без заголовков), сверху вниз."""
        model = self.sourceModel()
        notes = [model.note_at(self.mapToSource(self.index(r, 0)).row()) for r in range(self.rowCount())]
        return [n for n in notes if n is not None]

    def filterAcceptsRow(self, row, parent) -> bool:
        model = self.sourceModel()
        if model.map is None:
            return False
        r = model.row_at(row)
        if r.is_header:
            return any(self._accept_note(model.rows[i].note) for i in model.members(r.group))
        if r.group is not None and r.group in self.collapsed and model.grouped:
            return False
        return self._accept_note(r.note)

    def _accept_note(self, n: int) -> bool:
        name = self.sourceModel().map.names.get(n)
        if self.named_only and name is None:
            return False
        q = normalize_name(self.query)
        if not q:
            return True
        if q.isdigit():
            return int(q) == n
        return q == pitch_name(n).casefold() or (name is not None and q in normalize_name(name))


def row_rect(view: QTableView, cell: QRectF) -> QRectF:
    """Вся строка таблицы (обе колонки) по прямоугольнику одной её ячейки."""
    return QRectF(0, cell.top(), view.viewport().width(), cell.height())


class NoteDelegate(QStyledItemDelegate):
    """Рисует строки целиком (каждая ячейка — свою часть строки, по клипу): ноту `paint_note_row`, заголовок группы
    `paint_group_header`. Правка имени — QLineEdit в поле `plates.note_edit_field()`; на время правки строка в виде
    «editing», сигнал `editing(bool)`."""

    editing = Signal(bool)

    def __init__(self, view: NotesView) -> None:
        super().__init__(view)
        self._view = view
        self.edit_index: QPersistentModelIndex | None = None

    def paint(self, p, option, index) -> None:
        view = self._view
        proxy = view.model()
        row = proxy.source_row(index.row())
        if row is None:
            return
        full = row_rect(view, QRectF(option.rect))
        hover = view.hover_row == index.row()
        p.save()
        p.setClipRect(option.rect)
        if row.is_header:
            plates.paint_group_header(p, full, row.label, collapsed=row.group in proxy.collapsed, variant="scene",
                                      state="hover" if hover else "normal", inset=theme.NOTE_GROUP_INSET)
        else:
            model = proxy.sourceModel()
            name = model.map.names.get(row.note, "")
            others = model.data(model.note_index(row.note, COL_NAME), OTHERS_ROLE)
            editing = self.edit_index is not None and self.edit_index.row() == index.row()
            selected = view.selection.is_selected(row.note)
            state = "editing" if editing else "selected" if selected else "hover" if hover else "normal"
            plates.paint_note_row(p, full, str(row.note), name, state=state, dim=not name,
                                  badge=f"+{others}" if others else "", field=False)
        p.restore()

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(theme.NOTE_ROW_H)
        return size

    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        editor.setFont(theme.mono_font(theme.PLATE_NAME_FONT))
        editor.setFrame(False)
        accent = theme.qss_rgba(theme.TEXT_SELECTION_BG)
        # поле макета: заливка, рамка 1 px, радиус 3, текст в 9 px от края (у QLineEdit ещё 2 px своего поля)
        editor.setStyleSheet(
            f"QLineEdit {{ background: {theme.NOTE_EDIT_FIELD}; border: 1px solid {theme.CHIP_BORDER};"
            f" border-radius: {theme.NOTE_EDIT_RADIUS}px; padding: 0 6px; margin: 0; color: {theme.SELECTED};"
            f" selection-background-color: {accent}; selection-color: {theme.SELECTED}; }}")
        editor.textChanged.connect(lambda _t, e=editor: self._fit(e))
        self.edit_index = QPersistentModelIndex(index)
        self.editing.emit(True)
        return editor

    def updateEditorGeometry(self, editor, option, index) -> None:
        editor.setProperty("row_top", option.rect.top())
        editor.setProperty("row_h", option.rect.height())
        self._fit(editor)

    def _fit(self, editor: QLineEdit) -> None:
        """Поле растёт с текстом (не уже 180 px), но не дальше края строки."""
        top, height = editor.property("row_top"), editor.property("row_h")
        if top is None:
            return
        full = row_rect(self._view, QRectF(0, top, 1, height))
        editor.setGeometry(plates.note_edit_field(full, editor.text()).toRect())

    def destroyEditor(self, editor, index) -> None:
        super().destroyEditor(editor, index)
        self.edit_index = None
        self.editing.emit(False)
        self._view.viewport().update()


NAV_KEYS = (Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_PageUp, Qt.Key.Key_PageDown, Qt.Key.Key_Home, Qt.Key.Key_End)


class NotesView(QTableView):
    """Таблица без рамки, фона, сетки и заголовков; заголовки групп — на всю ширину, высоты строк — из макета. Клик по
    заголовку группы сворачивает или раскрывает её; правка идёт всегда в колонке имени; подсказки — свои (номер — высота
    ноты, бейдж — остальные номера с этим именем, обрезанное имя — целиком).

    Выделение — `selection` (`ui/selection.py`, ключи — номера нот, как в Проводнике): клик / Ctrl / Shift / Ctrl+Shift,
    Ctrl+A — все видимые ноты (заголовки и ноты свёрнутых групп не входят), клик по пустому месту и Esc — снять. Стрелки
    двигают текущую строку и выделяют её (с Shift — диапазон). Своё выделение Qt выключено; текущая строка (`currentIndex`)
    — та, что правится по двойному клику, Enter и F2. После сортировки и фильтра выделение остаётся у видимых нот."""

    group_clicked = Signal(str)
    selection_changed = Signal()

    def __init__(self, proxy: NoteFilter, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.hover_row = -1
        self.selection = Selection()
        self.setModel(proxy)
        self.setFrameShape(QTableView.Shape.NoFrame)
        self.setShowGrid(False)
        self.setWordWrap(False)
        self.setMouseTracking(True)
        self.setAutoFillBackground(False)
        self.viewport().setAutoFillBackground(False)
        pal = self.palette()
        # фона нет, а выделение рисует делегат плашкой: стиль не должен заливать выбранную строку (PE_PanelItemViewRow)
        for role in (QPalette.ColorRole.Base, QPalette.ColorRole.Window, QPalette.ColorRole.Highlight):
            for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
                pal.setColor(group, role, QColor(Qt.GlobalColor.transparent))
        self.setPalette(pal)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked
                             | QAbstractItemView.EditTrigger.EditKeyPressed
                             | QAbstractItemView.EditTrigger.AnyKeyPressed)
        self.verticalHeader().hide()
        self.verticalHeader().setMinimumSectionSize(1)
        self.verticalHeader().setDefaultSectionSize(theme.NOTE_ROW_H)
        header = self.horizontalHeader()
        header.hide()
        header.setSectionResizeMode(COL_NOTE, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(COL_NOTE, theme.NOTE_NUM_COL)
        header.setSectionResizeMode(COL_NAME, QHeaderView.ResizeMode.Stretch)
        self.delegate = NoteDelegate(self)
        self.setItemDelegate(self.delegate)
        for sig in (proxy.modelReset, proxy.layoutChanged, proxy.rowsInserted, proxy.rowsRemoved):
            sig.connect(lambda *_: self.relayout_rows())

    @property
    def proxy(self) -> NoteFilter:
        return self.model()

    def relayout_rows(self) -> None:
        """Заголовки групп — на всю ширину и выше строк нот (пересчёт после фильтрации и перестройки)."""
        self.clearSpans()
        for r in range(self.proxy.rowCount()):
            row = self.proxy.source_row(r)
            if row is not None and row.is_header:
                self.setSpan(r, 0, 1, len(COLUMNS))
                self.setRowHeight(r, theme.NOTE_GROUP_H)
            else:
                self.setRowHeight(r, theme.NOTE_ROW_H)
        self.hover_row = -1
        self.selection.set_items(self.proxy.note_rows())

    def _note_at(self, pos) -> int | None:
        index = self.indexAt(pos)
        row = self.proxy.source_row(index.row()) if index.isValid() else None
        return row.note if row is not None else None

    def _selection_done(self) -> None:
        self.viewport().update()
        self.selection_changed.emit()

    def select_all(self) -> None:
        self.selection.select_all()
        self._selection_done()

    def clear_selection(self) -> None:
        self.selection.clear()
        self._selection_done()

    def select_note(self, note: int, ctrl: bool = False, shift: bool = False) -> None:
        """Как щелчок по строке ноты с модификаторами (нота должна быть видна)."""
        self.selection.press(note, ctrl=ctrl, shift=shift)
        self._selection_done()

    def edit(self, index, *args):
        """Правка — всегда в колонке имени, по какой бы ячейке строки ни щёлкнули."""
        if index.isValid() and index.column() != COL_NAME:
            index = index.siblingAtColumn(COL_NAME)
        return super().edit(index, *args)

    def _header_at(self, pos) -> LayoutRow | None:
        index = self.indexAt(pos)
        row = self.proxy.source_row(index.row()) if index.isValid() else None
        return row if row is not None and row.is_header else None

    def mousePressEvent(self, event) -> None:
        row = self._header_at(event.position().toPoint())
        if row is not None:
            if event.button() == Qt.MouseButton.LeftButton:
                self.group_clicked.emit(row.group)
            return
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            note = self._note_at(event.position().toPoint())
            if note is None:
                self.clear_selection()
            else:
                mods = event.modifiers()
                self.select_note(note, ctrl=bool(mods & Qt.KeyboardModifier.ControlModifier),
                                 shift=bool(mods & Qt.KeyboardModifier.ShiftModifier))

    def keyPressEvent(self, event) -> None:
        if event.matches(QKeySequence.StandardKey.SelectAll):
            self.select_all()
            return
        if event.key() == Qt.Key.Key_Escape and self.state() != QAbstractItemView.State.EditingState:
            self.clear_selection()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.state() != QAbstractItemView.State.EditingState:
            if self.currentIndex().isValid():
                self.edit(self.currentIndex(), QAbstractItemView.EditTrigger.EditKeyPressed, event)
            return
        before = self.currentIndex()
        super().keyPressEvent(event)
        current = self.currentIndex()
        # заголовки групп не бывают текущими: стрелка проходит их (свёрнутые группы — несколько подряд)
        while event.key() in NAV_KEYS and current.isValid() and current.row() != before.row() \
                and self.proxy.source_row(current.row()).is_header:
            step = current
            super().keyPressEvent(event)
            current = self.currentIndex()
            if current.row() == step.row():  # край таблицы — вернуться на прежнюю строку ноты
                self.setCurrentIndex(before)
                current = before
                break
        if event.key() in NAV_KEYS and current.isValid() and current.row() != before.row():
            note = self.proxy.source_row(current.row()).note
            if note is not None:
                shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                self.select_note(note, shift=shift)

    def mouseDoubleClickEvent(self, event) -> None:
        if self._header_at(event.position().toPoint()) is not None:
            self.mousePressEvent(event)  # второй щелчок — снова переключить
            return
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event) -> None:
        index = self.indexAt(event.position().toPoint())
        row = index.row() if index.isValid() else -1
        if row != self.hover_row:
            self.hover_row = row
            self.viewport().update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        if self.hover_row != -1:
            self.hover_row = -1
            self.viewport().update()
        super().leaveEvent(event)

    def tooltip_at(self, pos) -> str:
        """Текст подсказки в точке `pos` вьюпорта ('' — подсказки нет)."""
        index = self.indexAt(pos)
        row = self.proxy.source_row(index.row()) if index.isValid() else None
        if row is None:
            return ""
        if row.is_header:
            return GROUP_TIP
        model = self.proxy.sourceModel()
        if index.column() == COL_NOTE:
            return note_tip([row.note])
        name = model.map.names.get(row.note, "")
        others = model.data(model.note_index(row.note, COL_NAME), OTHERS_ROLE)
        cell = QRectF(self.visualRect(index))
        shown, pill = plates.note_badge_rect(cell, name, f"+{others}" if others else "")
        if pill is not None and pill.contains(QPointF(pos)):
            return model.badge_tip(row.note)
        return name if shown != name else ""

    def viewportEvent(self, event) -> bool:
        if event.type() == QEvent.Type.ToolTip:
            text_ = self.tooltip_at(event.pos())
            if text_:
                QToolTip.showText(event.globalPos(), tip(text_), self.viewport())
            else:
                QToolTip.hideText()
            return True
        return super().viewportEvent(event)


def _sort_arrow(p: QPainter, x: float, cy: float, desc: bool) -> None:
    """Стрелка сортировки 7×4: вершиной вверх — по возрастанию, вниз — по убыванию."""
    path = QPainterPath()
    tip_y, base_y = (cy + 2, cy - 2) if desc else (cy - 2, cy + 2)
    path.moveTo(x, base_y)
    path.lineTo(x + 7, base_y)
    path.lineTo(x + 3.5, tip_y)
    path.closeSubpath()
    p.fillPath(path, theme.qcolor(theme.FIELD_CAPTION))


class ColumnHeader(QWidget):
    """Строка заголовков NOTE / NAME (28 px и линия 1 px снизу): NOTE по правому краю столбца 64 с отступом 18, NAME — от
    64. Клик — `clicked(колонка)`; стрелка показывает сортировку (`set_sort`). Подсказки — `tip_for(колонка)`."""

    clicked = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.sort: tuple[int, bool] | None = None
        self.tip_for = lambda _col: ""
        self._spec = text.mono(theme.NOTES_HEAD_FONT, QFont.Weight.DemiBold, theme.NOTES_HEAD_SPACING)
        self.setFixedHeight(theme.NOTES_HEAD_H + 1)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_sort(self, sort: tuple[int, bool] | None) -> None:
        self.sort = sort
        self.update()

    @staticmethod
    def column_at(x: float) -> int:
        return COL_NOTE if x < theme.NOTE_NUM_COL else COL_NAME

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        h = theme.NOTES_HEAD_H
        pad = theme.NOTE_NUM_PAD
        note = QRectF(0, 0, theme.NOTE_NUM_COL - pad, h)
        text.draw_text(p, note, COLUMNS[COL_NOTE], self._spec, theme.FIELD_CAPTION, plates.RIGHT_MID)
        text.draw_text(p, QRectF(theme.NOTE_NUM_COL, 0, self.width() - theme.NOTE_NUM_COL, h), COLUMNS[COL_NAME],
                       self._spec, theme.FIELD_CAPTION, plates.LEFT_MID)
        if self.sort is not None:
            col, desc = self.sort
            x = note.right() + 4 if col == COL_NOTE else \
                theme.NOTE_NUM_COL + text.text_width(COLUMNS[COL_NAME], self._spec) + 4
            _sort_arrow(p, x, h / 2, desc)
        p.fillRect(QRectF(0, h, self.width(), 1), theme.qcolor(theme.SCREEN_DIVIDER))

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.column_at(event.position().x()))

    def event(self, e) -> bool:
        if e.type() == QEvent.Type.ToolTip:
            text_ = self.tip_for(self.column_at(e.pos().x()))
            if text_:
                QToolTip.showText(e.globalPos(), tip(text_), self)
            return True
        return super().event(e)


class TotalsBar(QWidget):
    """Строка итогов (линия 1 px сверху и 26 px, текст по нижнему краю): слева — число нот с именем или ошибки карты
    цветом ошибки, справа — подсказка клавиш правки или «READ-ONLY TEMPLATE»."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.left, self.right, self.error = "", "", False
        self._spec = text.mono(theme.NOTES_TOTALS_FONT, spacing=theme.NOTES_TOTALS_SPACING)
        self.setFixedHeight(theme.NOTES_TOTALS_H + 1)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_texts(self, left: str, right: str, error: bool = False) -> None:
        if (left, right, error) != (self.left, self.right, self.error):
            self.left, self.right, self.error = left, right, error
            self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.fillRect(QRectF(0, 0, self.width(), 1), theme.qcolor(theme.SCREEN_DIVIDER))
        area = QRectF(0, 1, self.width(), theme.NOTES_TOTALS_H)
        bottom = Qt.AlignmentFlag.AlignBottom
        right_w = text.text_width(self.right, self._spec) if self.right else 0.0
        text.draw_text(p, area.adjusted(0, 0, -(right_w + 12 if right_w else 0), 0), self.left, self._spec,
                       theme.ERR_TEXT if self.error else theme.SCREEN_TEXT_3, Qt.AlignmentFlag.AlignLeft | bottom,
                       Qt.TextElideMode.ElideRight)
        if self.right:
            text.draw_text(p, area, self.right, self._spec, theme.SCREEN_TEXT_3, Qt.AlignmentFlag.AlignRight | bottom)


TYPING_MODIFIERS = Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.KeypadModifier  # ввод текста, не сочетание
EDIT_KEYS = (Qt.Key.Key_Delete, Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_F2)  # у шаблона — попытка правки


class NotesScreen(RecessedBlock):
    """Правый экран Maps: поиск и NAMED ONLY, заголовки колонок, таблица нот, строка итогов.

    Модель и фильтр принадлежат странице (это её состояние); экран — только вид. Delete в таблице (не в режиме правки)
    стирает имена выделенных нот. У шаблона попытка правки (ввод, Delete, двойной клик по ноте) — сигнал
    `edit_blocked`.
    """

    edit_blocked = Signal()

    def __init__(self, model: NoteTableModel, proxy: NoteFilter, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.model, self.proxy = model, proxy
        self._left: tuple[str, bool] = ("", False)
        self.screen = Screen()
        self.body.addWidget(self.screen)
        box = self.screen.body

        self.search = SearchField(SEARCH_PLACEHOLDER)
        self.named_only = ScreenCheck(NAMED_ONLY)
        self.named_only.setChecked(True)
        self.named_only.setToolTip(tip(NAMED_ONLY_TIP))
        tools = QHBoxLayout()
        tools.setContentsMargins(0, 0, 0, 0)
        tools.setSpacing(theme.NOTES_TOOLS_GAP - theme.CHECK_PAD)
        tools.addWidget(self.search, 1)
        tools.addWidget(self.named_only, 0, Qt.AlignmentFlag.AlignVCenter)
        box.addLayout(tools)
        box.addSpacing(theme.NOTES_HEAD_TOP)

        self.header = ColumnHeader()
        self.header.tip_for = lambda col: model.headerData(col, Qt.Orientation.Horizontal, Qt.ItemDataRole.ToolTipRole)
        box.addWidget(self.header)
        self.table = NotesView(proxy)
        self.selection = self.table.selection
        self.table.group_clicked.connect(self._toggle_group)
        self.table.installEventFilter(self)
        self.table.doubleClicked.connect(self._double_clicked)
        self.table.delegate.editing.connect(lambda _on: self._show_hint())
        box.addWidget(self.table, 1)
        self.totals = TotalsBar()
        box.addWidget(self.totals)
        self.bar = self.screen.attach(self.table, theme.NOTES_TRACK_TOP, theme.NOTES_TRACK_BOTTOM)

    def show_sort(self, sort: tuple[int, bool] | None) -> None:
        """Стрелка в заголовке колонки: по возрастанию / по убыванию; по группам — без стрелки."""
        self.header.set_sort(sort)

    def set_totals(self, left: str, error: bool = False, tip_text: str = "") -> None:
        """Левая часть строки итогов (ошибки — цветом ошибки) и её подсказка; правая часть — по состоянию."""
        self.totals.setToolTip(tip(tip_text) if tip_text else "")
        self._left = (left, error)
        self._show_hint()

    def _show_hint(self) -> None:
        left, error = self._left
        if self.model.map is None:
            right = ""
        elif self.model.read_only:
            right = READ_ONLY_HINT
        else:
            right = EDIT_HINT if self.table.delegate.edit_index is not None else ""
        self.totals.set_texts(left, right, error)

    def _toggle_group(self, key: str) -> None:
        self.proxy.toggle_group(key)

    def current_note(self) -> int | None:
        index = self.table.currentIndex()
        if not index.isValid():
            return None
        return self.model.note_at(self.proxy.mapToSource(index).row())

    def reveal_note(self, note: int) -> None:
        index = self.proxy.mapFromSource(self.model.note_index(note, COL_NAME))
        if index.isValid():
            self.table.setCurrentIndex(index)
            self.table.scrollTo(index, QAbstractItemView.ScrollHint.PositionAtCenter)

    def _locked(self) -> bool:
        return self.model.read_only and self.model.map is not None

    def _double_clicked(self, index) -> None:
        if self._locked() and self.model.note_at(self.proxy.mapToSource(index).row()) is not None:
            self.edit_blocked.emit()

    def eventFilter(self, obj, event) -> bool:
        if obj is self.table and event.type() == QEvent.Type.KeyPress and self._locked() and (
                event.key() in EDIT_KEYS or (event.text().isprintable() and event.text().strip()
                                             and not event.modifiers() & ~TYPING_MODIFIERS)):
            self.edit_blocked.emit()
            return True
        if (obj is self.table and event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Delete
                and self.table.state() != QAbstractItemView.State.EditingState and not self.model.read_only):
            self.model.clear_names(self.selection.selected)
            return True
        return super().eventFilter(obj, event)

