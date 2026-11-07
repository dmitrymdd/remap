"""Менеджер и редактор карт нот (PySide6): список шаблонов и карт пользователя, таблица нот 0–127.

Здесь — состояние вкладки и действия. Логики карт нет — только вызовы remap.core (duplicate_map, finalize_edit,
validate_map, экспорт) и remap.storage. Вид: `maps_strip.py` (верхняя полоса: клавиши, меню «…», поле карты, Save),
`maps_list.py` (список карт), `maps_table.py` (таблица нот) — в ряду `SplitRow` (ширина списка — в ui.ini), тексты — `maps_text.py`. Статус — во временной нижней
полосе, как на Convert. Диалоги вынесены в методы ask_*/choose_*/show_error, чтобы
тесты могли их подменить.

Шаблон только читается: первая попытка правки (ввод, Delete, двойной клик по ноте) один раз на открытие спрашивает,
сделать ли копию в My Maps. Отмены нет; «Revert changes» в меню «…» возвращает сохранённое состояние.

Write to (primary) на вкладке Maps не правится: его выбирают в профиле, в копии целевой карты.
В JSON карты primary остаётся (старые файлы читаются). Имя на нескольких нотах — бейдж «+N» рядом с именем.
"""
from __future__ import annotations

import copy
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox, QSizePolicy, QVBoxLayout,
    QWidget,
)

from ..core.notemap import NoteMap, duplicate_map, finalize_edit, validate_map
from ..core.notenames import ParseIssue, load_notenames, save_notenames
from ..storage import Storage, id_taken, sanitize_id
from ..templates import list_map_templates, load_map_template
from . import theme
from .maps_list import MapEntry, MapListScreen, MapSection
from .maps_strip import MapsStrip
from .maps_table import NoteFilter, NotesScreen, NoteTableModel
from .maps_text import (
    DUPLICATE_TO_EDIT, DUPLICATE_TO_EDIT_DETAILS, EXPORT_TIP, IMPORT_TIP, MORE_TIP, NEW_TIP, NO_MAP_HINT, NO_MAP_TITLE,
    SAVE_TIP, TEMPLATE, TEMPLATE_TIP, USER, MapRef, format_parse_issues, group_rows, legacy_tip, map_tooltip, next_sort,
    subtitle, totals_text, totals_tip,
)
from .settings import ui_settings
from .split import SplitRow
from .strip import section_width
from .theme import repolish
from .tips import tip

SAVE_KEYS = ("Ctrl+S",)
NAMED_ONLY_KEY = "maps/named_only"
SIDE_KEY = "layout/maps_side"  # ширина списка карт


# --- страница ---

