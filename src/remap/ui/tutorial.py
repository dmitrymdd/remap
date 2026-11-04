"""Обучение вкладки Profiles: затемнение корпуса с вырезами вокруг нужных мест, кольцо акцентом вокруг выреза и плашка
шага (счётчик, точки, заголовок, текст, SKIP / BACK / NEXT). Числа — `Profiles.dc.html` (токены `theme.TUT_*`).

Слой лежит поверх всего корпуса и забирает мышь, колесо и клавиатуру (горячие клавиши окна тоже — через
ShortcutOverride), поэтому под ним ничего не меняется, и вырезы пересчитываются только при смене размера. Вырез — лицо
виджета (место находит `resolve`) с полями из макета: вырез макета минус лицо, пополам. Плашка стоит со смещением от
выреза, как в макете; не помещается под вырезом — над ним; за край окна не выходит.
"""

from collections.abc import Callable
from dataclasses import dataclass
from math import ceil

from PySide6.QtCore import QEvent, QMargins, QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QAbstractButton, QApplication, QWidget

from . import text, theme
from .keys import TUT, Key, key_margins
from .metal import _Backdrop, inner_shadow, outer_shadow, paint_metal
from .theme import qcolor
from .tips import tip


@dataclass(frozen=True)
class Spot:
    """Вырез: `target` — что вырезать (имя места для `resolve`), поля вокруг лица по x и y, радиус."""

    target: str
    pad: tuple[float, float]
    radius: float


@dataclass(frozen=True)
class Step:
    """Шаг: заголовок, текст, вырезы; вырез `anchor` и левый верхний угол плашки в макете (x, y, ширина, высота; x, y)
    задают, где плашка стоит относительно выреза: по x — от левого края, по y — от низа, если в макете она под вырезом,
    иначе от верха."""

    title: str
    text: str
    spots: tuple[Spot, ...]
    mock_hole: tuple[int, int, int, int]
    mock_plate: tuple[int, int]
    anchor: int = 0

    def plate_at(self, hole: QRectF) -> QPointF:
        """Левый верхний угол лица плашки при вырезе `hole` (вырез `anchor`)."""
        x, y, _w, h = self.mock_hole
        px, py = self.mock_plate
        top = hole.bottom() + py - (y + h) if py >= y + h else hole.top() + py - y
        return QPointF(hole.left() + px - x, top)


STEPS = (
    Step("Profile", "A profile is one set of cables from one map to another. Pick it here, or start a new one "
         "with the dots key.",
         (Spot("profile", (6, 7), 9),), (46, 70, 184, 52), (120, 146)),
    Step("Source and target", "Pick the map your MIDI comes from and the map it should play on. The profile keeps "
         "both.",
         (Spot("maps", (7, 7), 9),), (318, 70, 536, 52), (436, 146)),
    Step("Connect notes", "Drag a note from Unassigned onto a target note to lay a cable. Several notes can go "
         "into one.",
         (Spot("pool", (6, 6), 12), Spot("target", (8, -2), 8)), (640, 152, 216, 612), (318, 270), anchor=1),
    Step("Remove cables", "Right-click a cable to remove it. Hold the right button and swipe across the scene to "
         "cut several at once. Ctrl+Z brings them back.",
         (Spot("cables", (4, 11), 8),), (521, 418, 130, 124), (420, 566)),
    Step("Match by number", "Connects every free note to the target note with the same number. A quick start when "
         "both maps share a layout.",
         (Spot("match", (4, 6), 6),), (150, 161, 126, 36), (304, 150)),
    Step("Both directions", "A profile works both ways. Swap shows the reverse direction, target to source. Edits "
         "there are saved too, and a cable you change there stays as you set it.",
         (Spot("swap", (8, 7), 9),), (556, 70, 60, 52), (436, 146)),
    Step("Save", "Ctrl+S. Source notes without a cable will ask whether to delete them or keep them on the same "
         "number.",
         (Spot("save", (6, 7), 9),), (227, 70, 50, 52), (120, 146)),
    Step("Run it again", "This guide is always one key away: press ? on the Profiles tab to see it again.",
         (Spot("help", (6, 6), 10),), (432, 8, 48, 48), (300, 76)),
)

