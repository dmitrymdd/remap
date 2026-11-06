"""Шапка окна: кнопка-логотип (открывает About), разделитель и шелкография «DRUM MIDI / NOTE REMAPPER»."""

import logging

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QPainter, QPen, QPixmap
from PySide6.QtWidgets import QAbstractButton, QSizePolicy, QWidget

from . import text, theme
from .theme import qcolor
from .tips import tip

log = logging.getLogger(__name__)

LINES = ("DRUM MIDI", "NOTE REMAPPER")

_pixmaps: dict[tuple[str, int], QPixmap | None] = {}


def logo_scale(dpr: float) -> int:
    """Какой пререндер брать: ближайший не меньше DPR (1.25 → 2×, уменьшается плавно), не больше самого крупного."""
    for n in theme.LOGO_SCALES:
        if dpr <= n:
            return n
    return theme.LOGO_SCALES[-1]


def logo_pixmap(kind: str, dpr: float) -> QPixmap | None:
    """Картинка логотипа (`kind`: "logo", "logo_hover", "logo_glow") под `dpr`; загружается один раз, нет файла —
    одно предупреждение и None."""
    key = (kind, logo_scale(dpr))
    if key not in _pixmaps:
        pm = QPixmap(str(theme.logo_png(*key)))
        if pm.isNull():
            log.warning("logo not loaded: %s@%sx", *key)
            _pixmaps[key] = None
        else:
            _pixmaps[key] = pm
    return _pixmaps[key]


class LogoButton(QAbstractButton):
    """Логотип 144×22 — кнопка About. Виджет шире лица на `LOGO_GLOW_PAD` с каждой стороны: туда ложится свечение
    при наведении; нажимается и подсвечивается только лицо. `on` — подсветка без наведения (About открыт)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.hovered = False
        self._on = False
        self._focus_visible = False
        self.setToolTip(tip("About"))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setAccessibleName("About REMAP")

    @property
    def on(self) -> bool:
        return self._on

    @on.setter
    def on(self, value: bool) -> None:
        self._on = value
        self.update()

    @property
    def lit(self) -> bool:
        """Рисуется подсвеченным (свечение + яркость)."""
        return self.hovered or self._on

    def face_rect(self) -> QRectF:
        pad = theme.LOGO_GLOW_PAD
        return QRectF(pad, pad, *theme.LOGO_SIZE)

    def sizeHint(self) -> QSize:
        w, h = theme.LOGO_SIZE
        return QSize(w + 2 * theme.LOGO_GLOW_PAD, h + 2 * theme.LOGO_GLOW_PAD)

    def hitButton(self, pos) -> bool:
        return self.face_rect().contains(QPointF(pos))

    def _set_hovered(self, value: bool) -> None:
        if value != self.hovered:
            self.hovered = value
            self.setCursor(Qt.CursorShape.PointingHandCursor if value else Qt.CursorShape.ArrowCursor)
            self.update()

    def mouseMoveEvent(self, event) -> None:
        self._set_hovered(self.hitButton(event.position().toPoint()))
        super().mouseMoveEvent(event)

    def enterEvent(self, event) -> None:
        self._set_hovered(self.hitButton(event.position().toPoint()))
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._set_hovered(False)
        super().leaveEvent(event)

    def event(self, e) -> bool:
        if e.type() == e.Type.ToolTip and not self.hitButton(e.pos()):
            e.ignore()
            return True  # подсказка — только над лицом, как у кнопки макета
        return super().event(e)

    def focusInEvent(self, event) -> None:
        self._focus_visible = event.reason() in (Qt.FocusReason.TabFocusReason, Qt.FocusReason.BacktabFocusReason,
                                                 Qt.FocusReason.ShortcutFocusReason)
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:
        self._focus_visible = False
        super().focusOutEvent(event)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        dpr, face = self.devicePixelRatioF(), self.face_rect()
        if self.lit:
            glow = logo_pixmap("logo_glow", dpr)
            if glow is not None:
                p.drawPixmap(QRectF(self.rect()), glow, QRectF(glow.rect()))
        logo = logo_pixmap("logo_hover" if self.lit else "logo", dpr)
        if logo is not None:
            p.drawPixmap(face, logo, QRectF(logo.rect()))
        if self._focus_visible and self.hasFocus():
            off, r = theme.LOGO_FOCUS_OFFSET, theme.LOGO_FOCUS_RADIUS
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setPen(QPen(qcolor(theme.KEY_FOCUS_RING), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            ring = face.adjusted(-off - 0.5, -off - 0.5, off + 0.5, off + 0.5)
            p.drawRoundedRect(ring, r + off, r + off)


class BrandBlock(QWidget):
    """Логотип 144×22 (`logo`, кнопка About), вертикальный разделитель 1×28 с тенью справа и две строки шелкографии.
    Блок начинается на `LOGO_GLOW_PAD` левее лица логотипа: свечение не обрезается краем блока."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._spec = text.label(theme.BRAND_FONT, spacing=theme.BRAND_SPACING)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.logo = LogoButton(self)
        self.logo.resize(self.logo.sizeHint())
        self.logo.move(0, round(theme.HEADER_H / 2 - theme.LOGO_SIZE[1] / 2) - theme.LOGO_GLOW_PAD)

    def _silk_width(self) -> float:
        return max(text.text_width(line, self._spec) for line in LINES)

    def sizeHint(self) -> QSize:
        w, _h = theme.LOGO_SIZE
        return QSize(int(theme.LOGO_GLOW_PAD + w + 2 * theme.HEADER_GAP + 1 + self._silk_width() + 1),
                     theme.HEADER_H - theme.RECESS_EDGE_TOP)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        gap, mid = theme.HEADER_GAP, theme.HEADER_H / 2
        x = theme.LOGO_GLOW_PAD + theme.LOGO_SIZE[0] + gap
        h = theme.BRAND_DIVIDER_H
        p.fillRect(QRectF(x + 1, mid - h / 2, 1, h), qcolor(theme.BRAND_DIVIDER_SHADOW))  # тень 1px вправо
        p.fillRect(QRectF(x, mid - h / 2, 1, h), qcolor(theme.BRAND_DIVIDER))
        x += 1 + gap
        line = text.line_height(self._spec)
        step = theme.BRAND_FONT * theme.BRAND_LINE
        top = mid - step
        for i, content in enumerate(LINES):
            rect = QRectF(x, top + i * step + (step - line) / 2, self._silk_width() + 2, line)
            text.draw_text(p, rect, content, self._spec, theme.SILK_TEXT)
