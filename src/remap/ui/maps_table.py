"""Таблица нот вкладки Maps: модель над рабочей копией карты, фильтр, делегат имени с бейджем «+N» и панель
(сведения о карте, поиск, «только с именем», таблица, ошибки карты)."""
from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QEvent, QModelIndex, QRectF, QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QStyle,
    QStyledItemDelegate, QStyleOptionViewItem, QTableView, QVBoxLayout, QWidget,
)

from ..core.notemap import NoteMap, articulations, normalize_name, set_note_name
from ..core.pitch import note_tip, pitch_name
from . import plates, theme
from .maps_text import COL_NAME, COL_NOTE, COLUMN_TIPS, COLUMNS, EDIT_TIP, SORT_TIPS, LayoutRow, group_rows

OTHERS_ROLE = Qt.ItemDataRole.UserRole + 4  # сколько ещё нот карты с этим именем (бейдж «+N»)


def update_spans(table: QTableView, columns: int) -> None:
    """Заголовки групп — на всю ширину таблицы (span пересчитывается после фильтрации и перестройки).
    Модель таблицы — модель с row_at() или прокси над ней."""
    table.clearSpans()
    view = table.model()
    proxy = view if isinstance(view, QSortFilterProxyModel) else None
    model = proxy.sourceModel() if proxy is not None else view
    for r in range(view.rowCount()):
        src = proxy.mapToSource(proxy.index(r, 0)).row() if proxy is not None else r
        if model.row_at(src).is_header:
            table.setSpan(r, 0, 1, columns)


def header_data(row: LayoutRow, col: int, role):
    """Данные строки-заголовка группы в таблице нот."""
    if role == Qt.ItemDataRole.DisplayRole and col == 0:
        return row.label.upper()
    if role == Qt.ItemDataRole.FontRole:
        f = QFont()
        f.setBold(True)
        f.setPointSizeF(8)
        return f
    if role == Qt.ItemDataRole.ForegroundRole:
        return QColor(theme.ACCENT)
    if role == Qt.ItemDataRole.BackgroundRole:
        return QColor(theme.RECESS_BOTTOM)
    return None


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
                tip = COLUMN_TIPS[section] + "\n" + SORT_TIPS[section]
                if section == COL_NAME and not self.read_only:
                    return tip + "\n" + EDIT_TIP
                return tip
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or self.map is None:
            return None
        row = self.rows[index.row()]
        if row.is_header:
            return header_data(row, index.column(), role)
        n, col = row.note, index.column()
        name = self.map.names.get(n)
        notes = self.group(n)
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            if col == COL_NOTE:
                return str(n)
            if col == COL_NAME:
                return name or ""
            return None
        if role == OTHERS_ROLE and col == COL_NAME:
            return max(0, len(notes) - 1)
        if role == Qt.ItemDataRole.ForegroundRole and name is None:
            return QColor(theme.PLATE_DELETED_NAME)
        if role == Qt.ItemDataRole.TextAlignmentRole and col != COL_NAME:
            return int(Qt.AlignmentFlag.AlignCenter)
        if role == Qt.ItemDataRole.ToolTipRole:
            tip = note_tip([n])
            if col == COL_NAME and len(notes) > 1:
                tip = f"{name}\n{tip}\nOn notes {', '.join(map(str, notes))}"
            return tip
        return None

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

    def _changed(self) -> None:
        self.refresh()  # меняются счётчики и подсветка всех нот затронутых артикуляций
        self.edited.emit()


class NameDelegate(QStyledItemDelegate):
    """Имя и бейдж «+N» (имя ещё на N нотах карты) — как в виде «кабелями». Правка имени — как обычно."""

    def paint(self, p, option, index) -> None:
        others = index.data(OTHERS_ROLE)
        if not others:
            super().paint(p, option, index)
            return
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        style = opt.widget.style() if opt.widget is not None else QApplication.style()
        rect = style.subElementRect(QStyle.SubElement.SE_ItemViewItemText, opt, opt.widget)
        margin = style.pixelMetric(QStyle.PixelMetric.PM_FocusFrameHMargin, opt, opt.widget) + 1
        badge = f"+{others}"
        p.save()
        bw = plates.badge_width(badge)
        # имя рисует сам стиль (тот же отступ, что у строк без бейджа); место под бейдж — заранее
        opt.text = opt.fontMetrics.elidedText(opt.text, Qt.TextElideMode.ElideRight,
                                              max(0, rect.width() - 2 * margin - bw - 8))
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, p, opt.widget)
        x = rect.left() + margin + opt.fontMetrics.horizontalAdvance(opt.text) + 8
        h = theme.BADGE_HEIGHT
        plates.paint_badge(p, QRectF(x, rect.center().y() - h / 2 + 1, bw, h), badge)
        p.restore()


