"""Страница Convert: исходные файлы (drop, диалог, Ctrl+V), профиль и направление, папка результатов, конвертация
пакетом, итог каждого файла и окно Details, результат наружу (перетаскивание в DAW, Ctrl+C).

Логики конвертации здесь нет — только вызов remap.core.convert_batch и показ отчёта; тексты — ui/convert_text.py.
Перетаскивание файлов принимает всё окно: оно передаёт события сюда (`drag_enter()`, `drag_leave()`, `drop()`).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QMimeData, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit,
    QMenu, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from ..core import FileResult, RemapProfile, convert_batch, output_path_for
from ..core.profile import FORWARD, REVERSE
from ..storage import Storage
from . import theme
from .convert_input import InputScreen
from .convert_output import OutputScreen, file_mime
from .convert_strip import ConvertStrip
from .convert_text import _plural, batch_summary, expand_midi_paths, is_midi, result_details
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
    def outputs(self) -> list[Path]:
        """Готовые результаты (успешные) в порядке исходных файлов."""
        return [r.dst for r in (self.results.get(s) for s in self.sources) if r is not None and r.ok]

    @property
    def output(self) -> Path | None:
        """Первый готовый результат."""
        outputs = self.outputs
        return outputs[0] if outputs else None

    # --- построение UI ---

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(theme.PAGE_MARGIN, 0, theme.PAGE_MARGIN, 0)
        root.setSpacing(0)

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
        root.addSpacing(theme.STRIP_GAP)

        self.input = InputScreen(self.remove_sources, self.show_details, self.choose_file, self.clear)
        self.output_screen = OutputScreen(self.copy_output, self.open_folder)
        self._active = self.input  # куда идёт Ctrl+A: экран, по которому щёлкнули последним
        self.input.activated = lambda: self._activate(self.input)
        self.output_screen.activated = lambda: self._activate(self.output_screen)
        # TEMP: until 5.5 — старая кнопка Convert на месте клавиши GO
        self.convert_btn = QPushButton("Convert  →")
        self.convert_btn.setObjectName("primary")
        self.convert_btn.setFixedHeight(theme.CONVERT_GO_SLOT_H)
        self.convert_btn.clicked.connect(self.convert)
        right = QWidget()
        right.setFixedWidth(theme.CONVERT_RIGHT_W)
        rbox = QVBoxLayout(right)
        rbox.setContentsMargins(0, 0, 0, theme.RECESS_EDGE_BOTTOM)  # низ клавиши — на одной линии с лицом INPUT
        rbox.setSpacing(0)
        rbox.addWidget(self.output_screen, stretch=1)
        rbox.addSpacing(theme.CONVERT_GO_GAP - theme.RECESS_EDGE_BOTTOM)
        rbox.addWidget(self.convert_btn)
        screens = QHBoxLayout()
        screens.setContentsMargins(0, 0, 0, 0)
        screens.setSpacing(theme.SCREEN_GAP)
        screens.addWidget(self.input)
        screens.addWidget(right)
        root.addLayout(screens, stretch=1)

        # TEMP: placement undecided (step 7) — статус в нижней полосе под экранами, как на Profiles
        self.status = QLabel("Supports .mid and .midi files.")
        self.status.setObjectName("status")
        self.status.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        band = QWidget()
        band.setFixedHeight(theme.BAND_H)
        band_box = QHBoxLayout(band)
        band_box.setContentsMargins(8, theme.BAND_ITEM_TOP, 8, theme.BAND_H - theme.BAND_ITEM_TOP - theme.BAND_ITEM_H)
        band_box.addWidget(self.status, stretch=1)
        root.addWidget(band)
        self._show_output_dir()

    def _bind_shortcuts(self) -> None:
        # горячие клавиши экрана Convert на всё окно; на других вкладках выключены (там Enter/Ctrl+C нужны редакторам)
        self._convert_shortcuts = [
            QShortcut(QKeySequence(keys), self, activated=slot, context=Qt.ShortcutContext.WindowShortcut)
            for keys, slot in ((QKeySequence.StandardKey.Paste, self.paste_file),
                               (QKeySequence.StandardKey.Copy, self.copy_output),
                               (Qt.Key.Key_Return, self.convert),
                               (Qt.Key.Key_Enter, self.convert),
                               (Qt.Key.Key_Escape, self.clear_selection),
                               (QKeySequence.StandardKey.Delete, self.remove_selected),
                               (QKeySequence.StandardKey.SelectAll, self.select_all))]

    def _activate(self, screen) -> None:
        self._active = screen

    def select_all(self) -> None:
        """Ctrl+A: всё в экране, по которому щёлкнули последним (по умолчанию — INPUT)."""
        self._active.select_all()

    def clear_selection(self) -> None:
        """Esc: снять выделение в обоих экранах (список не очищается — для этого CLEAR ALL)."""
        self.input.clear_selection()
        self.output_screen.clear_selection()

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

    def set_sources(self, paths: list[Path], keep_results: bool = False) -> None:
        """Заменить список исходных файлов (повторы убираются, порядок сохраняется). Результаты сбрасываются, а с
        `keep_results` (файлы убрали из списка) остаются у оставшихся файлов. Drop, диалог и Ctrl+V добавляют к списку,
        load() и «Clear all» — заменяют."""
        files: list[Path] = []
        for path in paths:
            path = Path(path).resolve()
            if path not in files:
                files.append(path)
        self.sources = files
        self.results = {p: r for p, r in self.results.items() if p in files} if keep_results else {}
        self._show_files()

    def _show_files(self) -> None:
        """Строки INPUT и карточки OUTPUT по `sources` и `results`: готовый результат — карточка, будущий (ещё не
        конвертировали) — приглушённая карточка, у несконвертированного файла карточки нет."""
        self.input.set_files(self.sources, self.results)
        cards = []
        for src in self.sources:
            res = self.results.get(src)
            if res is None:
                cards.append((output_path_for(src, self.output_dir), False))
            elif res.ok:
                cards.append((res.dst, True))
        self.output_screen.set_cards(cards)

    def _show_output_dir(self) -> None:
        """Поле OUTPUT: папка результатов (или «рядом с исходниками»), подсказка — она же целиком."""
        folder = self.output_dir
        self.output_btn.setText(str(folder) if folder is not None else NEXT_TO_SOURCES)
        self.output_btn.setToolTip(tip(f"Results go to {folder}" if folder is not None
                                       else "Each result is written next to its source file"))
        self.output_next_action.setChecked(folder is None)

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
        self.remove_sources([path])

    def remove_sources(self, paths: list[Path]) -> None:
        """«×» и Delete: убрать файлы из списка."""
        gone = set(paths)
        self.set_sources([p for p in self.sources if p not in gone], keep_results=True)
        if not self.sources:
            self.set_status("Cleared.")
        else:
            self.set_status(f"Removed {paths[0].name}." if len(paths) == 1 else f"Removed {_plural(len(paths), 'file')}.")

    def remove_selected(self) -> None:
        """Delete: убрать выделенные строки (ничего не выделено — ничего)."""
        selected = self.input.selection.selected
        if selected:
            self.remove_sources(selected)

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
        self.results = {}
        self._show_files()
        self._show_output_dir()
        self.set_status(f"Results go to {folder}" if folder is not None
                        else "Each result is written next to its source file.")

    def copy_output(self) -> None:
        """COPY и Ctrl+C: выделенные карточки OUTPUT, а если ничего не выделено — все готовые результаты."""
        files = self.output_screen.ready_targets()
        if not files:
            self.set_status("Convert a file first.", "error")
            return
        QGuiApplication.clipboard().setMimeData(file_mime(files))
        what = "Output file" if len(files) == 1 else f"{len(files)} output files"
        self.set_status(f"{what} copied. Paste into a folder, or into a DAW that supports pasting files.", "ok")

    def open_folder(self, path: Path | None = None) -> None:
        """Показать файл результата в Проводнике (двойной клик по карточке; без пути — первый результат)."""
        path = path if path is not None else self.output
        if path is None or not path.is_file():
            self.set_status("The output file is available after conversion.", "error")
            return
        if not self.reveal_in_explorer(path):
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
            self.input.set_active(True)

    def drag_leave(self) -> None:
        self.input.set_active(False)

    def drop_files(self, event) -> bool:
        """Drop на окно: True — файлы приняты (окно откроет вкладку Convert)."""
        self.input.set_active(False)
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
        self.results = {f.src: f for f in result.files}
        self.report_head = f"Profile: {profile.name}{' (reverse)' if self.direction == REVERSE else ''}\n\n"
        self._show_files()  # итог — в строке каждого файла, готовые результаты — карточками
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

