"""About: слой поверх корпуса окна — затемнение и плашка по центру (числа — `Convert.dc.html`, `showAbout`; токены
`theme.ABOUT_*`). Плашка: «ABOUT» и клавиша CLOSE, утопленный блок с экраном: имя и версия, описание, автор, ссылки
(GitHub и e-mail открываются в браузере / почте, Discord — копируется в буфер), две строки лицензии.

Слой, как обучение, забирает мышь, колесо и клавиатуру (горячие клавиши окна тоже — через ShortcutOverride).
Закрывается CLOSE и Esc; щелчок по затемнению ничего не делает (в макете он не задан).
"""

from dataclasses import dataclass
from math import ceil

from PySide6.QtCore import QEvent, QMargins, QPoint, QRect, QRectF, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QBrush, QDesktopServices, QFont, QLinearGradient, QPainter
from PySide6.QtWidgets import QAbstractButton, QApplication, QVBoxLayout, QWidget

from .. import __version__
from . import text, theme
from .glass import Screen
from .icons import draw_icon
from .keys import CLOSE, Key, key_margins
from .metal import Backdrop, RecessedBlock, inner_shadow, outer_shadow, paint_metal
from .plates import paint_plate
from .theme import qcolor
from .tips import tip

DESCRIPTION = ("Converts drum MIDI parts between note layouts — Guitar Pro, General MIDI, Superior Drummer, "
               "EZdrummer and your own maps.")
HANDLE, AUTHOR = "dmitry.mdd", "Dmitry Mysyakov"
LICENSE = ("© 2026 Dmitry Mysyakov · GPL-3.0 · no warranty",
           "Uses Qt / PySide6 (LGPL-3.0) · fonts: SIL OFL 1.1")
COPIED = "Copied"


@dataclass(frozen=True)
class Link:
    """Строка-ссылка: значок, подпись, значение; `url` — открыть, иначе (`copy`) — скопировать значение."""

    icon: str
    label: str
    value: str
    url: str = ""
    tip: str = ""


LINKS = (
    Link("code", "GitHub", "github.com/dmitrymdd", "https://github.com/dmitrymdd", "Open in the browser"),
    Link("chat", "Discord", HANDLE, "", "Copy the Discord name"),
    Link("mail", "Email", "dmitrymdd@gmail.com", "mailto:dmitrymdd@gmail.com", "Write an email"),
)


def screen_width() -> int:
    """Ширина экрана с рамкой: плашка минус рамка, поля и поля блока."""
    return theme.ABOUT_W - 2 - 2 * theme.ABOUT_PAD_X - 2 * theme.ABOUT_RECESS_PAD


def content_width() -> int:
    return screen_width() - 2 - 2 * theme.ABOUT_SCREEN_PAD_X


# --- строки экрана ---

class _Title(QWidget):
    """«REMAP» и версия справа, по одной базовой линии."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._name = text.mono(theme.ABOUT_NAME_FONT, QFont.Weight.DemiBold, theme.ABOUT_NAME_SPACING)
        self._version = text.mono(theme.ABOUT_VERSION_FONT)
        self.version = f"v{__version__}"
        self.setFixedHeight(ceil(text.line_height(self._name)))

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        top = Qt.AlignmentFlag.AlignTop
        text.draw_text(p, QRectF(self.rect()), "REMAP", self._name, theme.SCREEN_TEXT, Qt.AlignmentFlag.AlignLeft | top)
        shift = text.ascent_descent(self._name)[0] - text.ascent_descent(self._version)[0]
        text.draw_text(p, QRectF(self.rect()).adjusted(0, shift, 0, 0), self.version, self._version, theme.ACCENT,
                       Qt.AlignmentFlag.AlignRight | top)


class _Lines(QWidget):
    """Абзац строк с шагом `line` (line-height), перенос по ширине содержимого экрана."""

    def __init__(self, paragraphs: tuple[str, ...], spec: text.TextSpec, line: float, color: str,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._spec, self._step, self._color = spec, spec.px * line, color
        self.lines = [ln for para in paragraphs for ln in text.wrap(para, spec, content_width())]
        self.setFixedHeight(ceil(len(self.lines) * self._step))

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        for i, content in enumerate(self.lines):
            text.draw_text(p, QRectF(0, i * self._step, self.width(), self._step), content, self._spec, self._color)


class _Author(QWidget):
    """Линия-разделитель и «dmitry.mdd · Dmitry Mysyakov»."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._spec = text.mono(theme.ABOUT_AUTHOR_FONT)
        self.setFixedHeight(1 + theme.ABOUT_AUTHOR_PAD + ceil(text.line_height(self._spec)))

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.fillRect(QRectF(0, 0, self.width(), 1), qcolor(theme.SCREEN_DIVIDER))
        x, y, h = 0.0, 1 + theme.ABOUT_AUTHOR_PAD, text.line_height(self._spec)
        for content, color in ((HANDLE, theme.SCREEN_TEXT), ("·", theme.ABOUT_AUTHOR_DOT),
                               (AUTHOR, theme.ABOUT_AUTHOR_NAME)):
            w = text.text_width(content, self._spec)
            text.draw_text(p, QRectF(x, y, w + 1, h), content, self._spec, color)
            x += w + theme.ABOUT_AUTHOR_GAP