Resolve = Callable[[str, bool], QRectF | None]  # место, шаг только что открыт → лицо в координатах слоя (или None)


def _rounded(rect: QRectF, radius: float) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    return path


def paint_dim(p: QPainter, rect: QRectF, holes: list[tuple[QRectF, float]], dpr: float) -> None:
    """Затемнение `rect` с вырезами и кольцо вокруг каждого: свечение 18 px, полоса 4 px, рамка 1.5 px акцентом
    (как у div кольца в макете, тени — только снаружи его рамки)."""
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    dim = QPainterPath()
    dim.addRect(rect)
    for hole, radius in holes:
        dim = dim.subtracted(_rounded(hole, radius))
    p.fillPath(dim, qcolor(theme.TUT_DIM))
    out, spread, width = theme.TUT_RING_OUT, theme.TUT_RING_SPREAD_W, theme.TUT_RING_WIDTH
    for hole, radius in holes:
        ring, r = hole.adjusted(-out, -out, out, out), radius + out
        outer_shadow(p, ring, r, dpr, **theme.TUT_RING_GLOW)
        band = _rounded(ring.adjusted(-spread, -spread, spread, spread), r + spread).subtracted(_rounded(ring, r))
        p.fillPath(band, qcolor(theme.TUT_RING_SPREAD))
        p.setPen(QPen(qcolor(theme.ACCENT), width))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(ring.adjusted(width / 2, width / 2, -width / 2, -width / 2), r - width / 2, r - width / 2)
    p.restore()