class MapsPage(QWidget):
    """Менеджер карт (слева) и редактор выбранной карты (справа)."""


    def __init__(self, storage: Storage) -> None:
        super().__init__()
        self.storage = storage
        self.settings = ui_settings(storage)
        self.current: MapRef | None = None
        self.base: NoteMap | None = None  # последнее сохранённое состояние
        self.work: NoteMap | None = None  # рабочая копия, её правит таблица
        self.load_issues: list[ParseIssue] = []
        self.legacy = False  # открыта старая карта .txt (при сохранении станет .json)
        self._templates: dict[str, NoteMap] = {}
        self._user_ids: list[str] = []
        self._dirty = False
        self._asked_duplicate = False  # шаблон: вопрос «Duplicate to edit?» уже задан (один раз на открытие)
        self._build_ui()
        self.reload_list()
        self._update_state()

    # --- построение UI ---

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(theme.PAGE_MARGIN, 0, theme.PAGE_MARGIN, 0)
        root.setSpacing(0)
        self.strip = strip = MapsStrip()
        for key, slot, text in ((strip.new_btn, self.new_map, NEW_TIP), (strip.import_btn, self.import_txt, IMPORT_TIP),
                                (strip.export_btn, self.export, EXPORT_TIP), (strip.save_btn, self.save, SAVE_TIP)):
            key.clicked.connect(lambda _=False, slot=slot: slot())
            key.setToolTip(tip(text))
        strip.more_btn.setToolTip(tip(MORE_TIP))
        strip.duplicate_action.triggered.connect(lambda: self.duplicate())
        strip.rename_action.triggered.connect(lambda: self.rename())
        strip.delete_action.triggered.connect(lambda: self.delete())
        strip.revert_action.triggered.connect(lambda: self.revert())
        root.addWidget(strip)
        root.addSpacing(theme.STRIP_GAP)
        # Ctrl+S — на всё окно, пока видна вкладка (у скрытой страницы сочетание не срабатывает)
        self._shortcuts = [QShortcut(QKeySequence(k), self, activated=self._save_if_dirty,
                                     context=Qt.ShortcutContext.WindowShortcut) for k in SAVE_KEYS]

        self.list = MapListScreen()
        self.list.chosen.connect(self._on_chosen)

        self.model = NoteTableModel()
        self.model.edited.connect(self._update_state)
        self.proxy = NoteFilter()
        self.proxy.setSourceModel(self.model)
        self.notes = NotesScreen(self.model, self.proxy)
        self.notes.named_only.setChecked(self.settings.value(NAMED_ONLY_KEY, True, type=bool))
        self.proxy.named_only = self.notes.named_only.isChecked()
        self.notes.search.textChanged.connect(self._apply_filter)
        self.notes.named_only.toggled.connect(self._apply_filter)
        # запоминается только выбор пользователя (новая пустая карта снимает флажок сама)
        self.notes.named_only.clicked.connect(lambda on: self.settings.setValue(NAMED_ONLY_KEY, on))
        self.notes.header.clicked.connect(self.sort_by)
        self.notes.edit_blocked.connect(self._edit_blocked)

        # список карт — боковая колонка (ширина в ui.ini), таблица нот забирает остальное; секции полосы — над ними
        self.split = SplitRow(self.notes, self.list, side_first=True, side_min=theme.POOL_W, main_min=theme.SCENE_W,
                              settings=self.settings, key=SIDE_KEY)
        self.split.layout_changed.connect(
            lambda: strip.set_sections(section_width(self.list.width()), section_width(self.notes.width())))
        root.addWidget(self.split, stretch=1)

        # TEMP: placement undecided — статус в нижней полосе под экранами, как на Convert
        self.status = QLabel()
        self.status.setObjectName("status")
        self.status.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        band = QWidget()
        band.setFixedHeight(theme.BAND_H)
        band_box = QHBoxLayout(band)
        band_box.setContentsMargins(8, theme.BAND_ITEM_TOP, 8, theme.BAND_H - theme.BAND_ITEM_TOP - theme.BAND_ITEM_H)
        band_box.addWidget(self.status, stretch=1)
        root.addWidget(band)

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

    def ask_keep_import(self, title: str, text: str, details: str) -> bool:
        """Проблемы чтения .txt сразу после импорта: Keep (по умолчанию) — оставить карту; Discard import — удалить её."""
        box = QMessageBox(QMessageBox.Icon.Warning, title, text, QMessageBox.StandardButton.NoButton, self)
        box.setInformativeText(details)
        keep = box.addButton("Keep", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Discard import", QMessageBox.ButtonRole.DestructiveRole)
        box.setDefaultButton(keep)
        box.setEscapeButton(keep)
        box.exec()
        return box.clickedButton() is keep

    def show_error(self, text: str) -> None:
        QMessageBox.warning(self, "REMAP", text)

    # --- список ---

    def reload_list(self, select: MapRef | None = None) -> None:
        """Перестроить список; выделение — select или текущая карта (карта при этом не открывается)."""
        select = select or self.current
        self._templates = {}
        templates = []
        for tid, m in list_map_templates():
            self._templates[tid] = m
            templates.append(MapEntry(m.name, subtitle(m), MapRef(TEMPLATE, tid),
                                      tip(map_tooltip(m, TEMPLATE_TIP), title=m.name)))
        try:
            entries, issues = self.storage.list_maps()
        except OSError as e:
            entries, issues = [], []
            self.set_status(f"Cannot read the maps folder: {e}", "error")
        self._user_ids = [e.id for e in entries]
        mine = []
        for e in entries:
            try:
                m, _ = self.storage.load_map(e.id)
            except (OSError, ValueError) as err:
                mine.append(MapEntry(e.name, f"cannot read: {err}", None, tip(str(e.path), title=e.name)))
                continue
            extra = legacy_tip(e.path.name) if e.legacy else ""
            mine.append(MapEntry(e.name, subtitle(m, e.legacy), MapRef(USER, e.id),
                                 tip(map_tooltip(m, extra), title=e.name)))
        if not entries:
            mine.append(MapEntry("No maps yet", "Create, import or duplicate one", None))
        if issues:
            self.set_status(f"Skipped unreadable maps ({len(issues)}): "
                            + ", ".join(i.path.name for i in issues), "error")
        self.list.set_sections([MapSection("BUILT-IN TEMPLATES", tuple(templates), lock=True),
                                MapSection("MY MAPS", tuple(mine))])
        self.list.set_current(select if select in self.list.refs() else None)

    def _on_chosen(self, ref: MapRef) -> None:
        """Пользователь выбрал другую карту в списке: несохранённые правки — спросить; отказ — остаётся прежняя."""
        if ref == self.current or not self.maybe_leave():
            return
        self.open(ref)

    def select(self, ref: MapRef) -> None:
        """Выделить и открыть карту (с вопросом о несохранённых правках)."""
        if ref in self.list.refs():
            self._on_chosen(ref)

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
        self.list.set_current(ref)
        self._asked_duplicate = False
        self.legacy = not ref.read_only and not (self.storage.maps_dir / f"{ref.id}.json").is_file()
        self.work = copy.deepcopy(m)
        self.notes.table.clear_selection()  # другая карта — те же номера, но другие ноты
        self.model.set_map(self.work, ref.read_only)
        self._apply_filter()
        self._update_state()
        self.set_status("")
        return True

    def close_map(self) -> None:
        self.current = self.base = self.work = None
        self.list.set_current(None)
        self.load_issues = []
        self.legacy = False
        self.notes.table.clear_selection()
        self.model.set_map(None, True)
        self._update_state()

    def sort_by(self, column: int) -> None:
        """Клик по заголовку колонки: по возрастанию → по убыванию → снова по группам инструментов (вид по
        умолчанию); клик по другой колонке — сразу по возрастанию. Стрелка заголовка показывает состояние."""
        sort = next_sort(self.model.sort, column)
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

    def _save_if_dirty(self) -> None:
        if self.dirty:
            self.save()

    def _edit_blocked(self) -> None:
        """Попытка править шаблон: один раз на открытие предложить копию в My Maps."""
        if self._asked_duplicate or self.current is None or not self.current.read_only:
            return
        self._asked_duplicate = True
        if self.confirm("Built-in template", DUPLICATE_TO_EDIT, DUPLICATE_TO_EDIT_DETAILS):
            self.duplicate()

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
        self._dirty = dirty
        read_only = has_map and ref.read_only
        self.strip.show_state(has_map=has_map, read_only=read_only, dirty=dirty)
        self.notes.search.setEnabled(has_map)
        self.notes.named_only.setEnabled(has_map)
        field = self.strip.field
        if not has_map:
            field.set_map(NO_MAP_TITLE, locked=False)
            field.setToolTip("")
            self.notes.set_totals(NO_MAP_HINT.upper())
            return
        field.set_map(self.work.name, locked=read_only)
        extra = TEMPLATE_TIP if read_only else legacy_tip(f"{ref.id}.txt") if self.legacy else ""
        field.setToolTip(tip(extra, title=self.work.name) if extra else tip(self.work.name))
        errors = [i.message for i in validate_map(self.work) if i.severity == "error"]
        left, error = totals_text(len(self.work.names), errors)
        self.notes.set_totals(left, error, totals_tip(errors, self.load_issues))

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
        name = self.ask_unique_name("Import map", m.name)
        if name is None:
            return
        m.name = name
        m.meta.notes = f"Imported from {Path(path).name}"
        previous = self.current
        ref = self._add_and_open(m)
        if ref is None:
            return
        self.set_status(f'Imported "{name}": {len(m.names)} notes.', "ok")
        # карта уже импортирована: проблемы чтения — сразу показать, что пропущено, и дать отказаться
        if issues and not self.ask_keep_import(
                "Import REAPER note names", f"{Path(path).name}: {len(m.names)} notes imported, {len(issues)} issue(s).",
                format_parse_issues(issues)):
            self._discard_import(ref, previous)

    def _discard_import(self, ref: MapRef, previous: MapRef | None) -> None:
        """Удалить только что импортированную карту и вернуться к прежней."""
        try:
            self.storage.delete_map(ref.id)
        except OSError as e:
            self.show_error(f"Cannot delete the map:\n\n{e}")
            return
        self.close_map()
        self.reload_list()
        if previous is not None and previous in self.list.refs():
            self.open(previous)
        self.set_status("Import discarded.", "ok")

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
        self.status.setText(text)
        repolish(self.status, "state", state)