class NoteFilter(QSortFilterProxyModel):
    """«Только ноты с именем» + поиск по имени, номеру ноты или названию высоты.
    Заголовок группы виден, если видна хотя бы одна нота группы.

    Фильтр не пересчитывается при правке (dynamicSortFilter выключен): строка, у которой стёрли имя,
    не исчезает из-под курсора. Пересчёт — при смене фильтра или карты.
    """

    def __init__(self) -> None:
        super().__init__()
        self.named_only = True
        self.query = ""
        self.setDynamicSortFilter(False)

    def set_filter(self, named_only: bool, query: str) -> None:
        self.beginFilterChange()
        self.named_only, self.query = named_only, query
        self.endFilterChange()

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


TYPING_MODIFIERS = Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.KeypadModifier  # ввод текста, не сочетание


class NotesPanel(QWidget):
    """Правая колонка без заголовка и кнопок: сведения о карте, поиск и «только с именем», таблица нот, ошибки.

    Модель и фильтр принадлежат странице (это её состояние); панель — только вид. Delete в таблице (не в режиме правки
    ячейки) стирает имена выделенных нот. У шаблона попытка правки (ввод, Delete, двойной клик по ноте) —
    сигнал `edit_blocked`.
    """

    edit_blocked = Signal()

    def __init__(self, model: NoteTableModel, proxy: NoteFilter, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.model, self.proxy = model, proxy
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(6)
        self.source_label = QLabel()
        self.source_label.setObjectName("muted")
        self.source_label.setWordWrap(True)
        self.source_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        box.addWidget(self.source_label)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search: name or note number")
        self.search.setClearButtonEnabled(True)
        self.named_only = QCheckBox("Show only named notes")
        self.named_only.setChecked(True)
        tools = QHBoxLayout()
        tools.addWidget(self.search, stretch=1)
        tools.addSpacing(8)
        tools.addWidget(self.named_only)
        box.addLayout(tools)

        self.table = QTableView()
        self.table.setModel(proxy)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked
                                   | QAbstractItemView.EditTrigger.EditKeyPressed
                                   | QAbstractItemView.EditTrigger.AnyKeyPressed)
        header = self.table.horizontalHeader()
        header.setHighlightSections(False)
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(False)  # по умолчанию — группы, без стрелки
        header.setSectionResizeMode(COL_NOTE, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(COL_NOTE, 64)
        header.setSectionResizeMode(COL_NAME, QHeaderView.ResizeMode.Stretch)
        self.table.setItemDelegateForColumn(COL_NAME, NameDelegate(self.table))
        self.table.installEventFilter(self)
        self.table.doubleClicked.connect(self._double_clicked)
        for sig in (proxy.modelReset, proxy.layoutChanged, proxy.rowsInserted, proxy.rowsRemoved):
            sig.connect(lambda *_: update_spans(self.table, len(COLUMNS)))
        box.addWidget(self.table, stretch=1)

        self.issues_label = QLabel()
        self.issues_label.setObjectName("issues")
        self.issues_label.setWordWrap(True)
        box.addWidget(self.issues_label)

    def show_sort(self, sort: tuple[int, bool] | None) -> None:
        """Стрелка в заголовке столбца: по возрастанию / по убыванию; по группам — без стрелки."""
        header = self.table.horizontalHeader()
        header.setSortIndicatorShown(sort is not None)
        if sort is not None:
            header.setSortIndicator(sort[0], Qt.SortOrder.DescendingOrder if sort[1] else Qt.SortOrder.AscendingOrder)

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
                event.key() == Qt.Key.Key_Delete or (event.text().isprintable() and event.text().strip()
                                                    and not event.modifiers() & ~TYPING_MODIFIERS)):
            self.edit_blocked.emit()
            return True
        if (obj is self.table and event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Delete
                and self.table.state() != QAbstractItemView.State.EditingState and not self.model.read_only):
            rows = {self.proxy.mapToSource(i).row() for i in self.table.selectionModel().selectedRows()}
            for n in sorted(n for n in map(self.model.note_at, rows) if n is not None):
                self.model.set_name(n, "")
            return True
        return super().eventFilter(obj, event)
