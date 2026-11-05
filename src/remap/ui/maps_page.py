"""Менеджер и редактор карт нот (PySide6): список шаблонов и карт пользователя, таблица нот 0–127.

Здесь — состояние вкладки и действия. Логики карт нет — только вызовы remap.core (duplicate_map, finalize_edit,
validate_map, экспорт) и remap.storage. Вид: `maps_strip.py` (кнопки, заголовок, статус), `maps_list.py` (список карт),
`maps_table.py` (таблица нот), тексты — `maps_text.py`. Диалоги вынесены в методы ask_*/choose_*/show_error, чтобы
тесты могли их подменить.

Write to (primary) на вкладке Maps не правится: его выбирают в профиле, в копии целевой карты.
В JSON карты primary остаётся (старые файлы читаются). Имя на нескольких нотах — бейдж «+N» рядом с именем.
"""
from __future__ import annotations

import copy
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QInputDialog, QLineEdit, QListWidgetItem, QMessageBox, QVBoxLayout, QWidget,
)

from ..core.notemap import NoteMap, duplicate_map, finalize_edit, validate_map
from ..core.notenames import ParseIssue, load_notenames, save_notenames
from ..storage import Storage, id_taken, sanitize_id
from ..templates import list_map_templates, load_map_template
from . import theme
from .maps_list import REF_ROLE, MapList
from .maps_strip import MapsStrip
from .maps_table import NoteFilter, NotesPanel, NoteTableModel
from .maps_text import (
    OLD_TXT_CHIP, OLD_TXT_CHIP_TIP, NO_MAP_HINT, NO_MAP_TITLE, TEMPLATE, TEMPLATE_CHIP, TEMPLATE_CHIP_TIP, TEMPLATE_TIP,
    USER, MapRef, format_parse_issues, group_rows, issues_text, legacy_tip, map_info, map_tooltip, subtitle,
)
from .theme import repolish


# --- страница ---

