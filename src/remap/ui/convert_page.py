"""Страница Convert: исходные файлы (drop, диалог, Ctrl+V), профиль и направление, папка результатов, конвертация
пакетом, итог каждого файла и окно Details, результат наружу (перетаскивание в DAW, Ctrl+C).

Логики конвертации здесь нет — только вызов remap.core.convert_batch и показ отчёта; тексты — ui/convert_text.py.
Перетаскивание файлов принимает всё окно: оно передаёт события сюда (`drag_enter()`, `drag_leave()`, `drop()`).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QMimeData, QPoint, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QDrag, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit,
    QMenu, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from ..core import FileResult, RemapProfile, convert_batch, output_path_for
from ..core.profile import FORWARD, REVERSE
from ..storage import Storage
from . import theme
from .convert_strip import ConvertStrip
from .convert_text import _plural, batch_summary, expand_midi_paths, is_midi, result_details, result_line
from .profiles_page import SWAP_TIP, map_summary
from .theme import repolish as _repolish
from .tips import tip

DIRECTION_KEY = "convert/direction"  # ui.ini: направление конвертации, общее для всех профилей
NO_PROFILES = "NO PROFILES"
CREATE_PROFILE = "No remap profiles yet: create one on the Profiles tab"
NEXT_TO_SOURCES = "Next to source files"
NO_VALUE = "—"  # поле SOURCE / TARGET без профиля


def midi_paths_from_mime(mime: QMimeData) -> list[Path]:
    """Локальные .mid/.midi (и содержимое папок) из mime-данных (DnD или буфер обмена); иначе — пути в тексте."""
    paths = [Path(u.toLocalFile()) for u in mime.urls() if u.isLocalFile()]
    if not paths and mime.hasText():
        paths = [Path(line.strip().strip('"')) for line in mime.text().splitlines() if line.strip()]
    return expand_midi_paths(paths)


def _label(text: str, name: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName(name)
    return label


class SourceZone(QFrame):
    """Зона исходных файлов. Пустая — «перетащи сюда»; один файл — имя и папка; несколько — компактный список
    (имя и кнопка удаления, «Clear all»). После конвертации у каждого файла (и у одного) — строка результата
    (result_line: ✓ итог / ✗ ошибка) и «Details» (полный отчёт в окне). Клик открывает диалог выбора файлов;
    сам drop и Ctrl+V принимает всё окно."""

    ROW_H, RESULT_ROW_H = 26, 44  # строка списка; с результатом под именем
    LIST_MAX_H = 4 * RESULT_ROW_H + 2  # длиннее — прокрутка внутри списка

    def __init__(self, on_click, on_remove=None, on_clear=None, on_details=None) -> None:
        super().__init__()
        self.setObjectName("drop")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._on_click = on_click
        self._on_remove = on_remove or (lambda path: None)
        self._on_clear = on_clear or (lambda: None)
        self._on_details = on_details or (lambda path: None)
        self.paths: list[Path] = []
        self.results: dict[Path, FileResult] = {}
        self.icon = _label("↓", "icon")
        self.name = _label("", "cardName")
        self.folder = _label("", "muted")
        for w in (self.name, self.folder):
            w.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        box = QVBoxLayout(self)
        box.setContentsMargins(16, 14, 16, 14)
        box.setSpacing(2)
        for w in (self.icon, self.name, self.folder):
            w.setAlignment(Qt.AlignmentFlag.AlignCenter)
            box.addWidget(w)
        # один файл: строка результата и Details под папкой
        self.single = QWidget()
        self.single_result, self.single_details = self._result_widgets(lambda: self._details_of_single())
        single = QHBoxLayout(self.single)
        single.setContentsMargins(0, 4, 0, 0)
        single.addStretch(1)
        single.addWidget(self.single_result)
        single.addWidget(self.single_details)
        single.addStretch(1)
        box.addWidget(self.single)
        # несколько файлов: заголовок «N files · Clear all» и список строк с кнопками удаления
        self.files_box = QWidget()
        self.count = _label("", "cardName")
        self.clear_btn = QPushButton("Clear all")
        self.clear_btn.setObjectName("link")
        self.clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_btn.setToolTip("Remove all files (Esc)")
        self.clear_btn.clicked.connect(lambda: self._on_clear())
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.addWidget(self.count, stretch=1)
        head.addWidget(self.clear_btn)
        self.rows = QWidget()
        self.rows_box = QVBoxLayout(self.rows)
        self.rows_box.setContentsMargins(0, 0, 0, 0)
        self.rows_box.setSpacing(0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setWidget(self.rows)
        files = QVBoxLayout(self.files_box)
        files.setContentsMargins(0, 0, 0, 0)
        files.setSpacing(4)
        files.addLayout(head)
        files.addWidget(self.scroll)
        box.addWidget(self.files_box)
        self.set_files([])

    def _result_widgets(self, on_details) -> tuple[QLabel, QPushButton]:
        result = _label("", "status")
        result.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        details = QPushButton("Details")
        details.setObjectName("link")
        details.setCursor(Qt.CursorShape.PointingHandCursor)
        details.setToolTip("Show the full report")
        details.clicked.connect(lambda _=False: on_details())
        return result, details

    def _details_of_single(self) -> None:
        if self.paths:
            self._on_details(self.paths[0])

    @staticmethod
    def _show_result(label: QLabel, details: QPushButton, res: FileResult | None) -> None:
        label.setText(result_line(res) if res is not None else "")
        label.setToolTip("" if res is None or res.ok else (res.error or ""))
        _repolish(label, "state", "" if res is None else "ok" if res.ok else "error")
        for w in (label, details):
            w.setVisible(res is not None)

    def set_files(self, paths: list[Path], results: dict[Path, FileResult] | None = None) -> None:
        """Список файлов и (после конвертации) их результаты."""
        self.paths, self.results = list(paths), dict(results or {})
        many = len(paths) > 1
        self.files_box.setVisible(many)
        for w in (self.icon, self.name, self.folder):
            w.setVisible(not many)
        self.single.setVisible(len(paths) == 1 and paths[0] in self.results)
        if not paths:
            self.icon.setText("↓")
            self.name.setText("Drop a MIDI file here")
            self.folder.setText("or click to browse  ·  Ctrl+V to paste a copied file")
        elif not many:
            self.icon.setText("♫")
            self.name.setText(paths[0].name)
            self.folder.setText(str(paths[0].parent))
            self._show_result(self.single_result, self.single_details, self.results.get(paths[0]))
        else:
            self.count.setText(f"{len(paths)} files")
            while self.rows_box.count():
                item = self.rows_box.takeAt(0)
                if item.widget() is not None:  # прежняя строка — скрыть сразу (удалится в цикле событий)
                    item.widget().hide()
                    item.widget().deleteLater()
            height = 0
            for path in paths:
                row = self._row(path)
                height += row.height()
                self.rows_box.addWidget(row)
            self.scroll.setFixedHeight(min(height, self.LIST_MAX_H))
        self.setToolTip((f"{paths[0]}\n" if len(paths) == 1 else "")
                        + "Click or drop to add files · Esc to clear" if paths else "")
        _repolish(self, "loaded", "true" if paths else "false")
        self.updateGeometry()

    def row_widgets(self) -> list[QWidget]:
        """Строки списка (несколько файлов) в порядке файлов."""
        return [self.rows_box.itemAt(i).widget() for i in range(self.rows_box.count())]

    def _row(self, path: Path) -> QWidget:
        res = self.results.get(path)
        row = QWidget()
        row.setFixedHeight(self.RESULT_ROW_H if res is not None else self.ROW_H)
        row.name = name = _label(path.name, "muted")
        name.setToolTip(str(path))
        name.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        remove = QPushButton("✕")
        remove.setObjectName("remove")
        remove.setFixedSize(24, 22)
        remove.setCursor(Qt.CursorShape.PointingHandCursor)
        remove.setToolTip("Remove from the list")
        remove.clicked.connect(lambda _=False, p=path: self._on_remove(p))
        row.result, row.details = self._result_widgets(lambda p=path: self._on_details(p))
        self._show_result(row.result, row.details, res)
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.addWidget(name, stretch=1)
        top.addWidget(remove)
        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 28, 0)
        bottom.addWidget(row.result, stretch=1)
        bottom.addWidget(row.details)
        box = QVBoxLayout(row)
        box.setContentsMargins(2, 0, 2, 0)
        box.setSpacing(0)
        box.addLayout(top)
        if res is not None:
            box.addLayout(bottom)
        return row

    def set_active(self, active: bool) -> None:
        """Подсветка во время перетаскивания файла над окном."""
        _repolish(self, "active", "true" if active else "false")

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self._on_click()
        super().mouseReleaseEvent(event)


class OutputCard(QFrame):
    """Карточка результата: клик — показать файл в Проводнике, перетаскивание — в DAW/Проводник (все файлы).
    Клик от перетаскивания отличается стандартным порогом startDragDistance."""

    def __init__(self, on_click) -> None:
        super().__init__()
        self.setObjectName("card")
        self._on_click = on_click
        self.paths: list[Path] = []
        self.ready = False
        self._press_pos: QPoint | None = None
        self.name = _label("Output file", "cardName")
        self.folder = _label("Not converted yet", "muted")
        for label in (self.name, self.folder):
            label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(self.name)
        text.addWidget(self.folder)
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 10, 14, 10)
        row.addWidget(_label("♫", "icon"))
        row.addSpacing(8)
        row.addLayout(text, stretch=1)
        self.set_files([])

    @property
    def path(self) -> Path | None:
        return self.paths[0] if self.paths else None

    def set_files(self, paths: list[Path], ready: bool = False, where: str = "") -> None:
        """Несколько файлов — «N files» и where (папка результатов); один — имя и папка файла."""
        self.paths, self.ready = list(paths), ready
        if not paths:
            self.name.setText("Output file")
            self.folder.setText("Not converted yet")
        elif len(paths) == 1:
            self.name.setText(paths[0].name)
            self.folder.setText(str(paths[0].parent))
        else:
            self.name.setText(f"{len(paths)} files")
            self.folder.setText(where)
        tip = "\n".join(map(str, paths)) + "\nClick to show in folder · drag into your DAW" if ready else ""
        self.setToolTip(tip)
        _repolish(self, "state", "ok" if ready else "off")
        for label in self.findChildren(QLabel):  # цвет подписей зависит от state карточки
            label.style().unpolish(label)
            label.style().polish(label)
        self.setCursor(Qt.CursorShape.PointingHandCursor if ready else Qt.CursorShape.ArrowCursor)

    def _available(self) -> bool:
        return self.ready and any(p.is_file() for p in self.paths)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._available():
            self._press_pos = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if (self._press_pos is not None and event.buttons() & Qt.MouseButton.LeftButton
                and (event.position().toPoint() - self._press_pos).manhattanLength()
                >= QApplication.startDragDistance()):
            self._press_pos = None  # это перетаскивание, а не клик
            mime = QMimeData()
            mime.setUrls([QUrl.fromLocalFile(str(p)) for p in self.paths if p.is_file()])
            drag = QDrag(self)
            drag.setMimeData(mime)
            drag.exec(Qt.DropAction.CopyAction)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        clicked = self._press_pos is not None and event.button() == Qt.MouseButton.LeftButton
        self._press_pos = None
        super().mouseReleaseEvent(event)
        if clicked and self.rect().contains(event.position().toPoint()):
            self._on_click()


class ReportDialog(QDialog):
    """Полный отчёт файла (или текст ошибки): только чтение, текст выделяется и копируется; Copy — весь текст."""

    def __init__(self, parent, title: str, text: str) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(640, 480)
        self.view = QPlainTextEdit(text)
        self.view.setReadOnly(True)
        self.view.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse
                                          | Qt.TextInteractionFlag.TextSelectableByKeyboard)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.copy_btn = buttons.addButton("Copy", QDialogButtonBox.ButtonRole.ActionRole)
        self.copy_btn.setToolTip("Copy the whole report")
        self.copy_btn.clicked.connect(self.copy)
        buttons.rejected.connect(self.reject)
        box = QVBoxLayout(self)
        box.addWidget(self.view, stretch=1)
        box.addWidget(buttons)

    def copy(self) -> None:
        QGuiApplication.clipboard().setText(self.view.toPlainText())



class ConvertPage(QWidget):
    """Вкладка Convert. Состояние: `sources` (исходные файлы), `outputs` (готовые результаты), `results` (итог по
    исходному файлу), `output_dir` (None — рядом с исходниками), `direction` (ui.ini). Сверху — полоса `strip`
    (профиль, карты направления, «⇄», папка результатов)."""

    def __init__(self, storage: Storage, settings) -> None:
        super().__init__()
        self.storage = storage
        self.settings = settings
        self.sources: list[Path] = []     # исходные файлы (один или несколько)
        self.outputs: list[Path] = []     # готовые результаты последней конвертации (только успешные)
        self.results: dict[Path, FileResult] = {}  # результаты последней конвертации по исходному файлу
        self.report_head = ""             # «Profile: … » — заголовок окна Details
        self.output_dir: Path | None = None  # None — результаты рядом с исходниками
        saved = self.settings.value(DIRECTION_KEY)
        self.direction = saved if saved in (FORWARD, REVERSE) else FORWARD
        self._build_ui()
        self._bind_shortcuts()
        self.reload_profiles()

    @property
    def source(self) -> Path | None:
        """Первый исходный файл (при одном файле — он же)."""
        return self.sources[0] if self.sources else None

    @property
    def output(self) -> Path | None:
        """Первый готовый результат."""
        return self.outputs[0] if self.outputs else None

    # --- построение UI ---

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(theme.PAGE_MARGIN, 0, theme.PAGE_MARGIN, 16)
        root.setSpacing(8)

        self.strip = ConvertStrip()
        self.profile_combo = self.strip.combo
        self.profile_combo.currentIndexChanged.connect(self._on_profile_changed)
        self.source_field, self.target_field = self.strip.source_field, self.strip.target_field
        self.direction_btn = self.strip.direction_btn
        self.direction_btn.setToolTip(tip(SWAP_TIP))
        self.direction_btn.clicked.connect(lambda _=False: self.toggle_direction())
        self._show_direction()
        self.output_btn = self.strip.output_btn
        self.output_menu = QMenu(self)
        self.output_next_action = self.output_menu.addAction(NEXT_TO_SOURCES, lambda: self.set_output_dir(None))
        self.output_next_action.setCheckable(True)
        self.output_choose_action = self.output_menu.addAction("Choose folder…", self.choose_output_folder)
        self.output_btn.setMenu(self.output_menu)
        root.addWidget(self.strip)
        root.addSpacing(theme.STRIP_GAP - root.spacing())

        self.drop = SourceZone(self.choose_file, self.remove_source, self.clear, self.show_details)
        root.addWidget(self.drop)
        root.addSpacing(6)
        self.out_card = OutputCard(self.open_folder)
        root.addWidget(self.out_card)
        root.addSpacing(6)

        self.convert_btn = QPushButton("Convert  →")
        self.convert_btn.setObjectName("primary")
        self.convert_btn.clicked.connect(self.convert)
        self.copy_btn = QPushButton()
        self.copy_btn.clicked.connect(self.copy_output)
        self._show_copy()
        actions = QHBoxLayout()
        actions.addWidget(self.convert_btn)
        actions.addStretch(1)
        actions.addWidget(self.copy_btn)
        root.addLayout(actions)
        root.addSpacing(6)

        root.addStretch(1)

        self.status = QLabel("Supports .mid and .midi files.")
        self.status.setObjectName("status")
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        self._show_output_dir()

    def _bind_shortcuts(self) -> None:
        # горячие клавиши экрана Convert на всё окно; на других вкладках выключены (там Enter/Ctrl+C нужны редакторам)
        self._convert_shortcuts = [
            QShortcut(QKeySequence(keys), self, activated=slot, context=Qt.ShortcutContext.WindowShortcut)
            for keys, slot in ((QKeySequence.StandardKey.Paste, self.paste_file),
                               (QKeySequence.StandardKey.Copy, self.copy_output),
                               (Qt.Key.Key_Return, self.convert),
                               (Qt.Key.Key_Enter, self.convert),
                               (Qt.Key.Key_Escape, self.clear))]

    def set_shortcuts_enabled(self, enabled: bool) -> None:
        for sc in self._convert_shortcuts:
            sc.setEnabled(enabled)

    def reload_profiles(self) -> None:
        """Список профилей из хранилища (вызывается и при изменениях на вкладке Profiles). Профилей нет — в комбо
        «NO PROFILES», конвертация недоступна, подсказки ведут на вкладку Profiles."""
        current = self.profile_combo.currentData()
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        try:
            entries, issues = self.storage.list_profiles()
        except OSError as e:
            entries, issues = [], []
            self.set_status(f"Cannot read the profiles folder: {e}", "error")
        for entry in entries:
            self.profile_combo.addItem(entry.name, entry.id)
            self.profile_combo.setItemData(self.profile_combo.count() - 1, str(entry.path),
                                           Qt.ItemDataRole.ToolTipRole)
        index = self.profile_combo.findData(current) if current is not None else -1
        self.profile_combo.setCurrentIndex(max(index, 0) if entries else -1)
        self.profile_combo.setPlaceholderText("" if entries else NO_PROFILES)
        self.profile_combo.setEnabled(bool(entries))
        self.profile_combo.blockSignals(False)
        self.convert_btn.setEnabled(bool(entries))
        self.convert_btn.setToolTip(tip("Convert (Enter)") if entries else tip(CREATE_PROFILE))
        self._on_profile_changed()
        if issues:
            names = ", ".join(i.path.name for i in issues)
            self.set_status(f"Skipped unreadable profiles ({len(issues)}): {names}", "error")

    def _on_profile_changed(self, *_) -> None:
        """Подсказка комбо — полное имя профиля; SOURCE / TARGET — карты профиля в текущем направлении."""
        profile_id = self.profile_combo.currentData()
        self.profile_combo.setToolTip(tip(self.profile_combo.currentText()) if profile_id is not None
                                      else tip(CREATE_PROFILE))
        source = target = NO_VALUE
        if profile_id is not None:
            try:
                profile = self.storage.load_profile(profile_id).oriented(self.direction)
                source, target = map_summary(profile.source_map), map_summary(profile.target_map)
            except (OSError, ValueError) as e:
                self.set_status(f"Cannot read the profile: {e}", "error")
        for field, value in ((self.source_field, source), (self.target_field, target)):
            field.set_texts(value)
            field.setToolTip(tip(value) if value != NO_VALUE else "")

    def _show_direction(self) -> None:
        self.direction_btn.setProperty("dir", self.direction)  # в ← — тот же вид; карты меняются местами в полях

    def toggle_direction(self) -> None:
        """«⇄»: прямое или обратное направление конвертации (запоминается в ui.ini)."""
        self.direction = FORWARD if self.direction == REVERSE else REVERSE
        self.settings.setValue(DIRECTION_KEY, self.direction)
        self._show_direction()
        self._on_profile_changed()

    def selected_profile(self) -> RemapProfile:
        profile_id = self.profile_combo.currentData()
        if profile_id is None:
            raise ValueError("no remap profile selected: create one in the Profiles tab")
        return self.storage.load_profile(profile_id)

    # --- файлы ---

    def set_sources(self, paths: list[Path]) -> None:
        """Заменить список исходных файлов (повторы убираются, порядок сохраняется); результат и отчёт сбрасываются.
        Drop, диалог и Ctrl+V добавляют к списку (add_sources), load() и «Clear all» — заменяют."""
        files: list[Path] = []
        for path in paths:
            path = Path(path).resolve()
            if path not in files:
                files.append(path)
        self.sources, self.outputs, self.results = files, [], {}
        self.drop.set_files(files)
        self._show_planned_outputs()
        self._show_copy()

    def _show_copy(self) -> None:
        """«Copy files», когда результатов несколько (готовых, а до конвертации — будущих)."""
        n = len(self.outputs) if self.outputs else len(self.sources)
        what = "Copy files" if n > 1 else "Copy file"
        self.copy_btn.setText(f"{what}  ⧉")
        self.copy_btn.setToolTip(f"{what} (Ctrl+C)")

    def _where(self) -> str:
        return str(self.output_dir) if self.output_dir is not None else "Next to the source files"

    def _show_output_dir(self) -> None:
        """Поле OUTPUT: папка результатов (или «рядом с исходниками»), подсказка — она же целиком."""
        folder = self.output_dir
        self.output_btn.setText(str(folder) if folder is not None else NEXT_TO_SOURCES)
        self.output_btn.setToolTip(tip(f"Results go to {folder}" if folder is not None
                                       else "Each result is written next to its source file"))
        self.output_next_action.setChecked(folder is None)

    def _show_planned_outputs(self) -> None:
        """Карточка результата до конвертации: куда лягут файлы."""
        planned = [output_path_for(s, self.output_dir) for s in self.sources]
        self.out_card.set_files(planned, ready=False, where=self._where())

    def load(self, path: str | Path) -> None:
        if not is_midi(path):
            self.set_status("Choose an existing .mid or .midi file.", "error")
            return
        self.set_sources([Path(path)])
        self.set_status("File loaded. Click Convert or press Enter.")

    def clear(self) -> None:
        self.set_sources([])
        self.set_status("Cleared.")

    def remove_source(self, path: Path) -> None:
        """Кнопка ✕ в списке файлов."""
        self.set_sources([p for p in self.sources if p != path])
        self.set_status(f"Removed {path.name}." if self.sources else "Cleared.")

    def choose_file(self) -> None:
        start = str(self.sources[0].parent) if self.sources else ""
        paths, _ = QFileDialog.getOpenFileNames(self, "Open MIDI files", start,
                                                "MIDI files (*.mid *.midi);;All files (*.*)")
        files = [Path(p) for p in paths if is_midi(p)]
        if files:
            self._accept_files(files)

    def _accept_files(self, files: list[Path]) -> None:
        """Drop, диалог, Ctrl+V: файлы добавляются к списку (уже добавленные не повторяются)."""
        before = len(self.sources)
        self.set_sources(self.sources + list(files))
        added = len(self.sources) - before
        if not added:
            self.set_status("Already in the list.")
        elif len(self.sources) == 1:
            self.set_status("File loaded. Click Convert or press Enter.")
        elif before:
            self.set_status(f"Added {_plural(added, 'file')} · {len(self.sources)} in the list. "
                            "Click Convert or press Enter.")
        else:
            self.set_status(f"{len(self.sources)} files loaded. Click Convert or press Enter.")

    def paste_file(self) -> None:
        files = midi_paths_from_mime(QGuiApplication.clipboard().mimeData())
        if files:
            self._accept_files(files)
        else:
            self.set_status("No MIDI file in the clipboard. Copy a file in Explorer and press Ctrl+V.", "error")

    def ask_output_folder(self, start: str) -> str:
        """Диалог выбора папки результатов (пустая строка — отмена). Тесты подменяют."""
        return QFileDialog.getExistingDirectory(self, "Output folder", start)

    def choose_output_folder(self) -> None:
        start = str(self.output_dir) if self.output_dir else (str(self.sources[0].parent) if self.sources else "")
        folder = self.ask_output_folder(start)
        if folder:
            self.set_output_dir(Path(folder))

    def set_output_dir(self, folder: Path | None) -> None:
        """Папка для всех результатов; None — каждый рядом со своим исходником."""
        self.output_dir = folder
        self.outputs, self.results = [], {}
        self.drop.set_files(self.sources)
        self._show_output_dir()
        self._show_planned_outputs()
        self._show_copy()
        self.set_status(f"Results go to {folder}" if folder is not None
                        else "Each result is written next to its source file.")

    def copy_output(self) -> None:
        files = [p for p in self.outputs if p.is_file()]
        if not files:
            self.set_status("Convert a file first.", "error")
            return
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(p)) for p in files])  # на Windows Qt кладёт CF_HDROP
        mime.setText("\n".join(map(str, files)))
        # Проводнику: вставка = копирование (DROPEFFECT_COPY), а не перемещение
        mime.setData('application/x-qt-windows-mime;value="Preferred DropEffect"', b"\x01\x00\x00\x00")
        QGuiApplication.clipboard().setMimeData(mime)
        what = "Output file" if len(files) == 1 else f"{len(files)} output files"
        self.set_status(f"{what} copied. Paste into a folder, or into a DAW that supports pasting files.", "ok")

    def open_folder(self) -> None:
        """Показать файл результата в Проводнике (клик по карточке результата)."""
        if self.output is None or not self.output.is_file():
            self.set_status("The output file is available after conversion.", "error")
            return
        if not self.reveal_in_explorer(self.output):
            self.set_status("Cannot open the output folder.", "error")

    def reveal_in_explorer(self, path: Path) -> bool:
        """Открыть папку с выделенным файлом (на Windows); в других ОС — просто папку. Тесты подменяют."""
        if sys.platform == "win32":
            try:
                subprocess.Popen(["explorer", f"/select,{path}"])
                return True
            except OSError:
                pass
        return QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))

    # --- DnD внутрь окна (события передаёт окно) ---

    def drag_enter(self, event) -> None:
        if event.source() is None and midi_paths_from_mime(event.mimeData()):  # свой результат не принимаем
            event.acceptProposedAction()
            self.drop.set_active(True)

    def drag_leave(self) -> None:
        self.drop.set_active(False)

    def drop_files(self, event) -> bool:
        """Drop на окно: True — файлы приняты (окно откроет вкладку Convert)."""
        self.drop.set_active(False)
        files = midi_paths_from_mime(event.mimeData())
        if files:
            event.acceptProposedAction()
            self._accept_files(files)
            return True
        self.set_status("Drop .mid or .midi files, or a folder with them.", "error")
        return False

    # --- конвертация ---

    def show_error(self, text: str) -> None:
        """Диалог ошибки (тесты подменяют)."""
        QMessageBox.critical(self, "REMAP: error", text)

    def convert(self) -> None:
        """Конвертация всех исходных файлов выбранным профилем и направлением; ошибка файла не останавливает остальные."""
        if self.profile_combo.currentData() is None:
            self.set_status("Create a remap profile in the Profiles tab first.", "error")
            return
        if not self.sources:
            self.set_status("Drop a MIDI file or click the area above to choose one.", "error")
            return
        try:
            profile = self.selected_profile()
        except Exception as exc:  # noqa: BLE001 — ошибка хранилища: окно не падает
            self.show_error(f"Conversion failed:\n\n{exc}")
            self.set_status("Conversion failed.", "error")
            return
        result = convert_batch(self.sources, profile, self.direction, self.output_dir)
        self.outputs = result.outputs
        self.results = {f.src: f for f in result.files}
        self.report_head = f"Profile: {profile.name}{' (reverse)' if self.direction == REVERSE else ''}\n\n"
        self.drop.set_files(self.sources, self.results)  # итог — в строке каждого файла
        self._show_copy()
        if result.outputs:
            self.out_card.set_files(result.outputs, ready=True, where=self._where())
        else:
            self._show_planned_outputs()
        if len(result.files) == 1:
            res = result.files[0]
            if res.ok:
                self.set_status(f"Converted: {res.dst.name}", "ok")
            else:
                self.set_status("Conversion failed.", "error")
            return
        self.set_status(batch_summary(len(result.succeeded), len(result.failed)),
                        "error" if result.failed else "ok")

    def details_dialog(self, path: Path) -> ReportDialog | None:
        """Окно Details файла path (полный отчёт или ошибка); None — результата нет."""
        res = self.results.get(path)
        if res is None:
            return None
        return ReportDialog(self, f"{path.name} — report", result_details(res, self.report_head))

    def show_details(self, path: Path) -> None:
        dlg = self.details_dialog(path)
        if dlg is not None:
            dlg.exec()

    def set_status(self, text: str, state: str = "") -> None:
        self.status.setText(text)
        _repolish(self.status, "state", state)