class LinkRow(QAbstractButton):
    """Строка-ссылка: плашка (наведение — состояние hover плашек), значок, подпись, значение с «…», стрелка.
    `flash(text)` на время подменяет значение (Discord: «COPIED»)."""

    def __init__(self, link: Link, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.link = link
        self.shown = link.value
        self._label = text.mono(theme.ABOUT_LINK_LABEL_FONT, spacing=theme.ABOUT_LINK_LABEL_SPACING)
        self._value = text.mono(theme.ABOUT_LINK_VALUE_FONT)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(lambda: self.flash(None))
        self.setFixedHeight(theme.ABOUT_LINK_H)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # клавиатуру держит слой
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setToolTip(tip(link.tip))

    def flash(self, message: str | None) -> None:
        self.shown = self.link.value if message is None else message
        if message is not None:
            self._timer.start(theme.ABOUT_COPIED_MS)
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        paint_plate(p, QRectF(self.rect()), "hover" if self.underMouse() else "normal")
        icon_w, label_w, arrow_w = theme.ABOUT_LINK_COLS
        gap, h = theme.ABOUT_LINK_COL_GAP, self.height()
        x = 1 + theme.ABOUT_LINK_PAD
        draw_icon(p, self.link.icon, QRectF(x + (icon_w - 14) / 2, (h - 14) / 2, 14, 14), theme.SCREEN_TEXT_2)
        x += icon_w + gap
        text.draw_text(p, QRectF(x, 0, label_w, h), self.link.label.upper(), self._label, theme.SCREEN_TEXT_3)
        x += label_w + gap
        right = self.width() - 1 - theme.ABOUT_LINK_PAD - arrow_w
        text.draw_text(p, QRectF(x, 0, right - gap - x, h), self.shown, self._value, theme.SCREEN_TEXT,
                       elide_mode=Qt.TextElideMode.ElideRight)
        draw_icon(p, "external-link", QRectF(right + (arrow_w - 10) / 2, (h - 10) / 2, 10, 10), theme.SCREEN_TEXT_2)


# --- плашка ---

class AboutPlate(QWidget):
    """Плашка About: лицо `ABOUT_W` (высота — по содержимому) и поля под тень `0 24px 60px`."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._backdrop = Backdrop()
        self._title = text.label(theme.ABOUT_TITLE_FONT, spacing=theme.ABOUT_TITLE_SPACING)
        self.close_key = Key("", "x", spec=CLOSE, icon_stroke=1.5, parent=self)
        self.close_key.setToolTip(tip("Close (Esc)"))
        self.close_key.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.close_key.resize(self.close_key.sizeHint())

        self.block = RecessedBlock(self, margin=theme.ABOUT_RECESS_PAD)
        self.screen = Screen(glow_ry=theme.ABOUT_GLOW_RY, grid=False)
        self.block.body.addWidget(self.screen)
        body = self.screen.body
        body.setContentsMargins(1 + theme.ABOUT_SCREEN_PAD_X, 1 + theme.ABOUT_SCREEN_PAD_TOP,
                                1 + theme.ABOUT_SCREEN_PAD_X, 1 + theme.ABOUT_SCREEN_PAD_BOTTOM)
        body.setSpacing(theme.ABOUT_ROW_GAP)
        self.title = _Title()
        self.description = _Lines((DESCRIPTION,), text.mono(theme.ABOUT_DESC_FONT), theme.ABOUT_DESC_LINE,
                                  theme.ABOUT_DESC)
        self.author = _Author()
        links = QWidget()
        column = QVBoxLayout(links)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(theme.ABOUT_LINK_GAP)
        self.links = [LinkRow(link) for link in LINKS]
        for row in self.links:
            column.addWidget(row)
        self.license = _Lines(LICENSE, text.mono(theme.ABOUT_LICENSE_FONT), theme.ABOUT_LICENSE_LINE,
                              theme.SCREEN_TEXT_3)
        for w in (self.title, self.description, self.author, links, self.license):
            body.addWidget(w)
        self._layout()

    @staticmethod
    def margins() -> QMargins:
        s = theme.ABOUT_SHADOW
        return QMargins(s["blur"], s["blur"] - s["dy"], s["blur"], s["blur"] + s["dy"])

    def face_rect(self) -> QRectF:
        m = self.margins()
        return QRectF(m.left(), m.top(), theme.ABOUT_W, self.height() - m.top() - m.bottom())

    def _layout(self) -> None:
        m = self.margins()
        left, top = m.left() + 1 + theme.ABOUT_PAD_X, m.top() + 1 + theme.ABOUT_PAD_TOP
        inner_w = theme.ABOUT_W - 2 - 2 * theme.ABOUT_PAD_X
        km, face = key_margins(CLOSE), self.close_key.face_size()
        self.close_key.move(left + inner_w - face.width() - km.left(),
                            round(top + (theme.ABOUT_HEAD_H - face.height()) / 2) - km.top())
        block_h = self.block.sizeHint().height()
        self.block.setGeometry(left, top + theme.ABOUT_HEAD_H + theme.ABOUT_HEAD_GAP - theme.RECESS_EDGE_TOP,
                               inner_w, block_h)
        face_bottom = self.block.geometry().bottom() + 1 - theme.RECESS_EDGE_BOTTOM
        self.resize(m.left() + theme.ABOUT_W + m.right(), face_bottom + theme.ABOUT_PAD_BOTTOM + 1 + m.bottom())

    def _compose(self, p: QPainter, _rect: QRect, origin: QPoint) -> None:
        dpr, r = p.device().devicePixelRatioF(), theme.ABOUT_RADIUS
        face = self.face_rect()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        outer_shadow(p, face, r, dpr, **theme.ABOUT_SHADOW)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qcolor(theme.KEY_BORDER))
        p.drawRoundedRect(face, r, r)
        inner = face.adjusted(1, 1, -1, -1)
        g = QLinearGradient(0, inner.top(), 0, inner.bottom())
        for at, color in theme.ABOUT_STOPS:
            g.setColorAt(at, qcolor(color))
        p.setBrush(QBrush(g))
        p.drawRoundedRect(inner, r - 1, r - 1)
        light, dark = theme.ABOUT_INSET_LIGHT, theme.ABOUT_INSET_DARK
        inner_shadow(p, inner, r - 1, dpr, 1, 0, light[3], rgb=light[:3])
        inner_shadow(p, inner, r - 1, dpr, -1, 0, dark[3], rgb=dark[:3])
        paint_metal(p, inner, r - 1, origin)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.drawPixmap(0, 0, self._backdrop.get(self, self._compose))
        top = self.margins().top() + 1 + theme.ABOUT_PAD_TOP
        left = self.screen.mapTo(self, QPoint(0, 0)).x()  # по левой границе стекла, не по полю плашки
        text.draw_text(p, QRectF(left, top, 200, theme.ABOUT_HEAD_H), "About", self._title, theme.ABOUT_TITLE)


class AboutOverlay(QWidget):
    """Слой About на весь `parent` (корпус окна): `open()` показывает, CLOSE и Esc закрывают (`closed`)."""

    closed = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._focus: QWidget | None = None
        self.plate = AboutPlate(self)
        self.plate.close_key.clicked.connect(self.close_about)
        for row in self.plate.links:
            row.clicked.connect(lambda _=False, r=row: self.activate(r))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        parent.installEventFilter(self)
        self.hide()

    def open(self) -> None:
        if self.isVisible():
            return
        self._focus = QApplication.focusWidget()
        self.setGeometry(self.parentWidget().rect())
        self.show()
        self.raise_()
        self.setFocus(Qt.FocusReason.OtherFocusReason)

    def close_about(self) -> None:
        if not self.isVisible():
            return
        self.hide()
        if self._focus is not None:
            self._focus.setFocus(Qt.FocusReason.OtherFocusReason)
        self._focus = None
        self.closed.emit()

    def activate(self, row: LinkRow) -> None:
        """Ссылка: адрес — открыть, иначе — скопировать значение и на время показать «COPIED»."""
        if row.link.url:
            QDesktopServices.openUrl(QUrl(row.link.url))
        else:
            QApplication.clipboard().setText(row.link.value)
            row.flash(COPIED.upper())

    def _place_plate(self) -> None:
        plate, m = self.plate, self.plate.margins()
        face = plate.face_rect()
        x = (self.width() - face.width()) / 2
        y = max(0.0, (self.height() - face.height()) / 2 + theme.ABOUT_OFFSET_Y)
        plate.move(round(x) - m.left(), round(y) - m.top())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._place_plate()

    def paintEvent(self, _event) -> None:
        QPainter(self).fillRect(self.rect(), qcolor(theme.ABOUT_DIM))

    # --- ввод: под слой ничего не проходит ---
    def eventFilter(self, watched, event) -> bool:
        if watched is self.parentWidget() and event.type() == QEvent.Type.Resize and self.isVisible():
            self.setGeometry(self.parentWidget().rect())
        return False

    def event(self, e) -> bool:
        if e.type() == QEvent.Type.ShortcutOverride:  # горячие клавиши окна не срабатывают
            e.accept()
            return True
        return super().event(e)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close_about()
        event.accept()

    def focusNextPrevChild(self, _next: bool) -> bool:
        return False

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
