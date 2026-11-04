"""Экран OUTPUT вкладки Convert: заголовок (OUTPUT · COPY), карточки `_remapped.mid` и подвал «DRAG INTO YOUR DAW».

Карточка 54 px рисуется сама (числа — из макета): значок DIN, имя файла (с «…»), папка. Готовый результат можно
перетащить в DAW или папку и показать в Проводнике двойным кликом; будущий (до конвертации) — приглушён и только
показывает, куда ляжет файл. Выделение — как в Проводнике (`ui/selection.py`), те же правила, что у INPUT: перетаскивание
выделенной карточки берёт все выделенные, невыделенной — только её.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QEvent, QMimeData, QPoint, QRectF, Qt, QUrl
from PySide6.QtGui import QDrag, QPainter
from PySide6.QtWidgets import QApplication, QSizePolicy, QToolTip, QWidget

from . import text, theme
from .convert_input import OK, ListBody, ScreenFooter, ScreenHeader, screen_list
from .field import ScreenButton
from .glass import Screen
from .icons import ICONS, draw_icon
from .metal import RecessedBlock
from .plates import paint_plate
from .selection import Selection
from .tips import tip

FOOTER = "DRAG INTO YOUR DAW"
READY_TIP = "Drag into your DAW or a folder · double-click to show in folder"
PLANNED_TIP = "Not converted yet"
COPY_ALL_TIP, COPY_SELECTED_TIP = "Copy all files (Ctrl+C)", "Copy the selected files (Ctrl+C)"
LEFT_MID = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter


def file_mime(files: list[Path]) -> QMimeData:
    """Файлы для буфера обмена и перетаскивания: URL (на Windows Qt кладёт CF_HDROP), пути текстом и «вставка =
    копирование» для Проводника (DROPEFFECT_COPY, а не перемещение)."""
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(p)) for p in files])
    mime.setText("\n".join(map(str, files)))
    mime.setData('application/x-qt-windows-mime;value="Preferred DropEffect"', b"\x01\x00\x00\x00")
    return mime


class OutputCard(QWidget):
    """Карточка результата. `ready` — файл уже записан (иначе — будущий, приглушён); `selected` ставит экран."""

    def __init__(self, path: Path, ready: bool, owner: OutputScreen) -> None:
        super().__init__()
        self.path, self.ready, self._owner = path, ready, owner
        self.selected = False
        self._press: QPoint | None = None
        self._deferred = False  # нажали на выделенную без модификаторов: «только эта» — при отпускании без перетаскивания
        self.setFixedHeight(theme.OUT_CARD_H)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        if ready:
            self.setCursor(Qt.CursorShape.OpenHandCursor)

    def text_x(self) -> float:
        return 1 + theme.OUT_CARD_PAD + ICONS["output-din"].w + theme.OUT_CARD_GAP_X

    def text_room(self) -> float:
        return self.width() - 1 - theme.OUT_CARD_PAD - self.text_x()

    def folder_label(self) -> str:
        """Папка с «…» посередине: видны и диск, и сама папка файла."""
        return text.elide(str(self.path.parent), text.mono(theme.OUT_FOLDER_FONT), self.text_room(),
                          Qt.TextElideMode.ElideMiddle)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        if not self.ready:
            p.setOpacity(theme.OUT_PLANNED_OPACITY)
        paint_plate(p, QRectF(0, 0, self.width(), self.height()), "selected" if self.selected else "normal")
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        icon = ICONS["output-din"]
        draw_icon(p, "output-din", QRectF(1 + theme.OUT_CARD_PAD, (self.height() - icon.h) / 2, icon.w, icon.h))
        name, folder = text.mono(theme.OUT_NAME_FONT), text.mono(theme.OUT_FOLDER_FONT)
        name_h, folder_h = text.line_height(name), text.line_height(folder)
        y = (self.height() - name_h - theme.OUT_CARD_LINE_GAP - folder_h) / 2
        x, room = self.text_x(), self.text_room()
        text.draw_text(p, QRectF(x, y, room, name_h), self.path.name, name, theme.SCREEN_TEXT, LEFT_MID,
                       Qt.TextElideMode.ElideRight)
        text.draw_text(p, QRectF(x, y + name_h + theme.OUT_CARD_LINE_GAP, room + 1, folder_h), self.folder_label(),
                       folder, theme.SCREEN_TEXT_3, LEFT_MID)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._press = event.position().toPoint()
            self._deferred = self._owner.card_pressed(self.path, event.modifiers())
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        if (self._press is not None and event.buttons() & Qt.MouseButton.LeftButton
                and (event.position().toPoint() - self._press).manhattanLength() >= QApplication.startDragDistance()):
            self._press, self._deferred = None, False  # перетаскивание, а не клик
            self._owner.drag_from(self)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._deferred and event.button() == Qt.MouseButton.LeftButton:
            self._owner.card_clicked(self.path)
        self._press, self._deferred = None, False
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._owner.card_double_clicked(self.path)
        event.accept()

    def event(self, e) -> bool:
        if e.type() == QEvent.Type.ToolTip:
            QToolTip.showText(e.globalPos(), tip(READY_TIP if self.ready else PLANNED_TIP, str(self.path)), self)
            return True
        return super().event(e)


class OutputScreen(RecessedBlock):
    """Блок с экраном OUTPUT. Колбэки: `on_copy()` (COPY), `on_reveal(path)` (двойной клик). `selection` — ключи —
    пути результатов; `activated` — клик по экрану (страница запоминает, куда идёт Ctrl+A)."""

    def __init__(self, on_copy: Callable[[], None], on_reveal: Callable[[Path], None]) -> None:
        super().__init__()
        self._on_reveal = on_reveal
        self.selection = Selection()
        self.activated: Callable[[], None] | None = None
        self.screen = Screen()
        self.body.addWidget(self.screen)
        self.copy_btn = ScreenButton("Copy")
        self.copy_btn.clicked.connect(lambda _=False: on_copy())
        self.header = ScreenHeader("OUTPUT", self.copy_btn)
        self._body = ListBody(self)
        self.list = screen_list(self._body)
        self.footer = ScreenFooter()
        self.footer.set_parts([(FOOTER, OK)])
        self.screen.body.setSpacing(theme.INPUT_GAP)
        self.screen.body.addWidget(self.header)
        self.screen.body.addWidget(self.list, stretch=1)
        self.screen.body.addWidget(self.footer)
        top = theme.SCREEN_PAD + theme.INPUT_HEAD_H + theme.INPUT_GAP
        self.bar = self.screen.attach(self.list, top=top, bottom=theme.SCREEN_PAD + theme.TOTALS_H + theme.INPUT_GAP)
        self._cards: list[OutputCard] = []
        self.set_cards([])

    def cards(self) -> list[OutputCard]:
        return list(self._cards)

    def card(self, path: Path) -> OutputCard | None:
        return next((c for c in self._cards if c.path == path), None)

    def set_cards(self, cards: list[tuple[Path, bool]]) -> None:
        """Карточки (путь результата, готов ли он); выделение остаётся у оставшихся."""
        box = self._body.box
        while box.count():
            item = box.takeAt(0)
            if item.widget() is not None:
                item.widget().hide()
                item.widget().deleteLater()
        self._cards = [OutputCard(path, ready, self) for path, ready in cards]
        for card in self._cards:
            box.addWidget(card)
        box.addStretch(1)
        self.selection.set_items([c.path for c in self._cards])
        self.refresh_selection()
        self.copy_btn.setEnabled(any(c.ready for c in self._cards))

    def ready_targets(self, card: OutputCard | None = None) -> list[Path]:
        """Готовые файлы, на которые действует жест: от карточки — по правилу × (выделенная — все выделенные);
        без карточки (COPY, Ctrl+C) — выделенные, а если ничего не выделено — все."""
        if card is not None:
            keys = self.selection.targets(card.path)
        else:
            keys = self.selection.selected or [c.path for c in self._cards]
        ready = {c.path for c in self._cards if c.ready}
        return [k for k in keys if k in ready and k.is_file()]

    def refresh_selection(self) -> None:
        for card in self._cards:
            selected = self.selection.is_selected(card.path)
            if selected != card.selected:
                card.selected = selected
                card.update()
        self.copy_btn.setToolTip(tip(COPY_SELECTED_TIP if len(self.selection) else COPY_ALL_TIP))

    def _activate(self) -> None:
        if self.activated is not None:
            self.activated()

    def card_pressed(self, path: Path, modifiers) -> bool:
        """Нажатие на выделенную карточку без модификаторов выделение не меняет (так тащат несколько карточек) и
        возвращает True: «только эта» — при отпускании без перетаскивания (`card_clicked`), как в Проводнике."""
        self._activate()
        plain = not modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
        if plain and self.selection.is_selected(path):
            return True
        self.selection.press(path, ctrl=bool(modifiers & Qt.KeyboardModifier.ControlModifier),
                             shift=bool(modifiers & Qt.KeyboardModifier.ShiftModifier))
        self.refresh_selection()
        return False

    def card_clicked(self, path: Path) -> None:
        self.selection.click(path)
        self.refresh_selection()

    def empty_pressed(self, modifiers) -> None:
        self._activate()
        if not modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier):
            self.clear_selection()

    def select_all(self) -> None:
        self.selection.select_all()
        self.refresh_selection()

    def clear_selection(self) -> None:
        self.selection.clear()
        self.refresh_selection()

    def card_double_clicked(self, path: Path) -> None:
        card = self.card(path)
        if card is not None and card.ready:
            self._on_reveal(path)

    def drag_from(self, card: OutputCard) -> None:
        files = self.ready_targets(card)
        if not files:
            return
        drag = QDrag(card)
        drag.setMimeData(file_mime(files))
        drag.exec(Qt.DropAction.CopyAction)