class MapsPage(QWidget):
    """Менеджер карт (слева) и редактор выбранной карты (справа)."""

    dirty_changed = Signal(bool)

    def __init__(self, storage: Storage) -> None:
        super().__init__()
        self.storage = storage
        self.current: MapRef | None = None
        self.base: NoteMap | None = None  # последнее сохранённое состояние
        self.work: NoteMap | None = None  # рабочая копия, её правит таблица
        self.load_issues: list[ParseIssue] = []
        self.legacy = False  # открыта старая карта .txt (при сохранении станет .json)
        self._templates: dict[str, NoteMap] = {}
        self._user_ids: list[str] = []
        self._dirty = False
        self._build_ui()
        self.reload_list()
        self._update_state()

    # --- построение UI ---

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(theme.PAGE_MARGIN, 10, theme.PAGE_MARGIN, 16)
        root.setSpacing(16)
        self.strip = strip = MapsStrip()
        strip.new_btn.clicked.connect(self.new_map)
        strip.import_btn.clicked.connect(self.import_txt)
        strip.duplicate_btn.clicked.connect(self.duplicate)
        strip.rename_btn.clicked.connect(self.rename)
        strip.delete_btn.clicked.connect(self.delete)
        strip.export_btn.clicked.connect(self.export)
        strip.edit_copy_btn.clicked.connect(self.duplicate)
        strip.revert_btn.clicked.connect(self.revert)
        strip.save_btn.clicked.connect(self.save)

        left = QVBoxLayout()
        left.setSpacing(8)
        self.list = MapList()
        self.list.currentItemChanged.connect(self._on_current_changed)
        left.addWidget(self.list, stretch=1)
        left.addLayout(strip.actions)
        left_box = QWidget()
        left_box.setLayout(left)
        left_box.setFixedWidth(290)
        root.addWidget(left_box)

        self.model = NoteTableModel()
        self.model.edited.connect(self._update_state)
        self.proxy = NoteFilter()
        self.proxy.setSourceModel(self.model)
        self.notes = NotesPanel(self.model, self.proxy)
        self.notes.search.textChanged.connect(self._apply_filter)
        self.notes.named_only.toggled.connect(self._apply_filter)
        self.notes.table.horizontalHeader().sectionClicked.connect(self.sort_by)

        right = QVBoxLayout()
        right.setSpacing(6)
        right.addLayout(strip.head)
        right.addWidget(self.notes, stretch=1)
        right.addLayout(strip.bottom)
        root.addLayout(right, stretch=1)

    # --- диалоги (тесты подменяют эти методы) ---

    def ask_text(self, title: str, label: str, default: str) -> str | None:
        text, ok = QInputDialog.getText(self, title, label, QLineEdit.EchoMode.Normal, default)
        return text if ok else None

    def confirm(self, title: str, text: str, details: str = "") -> bool:
        box = QMessageBox(QMessageBox.Icon.Question, title, text,
                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, self)
        if details:
            box.setInformativeText(details)
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        return box.exec() == QMessageBox.StandardButton.Yes

    def ask_save_changes(self) -> str:
        """"save" / "discard" / "cancel"."""
        answer = QMessageBox.question(
            self, "Unsaved changes", f'Save changes to "{self.work.name}"?',
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save)
        return {QMessageBox.StandardButton.Save: "save",
                QMessageBox.StandardButton.Discard: "discard"}.get(answer, "cancel")

    def choose_open_file(self) -> str | None:
        path, _ = QFileDialog.getOpenFileName(self, "Import REAPER note names", "",
                                              "REAPER note names (*.txt);;All files (*.*)")
        return path or None

    def choose_save_file(self, default_name: str) -> str | None:
        path, _ = QFileDialog.getSaveFileName(self, "Export REAPER note names", default_name,
                                              "REAPER note names (*.txt)")
        return path or None

    def show_error(self, text: str) -> None:
        QMessageBox.warning(self, "REMAP", text)

    # --- список ---

    def reload_list(self, select: MapRef | None = None) -> None:
        """Перестроить список; выделение — select или текущая карта (сигналы при этом не идут)."""
        select = select or self.current
        self.list.blockSignals(True)
        self.list.clear()
        self._templates = {}
        self.list.add_header("BUILT-IN TEMPLATES")
        for tid, m in list_map_templates():
            self._templates[tid] = m
            self.list.add_entry(f"🔒  {m.name}", subtitle(m), MapRef(TEMPLATE, tid), map_tooltip(m, TEMPLATE_TIP))
        self.list.add_header("MY MAPS")
        try:
            entries, issues = self.storage.list_maps()
        except OSError as e:
            entries, issues = [], []
            self.set_status(f"Cannot read the maps folder: {e}", "error")
        self._user_ids = [e.id for e in entries]
        for e in entries:
            try:
                m, _ = self.storage.load_map(e.id)
            except (OSError, ValueError) as err:
                self.list.add_entry(e.name, f"cannot read: {err}", None, str(e.path))
                continue
            extra = legacy_tip(e.path.name) if e.legacy else ""
            self.list.add_entry(e.name, subtitle(m, e.legacy), MapRef(USER, e.id), map_tooltip(m, extra))
        if not entries:
            self.list.add_entry("No maps yet", "Create, import or duplicate one", None)
        if issues:
            self.set_status(f"Skipped unreadable maps ({len(issues)}): "
                            + ", ".join(i.path.name for i in issues), "error")
        row = self.list.row_of(select) if select is not None else -1
        if row >= 0:
            self.list.setCurrentRow(row)
        self.list.blockSignals(False)

    def _on_current_changed(self, cur: QListWidgetItem | None, prev: QListWidgetItem | None) -> None:
        ref = cur.data(REF_ROLE) if cur is not None else None
        if ref is None or ref == self.current:
            return
        if not self.maybe_leave():
            self.list.blockSignals(True)
            self.list.setCurrentItem(prev)
            self.list.blockSignals(False)
            return
        self.open(ref)

    def select(self, ref: MapRef) -> None:
        """Выделить и открыть карту (с вопросом о несохранённых правках)."""
        row = self.list.row_of(ref)
        if row >= 0:
            self.list.setCurrentRow(row)

    # --- редактор ---

    @property
    def dirty(self) -> bool:
        return self._dirty

    def open(self, ref: MapRef) -> bool:
        try:
            if ref.read_only:
                m, issues = load_map_template(ref.id), []
            else:
                m, issues = self.storage.load_map(ref.id)
        except (OSError, ValueError, KeyError) as e:
            self.show_error(f"Cannot open the map:\n\n{e}")
            return False
        self.current, self.base, self.load_issues = ref, m, issues
        self.legacy = not ref.read_only and not (self.storage.maps_dir / f"{ref.id}.json").is_file()
        self.work = copy.deepcopy(m)
        self.model.set_map(self.work, ref.read_only)
        self._apply_filter()
        self._update_state()
        self.set_status("")
        return True

    def close_map(self) -> None:
        self.current = self.base = self.work = None
        self.load_issues = []
        self.legacy = False
        self.model.set_map(None, True)
        self._update_state()

    def sort_by(self, column: int) -> None:
        """Клик по заголовку колонки: по возрастанию → по убыванию → снова по группам инструментов (вид по
        умолчанию); клик по другой колонке — сразу по возрастанию. Стрелка заголовка показывает состояние."""
        sort = self.model.sort
        if sort is None or sort[0] != column:
            sort = (column, False)
        elif not sort[1]:
            sort = (column, True)
        else:
            sort = None
        self.notes.show_sort(sort)
        note = self.notes.current_note()
        self.model.set_sort(sort)
        self.proxy.set_filter(self.notes.named_only.isChecked(), self.notes.search.text())
        if note is not None:
            self.notes.reveal_note(note)

    def _apply_filter(self) -> None:
        self.model.relayout()  # переименованные ноты встают в свои группы
        self.proxy.set_filter(self.notes.named_only.isChecked(), self.notes.search.text())

    def maybe_leave(self) -> bool:
        """Перед уходом с карты: несохранённые правки — спросить. False — остаться."""
        if not self.dirty:
            return True
        answer = self.ask_save_changes()
        if answer == "save":
            return self.save()
        if answer == "discard":
            self.revert()
            return True
        return False

    def save(self) -> bool:
        if self.current is None or self.current.read_only or self.work is None:
            return False
        errors = [i.message for i in validate_map(self.work) if i.severity == "error"]
        if errors:
            self.show_error("The map has errors and was not saved:\n\n" + "\n".join(errors))
            return False
        out = finalize_edit(self.base, self.work)
        try:
            self.storage.save_map(out, map_id=self.current.id, overwrite=True)
        except (OSError, ValueError) as e:
            self.show_error(f"Cannot save the map:\n\n{e}")
            return False
        # рабочую копию не пересоздаём, чтобы таблица не теряла прокрутку и выделение
        self.base = out
        self.work.meta = copy.deepcopy(out.meta)
        self.work.order = copy.deepcopy(out.order)
        self.work.primary = set(out.primary)
        self.load_issues = []
        self.legacy = False
        self.model.refresh()
        if self.model.rows != group_rows(self.work.names, list(range(128))):
            self._apply_filter()  # группы изменились; иначе не сбрасываем прокрутку и выделение
        self.reload_list()
        self._update_state()
        self.set_status(f'Saved "{out.name}".', "ok")
        return True

    def revert(self) -> None:
        if self.base is None:
            return
        self.work = copy.deepcopy(self.base)
        self.model.set_map(self.work, self.current.read_only)
        self._apply_filter()
        self._update_state()

    def _update_state(self) -> None:
        has_map = self.work is not None
        ref = self.current
        dirty = has_map and (self.work.names != self.base.names or self.work.primary != self.base.primary)
        if dirty != self._dirty:
            self._dirty = dirty
            self.dirty_changed.emit(dirty)
        read_only = has_map and ref.read_only
        self.strip.show_state(has_map=has_map, read_only=read_only, dirty=dirty)
        self.notes.search.setEnabled(has_map)
        self.notes.named_only.setEnabled(has_map)
        if not has_map:
            self.strip.set_kind("", "")
            self.strip.title.setText(NO_MAP_TITLE)
            self.notes.source_label.setText(NO_MAP_HINT)
            self.notes.issues_label.setText("")
            return
        if read_only:
            self.strip.set_kind(TEMPLATE_CHIP, TEMPLATE_CHIP_TIP)
        else:
            self.strip.set_kind(OLD_TXT_CHIP if self.legacy else "", OLD_TXT_CHIP_TIP)
        self.strip.title.setText(self.work.name)
        self.notes.source_label.setText(map_info(self.work))
        self._update_issues()

    def _update_issues(self) -> None:
        errors = [i.message for i in validate_map(self.work) if i.severity == "error"]
        label = self.notes.issues_label
        label.setText(issues_text(errors, len(self.load_issues)))
        label.setToolTip(format_parse_issues(self.load_issues) if self.load_issues else "")
        repolish(label, "state", "error" if errors else "")

    # --- действия ---

    def ask_unique_name(self, title: str, default: str, exclude_id: str | None = None) -> str | None:
        """Имя новой карты; ID (имя файла) не должен совпадать с существующей картой. None — отмена."""
        while True:
            text = self.ask_text(title, "Map name:", default)
            if text is None:
                return None
            text = text.strip()
            if not text:
                self.show_error("The name cannot be empty.")
                continue
            if id_taken(text, self._user_ids, exclude_id):
                self.show_error(f'A map named "{text}" already exists. Choose another name.')
                default = text
                continue
            return text

    def _add_and_open(self, m: NoteMap) -> MapRef | None:
        try:
            map_id = self.storage.save_map(m)
        except (OSError, ValueError) as e:
            self.show_error(f"Cannot save the map:\n\n{e}")
            return None
        ref = MapRef(USER, map_id)
        self.reload_list(select=ref)
        self.open(ref)
        return ref

    def new_map(self) -> None:
        if not self.maybe_leave():
            return
        name = self.ask_unique_name("New map", "New map")
        if name is None:
            return
        if self._add_and_open(NoteMap(name=name)):
            self.notes.named_only.setChecked(False)  # в пустой карте иначе нечего показать
            self.set_status(f'Created "{name}". Type names next to the notes and click Save.', "ok")

    def import_txt(self) -> None:
        if not self.maybe_leave():
            return
        path = self.choose_open_file()
        if not path:
            return
        try:
            m, issues = load_notenames(path)
        except (OSError, ValueError) as e:
            self.show_error(f"Cannot read the file:\n\n{e}")
            return
        if issues and not self.confirm(
                "Import REAPER note names",
                f"{Path(path).name}: {len(m.names)} notes read, {len(issues)} issue(s). Import anyway?",
                format_parse_issues(issues)):
            return
        name = self.ask_unique_name("Import map", m.name)
        if name is None:
            return
        m.name = name
        m.meta.notes = f"Imported from {Path(path).name}"
        if self._add_and_open(m):
            self.set_status(f'Imported "{name}": {len(m.names)} notes.', "ok")

    def duplicate(self) -> None:
        if self.base is None or not self.maybe_leave():
            return
        src, from_template = self.base, self.current.read_only
        name = self.ask_unique_name("Duplicate map", f"{src.name} (copy)")
        if name is None:
            return
        if self._add_and_open(duplicate_map(src, name, from_template=from_template)):
            self.set_status(f'Created "{name}" from "{src.name}".', "ok")

    def rename(self) -> None:
        if self.current is None or self.current.read_only or not self.maybe_leave():
            return
        old_ref, old_name = self.current, self.base.name
        name = self.ask_unique_name("Rename map", old_name, exclude_id=old_ref.id)
        if name is None or name == old_name:
            return
        m = copy.deepcopy(self.base)
        m.name = name
        try:
            new_id = self.storage.rename_map(old_ref.id, m)
        except (OSError, ValueError) as e:
            self.show_error(f"Cannot rename the map:\n\n{e}")
            return
        ref = MapRef(USER, new_id)
        self.current = None
        self.reload_list(select=ref)
        self.open(ref)
        self.set_status(f'Renamed "{old_name}" to "{name}".', "ok")

    def delete(self) -> None:
        if self.current is None or self.current.read_only:
            return
        name = self.base.name
        if not self.confirm("Delete map", f'Delete the map "{name}"? This cannot be undone.'):
            return
        try:
            self.storage.delete_map(self.current.id)
        except OSError as e:
            self.show_error(f"Cannot delete the map:\n\n{e}")
            return
        self.close_map()
        self.reload_list()
        self.set_status(f'Deleted "{name}".', "ok")

    def export(self) -> None:
        """Экспорт всей карты в том виде, как она в редакторе (включая несохранённые правки)."""
        if self.work is None:
            return
        m = finalize_edit(self.base, self.work)
        path = self.choose_save_file(sanitize_id(m.name) + ".txt")
        if not path:
            return
        try:
            save_notenames(m, path)
        except OSError as e:
            self.show_error(f"Cannot export the map:\n\n{e}")
            return
        self.set_status(f"Exported to {path}.", "ok")

    def set_status(self, text: str, state: str = "") -> None:
        self.strip.set_status(text, state)