class _Link(QAbstractButton):
    """SKIP: подчёркнутая надпись без фона."""

    def __init__(self, label: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.setText(label)
        self._spec = text.label(theme.TUT_SKIP_FONT, spacing=theme.TUT_SKIP_SPACING)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def sizeHint(self) -> QSize:
        _ascent, descent = text.ascent_descent(self._spec)
        line = text.line_height(self._spec)
        below = max(0.0, theme.TUT_SKIP_UNDERLINE + 1 - descent)  # подчёркивание ниже строки
        return QSize(ceil(text.text_width(self.text(), self._spec)), ceil(line + below))

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        ascent, _descent = text.ascent_descent(self._spec)
        line = text.line_height(self._spec)
        width = text.text_width(self.text(), self._spec)
        text.draw_text(p, QRectF(0, 0, width, line), self.text(), self._spec, theme.TUT_SKIP,
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        p.fillRect(QRectF(0, ascent + theme.TUT_SKIP_UNDERLINE, width, 1), qcolor(theme.TUT_SKIP))


class TutorialPlate(QWidget):
    """Плашка шага: лицо 320 px шириной (высота — по тексту) и поля вокруг под тень `0 18px 44px`."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._backdrop = _Backdrop()
        self._counter = text.label(theme.TUT_COUNTER_FONT, spacing=theme.TUT_COUNTER_SPACING)
        self._title = text.label(theme.TUT_TITLE_FONT, spacing=theme.TUT_TITLE_SPACING)
        self._text = text.prose(theme.TUT_TEXT_FONT)
        self.back = Key("Back", spec=TUT, parent=self)
        self.next = Key("Next", spec=TUT, parent=self)
        self.next.lit = True
        self.skip = _Link("Skip", self)
        self.back.setToolTip(tip("Previous step"))
        self.next.setToolTip(tip("Next step (Enter)"))
        self.skip.setToolTip(tip("Close the tutorial (Esc)"))
        for key in (self.back, self.next):
            key.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # фокус остаётся у слоя: он и забирает клавиатуру
        self.index, self.count = 0, 1
        self.step: Step | None = None
        self.lines: list[str] = []
        self._face_h = 0.0

    @staticmethod
    def margins() -> QMargins:
        s = theme.TUT_PLATE_SHADOW
        return QMargins(s["blur"], s["blur"] - s["dy"], s["blur"], s["blur"] + s["dy"])

    def face_rect(self) -> QRectF:
        m = self.margins()
        return QRectF(m.left(), m.top(), theme.TUT_PLATE_W, self._face_h)

    def _content(self) -> tuple[float, float]:
        """Левый край и ширина содержимого (внутри рамки 1 px и полей)."""
        pad = theme.TUT_PLATE_PAD_X
        return self.margins().left() + 1 + pad, theme.TUT_PLATE_W - 2 - 2 * pad

    def _rows(self) -> tuple[float, float, float, float]:
        """y строк от верха виджета: счётчик, заголовок, текст, клавиши."""
        gap = theme.TUT_PLATE_GAP
        y_counter = self.margins().top() + 1 + theme.TUT_PLATE_PAD_TOP
        y_title = y_counter + text.line_height(self._counter) + gap
        y_text = y_title + text.line_height(self._title) + gap
        y_keys = y_text + len(self.lines) * self._line_step() + gap + theme.TUT_PLATE_ROW_TOP
        return y_counter, y_title, y_text, y_keys

    def _line_step(self) -> float:
        return theme.TUT_TEXT_FONT * theme.TUT_TEXT_LINE

    def set_step(self, index: int, count: int, step: Step) -> None:
        self.index, self.count, self.step = index, count, step
        self.lines = text.wrap(step.text, self._text, self._content()[1])
        last = index == count - 1
        self.next.setText("Done" if last else "Next")
        self.back.setVisible(index > 0)  # visibility: hidden — место остаётся
        self.skip.setVisible(not last)
        *_, y_keys = self._rows()
        self._face_h = y_keys + theme.KEY_TUT_HEIGHT + theme.TUT_PLATE_PAD_BOTTOM + 1 - self.margins().top()
        m = self.margins()
        self.resize(m.left() + theme.TUT_PLATE_W + m.right(), ceil(m.top() + self._face_h + m.bottom()))
        self._place_buttons(y_keys)
        self.update()

    def _place_buttons(self, y_keys: float) -> None:
        left, width = self._content()
        km, mid = key_margins(TUT), y_keys + theme.KEY_TUT_HEIGHT / 2
        x = left + width
        for key in (self.next, self.back):
            key.resize(key.sizeHint())
            x -= key.face_size().width()
            key.move(round(x) - km.left(), round(y_keys) - km.top())
            x -= theme.TUT_PLATE_KEY_GAP
        self.skip.resize(self.skip.sizeHint())
        line = text.line_height(self.skip._spec)
        self.skip.move(round(left), round(mid - line / 2))

    def _compose(self, p: QPainter, _rect: QRect, origin: QPoint) -> None:
        dpr, r = p.device().devicePixelRatioF(), theme.TUT_PLATE_RADIUS
        face = self.face_rect()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        outer_shadow(p, face, r, dpr, **theme.TUT_PLATE_SHADOW)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qcolor(theme.KEY_BORDER))
        p.drawRoundedRect(face, r, r)
        inner = face.adjusted(1, 1, -1, -1)
        g = QLinearGradient(0, inner.top(), 0, inner.bottom())
        for at, color in theme.TUT_PLATE_STOPS:
            g.setColorAt(at, qcolor(color))
        p.setBrush(QBrush(g))
        p.drawRoundedRect(inner, r - 1, r - 1)
        light, dark = theme.TUT_PLATE_INSET_LIGHT, theme.TUT_PLATE_INSET_DARK
        inner_shadow(p, inner, r - 1, dpr, 1, 0, light[3], rgb=light[:3])
        inner_shadow(p, inner, r - 1, dpr, -1, 0, dark[3], rgb=dark[:3])
        paint_metal(p, inner, r - 1, origin)

    def paintEvent(self, _event) -> None:
        if self.step is None:
            return
        p = QPainter(self)
        p.drawPixmap(0, 0, self._backdrop.get(self, self._compose))
        left, width = self._content()
        y_counter, y_title, y_text, _y_keys = self._rows()
        line = text.line_height(self._counter)
        text.draw_text(p, QRectF(left, y_counter, width, line), f"Step {self.index + 1} / {self.count}",
                       self._counter, theme.SILK_TEXT)
        self._paint_dots(p, left + width, y_counter + line / 2)
        text.draw_text(p, QRectF(left, y_title, width, text.line_height(self._title)), self.step.title, self._title,
                       theme.TUT_TITLE)
        step = self._line_step()
        for i, content in enumerate(self.lines):
            text.draw_text(p, QRectF(left, y_text + i * step, width, step), content, self._text, theme.TUT_TEXT)

    def _paint_dots(self, p: QPainter, right: float, mid: float) -> None:
        size, gap, dpr = theme.TUT_DOT, theme.TUT_DOT_GAP, self.devicePixelRatioF()
        x = right - self.count * size - (self.count - 1) * gap
        dot = QRectF(0, 0, size, size)
        for i in range(self.count):
            p.save()
            p.translate(round(x * dpr) / dpr, round((mid - size / 2) * dpr) / dpr)
            if i == self.index:
                outer_shadow(p, dot, 0, dpr, **theme.TUT_DOT_GLOW)
                p.fillRect(dot, qcolor(theme.ACCENT))
            elif i < self.index:
                p.fillRect(dot, qcolor(theme.TUT_DOT_PAST))
            else:
                p.fillRect(dot, qcolor(theme.TUT_DOT_FUTURE))
                inner_shadow(p, dot, 0, dpr, **theme.TUT_DOT_FUTURE_SHADOW)
            p.restore()
            x += size + gap


class TutorialOverlay(QWidget):
    """Слой обучения на весь `parent` (корпус окна). `start()` — показать с первого шага; закрывается SKIP, Esc и
    DONE (`finished`). Enter / → — дальше, ← — назад."""

    finished = Signal()

    def __init__(self, parent: QWidget, resolve: Resolve, steps: tuple[Step, ...] = STEPS) -> None:
        super().__init__(parent)
        self.steps, self._resolve = steps, resolve
        self.index = 0
        self.holes: list[tuple[QRectF, float]] = []
        self._layer: tuple[tuple, QPixmap] | None = None
        self._focus: QWidget | None = None
        self.plate = TutorialPlate(self)
        self.plate.back.clicked.connect(self.back)
        self.plate.next.clicked.connect(self.next)
        self.plate.skip.clicked.connect(self.finish)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        parent.installEventFilter(self)
        self.hide()

    # --- шаги ---
    def start(self, index: int = 0) -> None:
        self._focus = QApplication.focusWidget()
        self.setGeometry(self.parentWidget().rect())
        self.show()
        self.raise_()
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        self.go(index)

    def go(self, index: int) -> None:
        self.index = index
        self.plate.set_step(index, len(self.steps), self.steps[index])
        self.relayout(entering=True)

    def next(self) -> None:
        if self.index == len(self.steps) - 1:
            self.finish()
        else:
            self.go(self.index + 1)

    def back(self) -> None:
        if self.index > 0:
            self.go(self.index - 1)

    def finish(self) -> None:
        if not self.isVisible():
            return
        self.hide()
        if self._focus is not None:
            self._focus.setFocus(Qt.FocusReason.OtherFocusReason)
        self._focus = None
        self.finished.emit()

    # --- вырезы и плашка ---
    def relayout(self, entering: bool = False) -> None:
        """Вырезы по текущему положению мест и плашка рядом; `entering` — шаг только что открыт (место может
        прокрутить вид, чтобы стать видимым)."""
        if not self.isVisible():
            return
        step = self.steps[self.index]
        found: list[tuple[QRectF, float] | None] = []
        for spot in step.spots:
            face = self._resolve(spot.target, entering)
            dx, dy = spot.pad
            found.append(None if face is None or face.isEmpty() else (face.adjusted(-dx, -dy, dx, dy), spot.radius))
        self.holes = [h for h in found if h is not None]
        anchor = found[step.anchor] if step.anchor < len(found) else None
        anchor = anchor or (self.holes[0] if self.holes else None)
        self._place_plate(anchor[0] if anchor else None, step)
        self.update()

    def _place_plate(self, hole: QRectF | None, step: Step) -> None:
        plate, m = self.plate, self.plate.margins()
        face = plate.face_rect()
        w, h = face.width(), face.height()
        bounds = QRectF(self.rect()).adjusted(*[theme.TUT_PLATE_MARGIN] * 2, *[-theme.TUT_PLATE_MARGIN] * 2)
        if hole is None:
            x, y = bounds.center().x() - w / 2, bounds.center().y() - h / 2
        else:
            at = step.plate_at(hole)
            x, y = at.x(), at.y()
            if y + h > bounds.bottom() and y >= hole.bottom():  # под вырезом не помещается — над ним
                y = hole.top() - theme.TUT_PLATE_FLIP_GAP - h
        x = min(max(x, bounds.left()), bounds.right() - w)
        y = min(max(y, bounds.top()), bounds.bottom() - h)
        plate.move(round(x) - m.left(), round(y) - m.top())

    # --- рисование ---
    def _dim_pixmap(self) -> QPixmap:
        dpr = self.devicePixelRatioF()
        key = (self.width(), self.height(), dpr,
               tuple((r.x(), r.y(), r.width(), r.height(), radius) for r, radius in self.holes))
        if self._layer is None or self._layer[0] != key:
            pm = QPixmap(ceil(self.width() * dpr), ceil(self.height() * dpr))
            pm.setDevicePixelRatio(dpr)
            pm.fill(Qt.GlobalColor.transparent)
            p = QPainter(pm)
            paint_dim(p, QRectF(self.rect()), self.holes, dpr)
            p.end()
            self._layer = (key, pm)
        return self._layer[1]

    def paintEvent(self, _event) -> None:
        QPainter(self).drawPixmap(0, 0, self._dim_pixmap())

    # --- ввод: под слой ничего не проходит ---
    def eventFilter(self, watched, event) -> bool:
        if watched is self.parentWidget() and event.type() == QEvent.Type.Resize and self.isVisible():
            self.setGeometry(self.parentWidget().rect())
            QTimer.singleShot(0, self.relayout)  # layout корпуса раскладывается после события размера
        return False

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.relayout()

    def event(self, e) -> bool:
        if e.type() == QEvent.Type.ShortcutOverride:  # горячие клавиши окна (Ctrl+Z, Ctrl+S…) не срабатывают
            e.accept()
            return True
        return super().event(e)

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.finish()
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Right):
            self.next()
        elif key == Qt.Key.Key_Left:
            self.back()
        event.accept()

    def focusNextPrevChild(self, _next: bool) -> bool:
        return False  # Tab не уводит фокус под слой

    def mousePressEvent(self, event) -> None:
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:
        event.accept()

    def wheelEvent(self, event) -> None:
        event.accept()

    def contextMenuEvent(self, event) -> None:
        event.accept()


def profiles_resolver(window) -> Resolve:
    """Места шагов на вкладке Profiles окна `window` (MainWindow) в координатах его корпуса."""
    page, root = window.profiles_page, window.centralWidget()

    def face(w: QWidget) -> QRectF | None:
        if not w.isVisible():
            return None
        f = w.face_rect() if hasattr(w, "face_rect") else QRectF(w.rect())
        return f.translated(QPointF(w.mapTo(root, QPoint(0, 0))))

    def union(*widgets: QWidget) -> QRectF | None:
        rects = [r for r in map(face, widgets) if r is not None]
        if not rects:
            return None
        out = rects[0]
        for r in rects[1:]:
            out = out.united(r)
        return out

    def editor(rect: QRectF | None) -> QRectF | None:
        return None if rect is None else rect.translated(QPointF(page.cables.mapTo(root, QPoint(0, 0))))

    places: dict[str, Callable[[bool], QRectF | None]] = {
        "profile": lambda _e: union(page.combo, page.strip.dots_btn),
        "maps": lambda _e: union(page.from_btn, page.to_btn),
        "pool": lambda _e: face(page.cables.pool_screen),
        "target": lambda _e: editor(page.cables.target_column_rect()),
        # кабелей нет — вся сцена
        "cables": lambda entering: (editor(page.cables.busiest_bundle(reveal=entering))
                                    or face(page.cables.scene_screen)),
        "match": lambda _e: face(page.match_btn),
        "swap": lambda _e: face(page.direction_btn),
        "save": lambda _e: face(page.save_btn),
        "help": lambda _e: face(window.help_btn),
    }
    return lambda target, entering: places[target](entering)
