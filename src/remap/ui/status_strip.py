"""Нижняя полоса под экранами (между нижними винтами) — одна на всех вкладках. Рисует сама (`ui/text.py`, токены theme).

Слева — статус (всегда по левому краю, длинный обрезается «…» справа); справа, прижатые к правому краю, — подсказки
Profiles «N matches · Apply · ✕» (`set_suggestion()`): статус обрезается перед ними, Apply не прыгает от длины статуса.
Статус может гаснуть (`fade_ms`): своё свойство `opacity`, подсказок оно не касается."""

from __future__ import annotations

from PySide6.QtCore import Property, QEasingCurve, QEvent, QPointF, QPropertyAnimation, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from . import text, theme
from .tips import tip

FONT = text.mono(12)
PAD_X = 8  # от краёв полосы
SUGGEST_GAP = 16  # статус — подсказки
PART_GAP = 8  # между частями «N matches · Apply · ✕»
STATE_COLORS = {"": theme.SILK_TEXT, "ok": theme.OK_TEXT, "warn": theme.WARN_TEXT, "error": theme.ERR_TEXT}
DOT, APPLY, DISMISS = "·", "Apply", "✕"


class StatusStrip(QWidget):
    """`set_status(text, state)` (state: "" / "ok" / "warn" / "error"), `text()`, `state()`; подсказки —
    `set_suggestion()` / `clear_suggestion()`, нажатия — `apply_clicked` / `dismiss_clicked`."""

    apply_clicked = Signal()
    dismiss_clicked = Signal()

    def __init__(self, parent: QWidget | None = None, *, fade_ms: int = 0, fade_duration: int = 0) -> None:
        super().__init__(parent)
        self.setFixedHeight(theme.BAND_H)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
        self._text, self._state, self._opacity = "", "", 1.0
        self._suggestion: str | None = None
        self._suggest_tip = self._apply_tip = self._dismiss_tip = ""
        self._apply_enabled = True
        self._hover: str | None = None
        self._fade = self._timer = None
        if fade_ms:
            self._fade = QPropertyAnimation(self, b"opacity", self)
            self._fade.setDuration(fade_duration)
            self._fade.setEndValue(0.0)
            self._fade.setEasingCurve(QEasingCurve.Type.Linear)
            self._timer = QTimer(self)
            self._timer.setSingleShot(True)
            self._timer.setInterval(fade_ms)
            self._timer.timeout.connect(self._fade.start)

    # --- статус ---

    def set_status(self, value: str, state: str = "") -> None:
        if state not in STATE_COLORS:
            raise ValueError(f"unknown status state {state!r}")
        self._text, self._state = value, state
        if self._fade is not None:
            self._fade.stop()
            self._opacity = 1.0
            if value:
                self._timer.start()
            else:
                self._timer.stop()
        self.update()

    def text(self) -> str:
        return self._text

    def state(self) -> str:
        return self._state

    def _get_opacity(self) -> float:
        return self._opacity

    def _set_opacity(self, value: float) -> None:
        self._opacity = value
        self.update()

    opacity = Property(float, _get_opacity, _set_opacity)

    @property
    def fade_timer(self) -> QTimer | None:
        return self._timer

    @property
    def fade_animation(self) -> QPropertyAnimation | None:
        return self._fade

    # --- подсказки ---

    def set_suggestion(self, label: str, label_tip: str = "", apply_enabled: bool = True, apply_tip: str = "",
                       dismiss_tip: str = "") -> None:
        self._suggestion, self._suggest_tip = label, label_tip
        self._apply_enabled, self._apply_tip, self._dismiss_tip = apply_enabled, apply_tip, dismiss_tip
        self.update()

    def clear_suggestion(self) -> None:
        self._suggestion = None
        self._hover = None
        self.unsetCursor()
        self.update()

    def suggestion(self) -> str | None:
        """Текст «N matches»; None — подсказок нет."""
        return self._suggestion

    def suggestion_tip(self) -> str:
        return self._suggest_tip

    def apply_enabled(self) -> bool:
        return self._apply_enabled

    # --- геометрия (логические px) ---

    def line_rect(self) -> QRectF:
        """Полоса строки: на линии центров нижних винтов."""
        return QRectF(PAD_X, theme.BAND_ITEM_TOP, self.width() - 2 * PAD_X, theme.BAND_ITEM_H)

    def parts(self) -> dict[str, QRectF]:
        """Части подсказок справа налево от правого края: label, dot, apply, dismiss; пусто — подсказок нет."""
        if self._suggestion is None:
            return {}
        line = self.line_rect()
        out: dict[str, QRectF] = {}
        x = line.right()
        for name, value in (("dismiss", DISMISS), ("apply", APPLY), ("dot", DOT), ("label", self._suggestion)):
            w = text.text_width(value, FONT)
            x -= w
            out[name] = QRectF(x, line.top(), w, line.height())
            x -= PART_GAP
        return out

    def status_rect(self) -> QRectF:
        """Место статуса: от левого поля до подсказок (с зазором) или до правого поля."""
        line = self.line_rect()
        parts = self.parts()
        if parts:
            line.setRight(max(line.left(), parts["label"].left() - SUGGEST_GAP))
        return line

    def shown_text(self) -> str:
        """Статус, как он нарисован (с «…», если не поместился)."""
        return text.elide(self._text, FONT, self.status_rect().width()) if self._text else ""

    def _hit(self, pos) -> str | None:
        for name, r in self.parts().items():
            zone = r.adjusted(-PART_GAP / 2, -theme.BAND_ITEM_TOP, PART_GAP / 2, self.height())
            if zone.contains(pos):
                return name
        return None

    # --- события ---

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        if self._text and self._opacity > 0:
            p.setOpacity(self._opacity)
            text.draw_text(p, self.status_rect(), self._text, FONT, STATE_COLORS[self._state],
                           elide_mode=Qt.TextElideMode.ElideRight)
            p.setOpacity(1.0)
        for name, r in self.parts().items():
            value = {"label": self._suggestion, "dot": DOT, "apply": APPLY, "dismiss": DISMISS}[name]
            text.draw_text(p, r, value, FONT, self._part_color(name))

    def _part_color(self, name: str) -> QColor:
        if name in ("label", "dot"):
            return QColor(theme.SILK_TEXT)
        if name == "apply" and not self._apply_enabled:
            return QColor(theme.SILK_FAINT)
        return QColor(theme.ACCENT_HOVER if self._hover == name else theme.ACCENT)

    def _clickable(self, name: str | None) -> bool:
        return name == "dismiss" or (name == "apply" and self._apply_enabled)

    def mouseMoveEvent(self, event) -> None:
        hit = self._hit(event.position())
        if hit != self._hover:
            self._hover = hit
            if self._clickable(hit):
                self.setCursor(Qt.CursorShape.PointingHandCursor)
            else:
                self.unsetCursor()
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        if self._hover is not None:
            self._hover = None
            self.unsetCursor()
            self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            hit = self._hit(event.position())
            if hit == "apply" and self._apply_enabled:
                self.apply_clicked.emit()
            elif hit == "dismiss":
                self.dismiss_clicked.emit()
        super().mouseReleaseEvent(event)

    def tooltip_at(self, pos) -> str:
        """Подсказка в точке: части подсказок — свои, обрезанный статус — целиком."""
        pos = QPointF(pos)
        hit = self._hit(pos)
        if hit in ("label", "dot"):
            return self._suggest_tip
        if hit == "apply":
            return self._apply_tip
        if hit == "dismiss":
            return self._dismiss_tip
        if self.status_rect().contains(pos) and self._text and self.shown_text() != self._text:
            return self._text
        return ""

    def event(self, event) -> bool:
        if event.type() == QEvent.Type.ToolTip:
            value = self.tooltip_at(QPointF(event.pos()))
            if value:
                QToolTip.showText(event.globalPos(), tip(value), self)
            else:
                QToolTip.hideText()
                event.ignore()
            return True
        return super().event(event)

