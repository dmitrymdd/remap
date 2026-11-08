"""Экран INPUT вкладки Convert: заголовок (INPUT · N FILES · CLEAR ALL), строки файлов, зона drop последним элементом
списка (прокручивается вместе с ним) и строка итогов. Всё рисуется само (`plates`, `text`, `icons`); выделение — как в
Проводнике (`ui/selection.py`). Логику (добавить, убрать, Details) подключает страница колбэками.

Строка файла 60 px (числа — из макета): 1-я строка — значок, имя, «×»; 2-я — LED, итог файла (`result_line()`; до
конвертации — «Ready»), DETAILS. Цвет строки и LED — `file_state()`: ok / warn / error; смысл — в подсказке у LED и итога.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QScrollArea, QSizePolicy, QToolTip, QVBoxLayout, QWidget,
)

from ..core import FileResult, OutputConflict
from . import text, theme
from .convert_text import (
    ERROR, OK, READY, READY_LINE, WARN, conflict_line, file_state, result_line, state_tip, totals_parts,
)
from .field import ScreenButton
from .glass import Screen
from .icons import ICONS, draw_icon
from .metal import RecessedBlock, outer_shadow
from .plates import paint_plate
from .selection import Selection
from .theme import qcolor
from .tips import tip

LEFT_MID = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
TEXT_COLORS = {READY: theme.SCREEN_TEXT_3, OK: theme.OK_TEXT, WARN: theme.WARN_TEXT, ERROR: theme.ERR_TEXT}
LED_COLORS = {OK: theme.OK_LED, WARN: theme.WARN_LED, ERROR: theme.ERR_LED}
PLATE_STATES = {WARN: "warn", ERROR: "error"}  # ok и ready — обычная плашка (в макете у ok те же фон и рамка)
REMOVE_TIP, REMOVE_SELECTED_TIP = "Remove from the list", "Remove the selected files (Delete)"
DETAILS_TIP = "Show the full report"
CLEAR_TIP = "Remove all files (Esc)"
DROP_TIP = "Click or drop to add files · Ctrl+V · Esc to clear"
DROP_TITLE, DROP_SUB = "DROP .MID FILES OR A FOLDER", "click to browse · Ctrl+V to paste"

_LEDS: dict[tuple[str, float], QPixmap] = {}
LED_PAD = theme.LED_GLOW_BLUR + 2  # поле растра LED под свечение


def _button_spec() -> text.TextSpec:
    return text.mono(theme.FILE_BTN_FONT, QFont.Weight.Normal, theme.FILE_BTN_SPACING, theme.WDTH_BUTTON)


def _led_pixmap(color: str | None, dpr: float) -> QPixmap:
    """LED со свечением и тёмным кольцом (`None` — погашен: без свечения), растр с полями `LED_PAD`."""
    key = (color or "", dpr)
    pm = _LEDS.get(key)
    if pm is None:
        size = theme.LED_SIZE + 2 * LED_PAD
        pm = QPixmap(round(size * dpr), round(size * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = theme.LED_SIZE / 2
        led = QRectF(LED_PAD, LED_PAD, theme.LED_SIZE, theme.LED_SIZE)
        if color is not None:
            rgb = QColor(color).getRgb()[:3]
            outer_shadow(p, led, r, dpr, 0, theme.LED_GLOW_BLUR, 1.0, rgb)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qcolor(theme.LED_RING))
        p.drawEllipse(led.adjusted(-1, -1, 1, 1))
        p.setBrush(qcolor(color or theme.LED_OFF))
        p.drawEllipse(led)
        p.end()
        _LEDS[key] = pm
    return pm


def _paint_frame(p: QPainter, rect: QRectF, radius: float, hot: bool) -> None:
    """Рамка кнопки строки (× и DETAILS): 1 px, без заливки; наведение — светлее (в макете не задано)."""
    p.setPen(QPen(qcolor(theme.CHECK_HOVER_BORDER if hot else theme.SCREEN_BTN_BORDER), 1))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), radius - 0.5, radius - 0.5)


class FileRow(QWidget):
    """Строка файла. `state` — ready / ok / warn / error; `line` — текст второй строки; `selected` — ставит список.
    `conflict` — имя результата занято (до конвертации: строка — предупреждением, CONVERT файл пропустит)."""

    def __init__(self, path: Path, res: FileResult | None, owner: InputScreen,
                 conflict: OutputConflict | None = None) -> None:
        super().__init__()
        self.path, self.res, self._owner = path, res, owner
        self.conflict = conflict if res is None else None  # готовый результат важнее
        self.state = file_state(res, self.conflict)
        self.line = (result_line(res) if res is not None else conflict_line(self.conflict) if self.conflict is not None
                     else READY_LINE)
        self.selected = False
        self._hover: str | None = None
        self._pressed: str | None = None
        self.setFixedHeight(theme.FILE_ROW_H)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)

    # --- геометрия (координаты строки) ---
    def _line_tops(self) -> tuple[float, float]:
        first, second = theme.FILE_REMOVE_SIZE, theme.FILE_DETAILS_H
        top = (theme.FILE_ROW_H - first - theme.FILE_ROW_LINE_GAP - second) / 2
        return top, top + first + theme.FILE_ROW_LINE_GAP

    def remove_rect(self) -> QRectF:
        size = theme.FILE_REMOVE_SIZE
        return QRectF(self.width() - 1 - theme.FILE_ROW_PAD_R - size, self._line_tops()[0], size, size)

    def details_rect(self) -> QRectF | None:
        if self.res is None:
            return None
        w = text.text_width("DETAILS", _button_spec()) + 2 * (theme.FILE_DETAILS_PAD + 1)
        w = float(round(w))
        return QRectF(self.width() - 1 - theme.FILE_ROW_PAD_R - w, self._line_tops()[1], w, theme.FILE_DETAILS_H)

    def text_x(self) -> float:
        return 1 + theme.FILE_ROW_PAD_L + ICONS["file"].w + theme.FILE_ROW_GAP_X

    def led_rect(self) -> QRectF:
        x = 1 + theme.FILE_ROW_PAD_L + theme.FILE_ROW_INDENT - 14  # margin-left −14 макета
        cy = self._line_tops()[1] + theme.FILE_DETAILS_H / 2
        return QRectF(x, cy - theme.LED_SIZE / 2, theme.LED_SIZE, theme.LED_SIZE)

    def line_rect(self) -> QRectF:
        details = self.details_rect()
        right = (details.left() - theme.FILE_ROW_GAP_X) if details is not None \
            else self.width() - 1 - theme.FILE_ROW_PAD_R
        return QRectF(self.text_x(), self._line_tops()[1], right - self.text_x(), theme.FILE_DETAILS_H)

    def _hit(self, pos: QPointF) -> str | None:
        details = self.details_rect()
        if self.remove_rect().contains(pos):
            return "remove"
        if details is not None and details.contains(pos):
            return "details"
        return None

    # --- рисование ---
    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        paint_plate(p, QRectF(0, 0, self.width(), self.height()),
                    "selected" if self.selected else PLATE_STATES.get(self.state, "normal"))
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        top1 = self._line_tops()[0]
        icon = ICONS["file"]
        x0 = 1 + theme.FILE_ROW_PAD_L
        draw_icon(p, "file", QRectF(x0, top1 + (theme.FILE_REMOVE_SIZE - icon.h) / 2, icon.w, icon.h))
        remove = self.remove_rect()
        name = QRectF(self.text_x(), top1, remove.left() - theme.FILE_ROW_GAP_X - self.text_x(), theme.FILE_REMOVE_SIZE)
        text.draw_text(p, name, self.path.name, text.mono(theme.FILE_NAME_FONT), theme.SCREEN_TEXT, LEFT_MID,
                       Qt.TextElideMode.ElideRight)
        _paint_frame(p, remove, theme.FILE_REMOVE_RADIUS, self._hover == "remove")
        x = ICONS["x"]
        draw_icon(p, "x", QRectF(remove.center().x() - x.w / 2, remove.center().y() - x.h / 2, x.w, x.h),
                  theme.SCREEN_TEXT_2)
        led = self.led_rect()
        p.drawPixmap(QPointF(led.left() - LED_PAD, led.top() - LED_PAD),
                     _led_pixmap(LED_COLORS.get(self.state), self.devicePixelRatioF()))
        text.draw_text(p, self.line_rect(), self.line, text.mono(theme.FILE_RESULT_FONT), TEXT_COLORS[self.state],
                       LEFT_MID, Qt.TextElideMode.ElideRight)
        details = self.details_rect()
        if details is not None:
            _paint_frame(p, details, theme.FILE_DETAILS_RADIUS, self._hover == "details")
            text.draw_text(p, details, "DETAILS", _button_spec(), theme.SCREEN_BTN_TEXT, Qt.AlignmentFlag.AlignCenter)

    # --- мышь и подсказки ---
    def _set_hover(self, hit: str | None) -> None:
        if hit != self._hover:
            self._hover = hit
            self.setCursor(Qt.CursorShape.PointingHandCursor if hit else Qt.CursorShape.ArrowCursor)
            self.update()

    def mouseMoveEvent(self, event) -> None:
        self._set_hover(self._hit(event.position()))
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        self._set_hover(None)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        self._pressed = self._hit(event.position())
        if self._pressed is None:
            self._owner.row_pressed(self.path, event.modifiers())
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        pressed, self._pressed = self._pressed, None
        if pressed is not None and event.button() == Qt.MouseButton.LeftButton \
                and self._hit(event.position()) == pressed:
            if pressed == "remove":
                self._owner.remove_clicked(self.path)
            else:
                self._owner.details_clicked(self.path)
        event.accept()

    def tooltip_at(self, pos: QPointF) -> str:
        hit = self._hit(pos)
        if hit == "remove":
            many = self.selected and len(self._owner.selection) > 1
            return tip(REMOVE_SELECTED_TIP if many else REMOVE_TIP)
        if hit == "details":
            return tip(DETAILS_TIP)
        meaning = state_tip(self.res, self.conflict)
        line = self.line_rect()
        zone = QRectF(self.led_rect().left() - 2, line.top(), line.right() - self.led_rect().left() + 2, line.height())
        if meaning is not None and zone.contains(pos):
            title, body = meaning
            return tip(body, title)
        return tip(str(self.path))

    def event(self, e) -> bool:
        if e.type() == QEvent.Type.ToolTip:
            QToolTip.showText(e.globalPos(), self.tooltip_at(QPointF(e.pos())), self)
            return True
        return super().event(e)


class DropZone(QWidget):
    """Зона drop: пунктирная рамка, значок и две строки по центру; клик — диалог выбора файлов. Это `<button>` макета:
    текст — `WDTH_BUTTON`. `active` — над окном тащат файлы (рамка акцентом; в макете не задано)."""

    def __init__(self, on_click: Callable[[], None]) -> None:
        super().__init__()
        self._on_click = on_click
        self.active = False
        self.setMinimumHeight(theme.DROP_MIN_H)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setToolTip(tip(DROP_TIP))
        self._title = text.mono(theme.DROP_TITLE_FONT, QFont.Weight.DemiBold, theme.DROP_TITLE_SPACING,
                                theme.WDTH_BUTTON)
        self._sub = text.mono(theme.DROP_SUB_FONT, wdth=theme.WDTH_BUTTON)

    def set_active(self, active: bool) -> None:
        self.active = active
        self.update()

    def event(self, e) -> bool:
        if e.type() in (QEvent.Type.HoverEnter, QEvent.Type.HoverLeave):
            self.update()
        return super().event(e)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        box = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        border = theme.ACCENT if self.active else theme.CHECK_HOVER_BORDER if self.underMouse() else theme.DROP_BORDER
        pen = QPen(qcolor(border), 1)
        pen.setStyle(Qt.PenStyle.CustomDashLine)
        pen.setDashPattern(list(theme.DROP_DASH))
        p.setPen(pen)
        p.setBrush(qcolor(theme.DROP_BG))
        r = theme.DROP_RADIUS - 0.5
        p.drawRoundedRect(box, r, r)
        icon = ICONS["drop-target"]
        title_h, sub_h = text.line_height(self._title), text.line_height(self._sub)
        block = icon.h + theme.DROP_GAP + title_h + theme.DROP_GAP + sub_h
        y = round((self.height() - block) / 2)
        draw_icon(p, "drop-target", QRectF((self.width() - icon.w) / 2, y, icon.w, icon.h), theme.SCREEN_TEXT_2)
        y += icon.h + theme.DROP_GAP
        text.draw_text(p, QRectF(0, y, self.width(), title_h), DROP_TITLE, self._title, theme.SCREEN_BTN_TEXT,
                       Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        y += title_h + theme.DROP_GAP
        text.draw_text(p, QRectF(0, y, self.width(), sub_h), DROP_SUB, self._sub, theme.SCREEN_TEXT_3,
                       Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self._on_click()


class ScreenHeader(QWidget):
    """Заголовок экрана Convert: название акцентом, счётчик («N FILES»), кнопка справа, линия под ними (высота 30
    вместе с линией)."""

    def __init__(self, title: str, button: ScreenButton) -> None:
        super().__init__()
        self.title, self.count = title, ""
        self._title = text.mono(theme.POOL_HEAD_FONT, QFont.Weight.DemiBold, theme.POOL_HEAD_SPACING)
        self._count = text.mono(theme.INPUT_COUNT_FONT)
        self.setFixedHeight(theme.INPUT_HEAD_H)
        box = QHBoxLayout(self)
        box.setContentsMargins(0, 0, 0, theme.INPUT_HEAD_BELOW + 1)
        box.addStretch(1)
        box.addWidget(button, 0, Qt.AlignmentFlag.AlignVCenter)

    def set_count(self, count: str) -> None:
        self.count = count
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        body = QRectF(0, 0, self.width(), self.height() - theme.INPUT_HEAD_BELOW - 1)
        text.draw_text(p, body, self.title, self._title, theme.ACCENT)
        if self.count:
            x = text.text_width(self.title, self._title) + theme.FILE_ROW_GAP_X
            text.draw_text(p, body.adjusted(x, 0, 0, 0), self.count, self._count, theme.SCREEN_TEXT_3)
        p.fillRect(QRectF(0, self.height() - 1, self.width(), 1), qcolor(theme.SCREEN_DIVIDER))


class ScreenFooter(QWidget):
    """Нижняя строка экрана (итоги INPUT, «DRAG INTO YOUR DAW» у OUTPUT): линия сверху, части по нижнему краю, каждая
    своим цветом, зазор 14."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[tuple[str, str]] = []
        self._spec = text.mono(theme.TOTALS_FONT, spacing=theme.TOTALS_SPACING)
        self.setFixedHeight(theme.TOTALS_H)

    def set_parts(self, parts: list[tuple[str, str]]) -> None:
        self.parts = parts
        self.update()

    @property
    def text(self) -> str:
        return " · ".join(t for t, _ in self.parts)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.fillRect(QRectF(0, 0, self.width(), 1), qcolor(theme.SCREEN_DIVIDER))
        x = 0.0
        for label, state in self.parts:
            w = text.text_width(label, self._spec)
            text.draw_text(p, QRectF(x, 1, w + 1, self.height() - 1), label, self._spec,
                           theme.SCREEN_TEXT_3 if state == OK else TEXT_COLORS[state],
                           Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
            x += w + theme.TOTALS_GAP


class ListBody(QWidget):
    """Содержимое прокрутки экрана: строки (и зона drop); клик по пустому месту снимает выделение (`owner.empty_pressed`)."""

    def __init__(self, owner) -> None:
        super().__init__()
        self._owner = owner
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(0, 0, 0, 0)
        self.box.setSpacing(theme.INPUT_GAP)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._owner.empty_pressed(event.modifiers())
        super().mousePressEvent(event)


def screen_list(body: QWidget) -> QScrollArea:
    """Прокрутка содержимого экрана: без рамки и штатных полос (полосу экрана подключает `Screen.attach`)."""
    area = QScrollArea()
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setWidgetResizable(True)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    area.setWidget(body)
    return area


class InputScreen(RecessedBlock):
    """Блок с экраном INPUT. Колбэки: `on_remove(paths)`, `on_details(path)`, `on_browse()`, `on_clear()`;
    `selection` — выделенные строки (ключи — пути)."""

    def __init__(self, on_remove: Callable[[list[Path]], None], on_details: Callable[[Path], None],
                 on_browse: Callable[[], None], on_clear: Callable[[], None]) -> None:
        super().__init__()
        self._on_remove, self._on_details = on_remove, on_details
        self.selection = Selection()
        self.activated: Callable[[], None] | None = None  # клик по экрану: страница запоминает, куда идёт Ctrl+A
        self.setMinimumWidth(theme.CONVERT_INPUT_W)  # ширину задаёт ряд экранов (SplitRow)
        self.screen = Screen()
        self.body.addWidget(self.screen)
        self.clear_btn = ScreenButton("Clear all")
        self.clear_btn.setToolTip(tip(CLEAR_TIP))
        self.clear_btn.clicked.connect(lambda _=False: on_clear())
        self.header = ScreenHeader("INPUT", self.clear_btn)
        self._body = ListBody(self)
        self.list = screen_list(self._body)
        self.drop_zone = DropZone(on_browse)
        self.totals = ScreenFooter()
        self.screen.body.setSpacing(theme.INPUT_GAP)
        self.screen.body.addWidget(self.header)
        self.screen.body.addWidget(self.list, stretch=1)
        self.screen.body.addWidget(self.totals)
        self.bar = self.screen.attach(self.list, top=theme.SCREEN_PAD + theme.INPUT_HEAD_H + theme.INPUT_GAP)
        self._rows: list[FileRow] = []
        self.set_files([], {})

    def rows(self) -> list[FileRow]:
        return list(self._rows)

    def row(self, path: Path) -> FileRow | None:
        return next((r for r in self._rows if r.path == path), None)

    def set_files(self, paths: list[Path], results: dict[Path, FileResult],
                  conflicts: dict[Path, OutputConflict] | None = None) -> None:
        """Строки по файлам (у каждого — его результат, если уже конвертировали, или конфликт имени результата);
        выделение остаётся у оставшихся."""
        conflicts = conflicts or {}
        box = self._body.box
        while box.count():
            item = box.takeAt(0)
            if item.widget() is not None and item.widget() is not self.drop_zone:
                item.widget().hide()
                item.widget().deleteLater()
        self._rows = [FileRow(path, results.get(path), self, conflicts.get(path)) for path in paths]
        for row in self._rows:
            box.addWidget(row)
        box.addSpacing(theme.DROP_TOP_EXTRA)
        box.addWidget(self.drop_zone, stretch=1)
        self.selection.set_items(paths)
        self.refresh_selection()
        n = len(paths)
        self.header.set_count(f"{n} FILE" + ("" if n == 1 else "S") if n else "")
        self.clear_btn.setEnabled(bool(n))
        shown = [results[p] for p in paths if p in results]
        self.totals.setVisible(bool(shown))
        self.totals.set_parts(totals_parts(shown) if shown else [])
        bottom = theme.SCREEN_PAD + (theme.TOTALS_H + theme.INPUT_GAP if shown else 0)
        self.screen.set_track(self.bar, theme.SCREEN_PAD + theme.INPUT_HEAD_H + theme.INPUT_GAP, bottom)

    def refresh_selection(self) -> None:
        for row in self._rows:
            selected = self.selection.is_selected(row.path)
            if selected != row.selected:
                row.selected = selected
                row.update()

    def set_active(self, active: bool) -> None:
        self.drop_zone.set_active(active)

    # --- события строк ---
    def _activate(self) -> None:
        if self.activated is not None:
            self.activated()

    def row_pressed(self, path: Path, modifiers) -> None:
        self._activate()
        self.selection.press(path, ctrl=bool(modifiers & Qt.KeyboardModifier.ControlModifier),
                             shift=bool(modifiers & Qt.KeyboardModifier.ShiftModifier))
        self.refresh_selection()

    def empty_pressed(self, modifiers) -> None:
        self._activate()
        if not modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier):
            self.selection.clear()
            self.refresh_selection()

    def select_all(self) -> None:
        self.selection.select_all()
        self.refresh_selection()

    def clear_selection(self) -> None:
        self.selection.clear()
        self.refresh_selection()

    def remove_clicked(self, path: Path) -> None:
        """«×»: у выделенной строки — все выделенные, у невыделенной — только она."""
        self._on_remove(self.selection.targets(path))

    def details_clicked(self, path: Path) -> None:
        self._on_details(path)
