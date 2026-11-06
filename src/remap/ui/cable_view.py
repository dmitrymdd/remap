"""Вид профиля «кабелями»: показ и правка перетаскиванием кабелей.

Два экрана рядом (`Screen` в утопленных блоках 260 и 564 px, ширины и колонки сцены 200 / 122 / 200 фиксированы):
пул — отдельная QGraphicsView со своей прокруткой (неподключённые ноты по группам инструментов, зачёркнутые — delete —
в своей группе); сцена — вторая QGraphicsView: колонка «from» (подключённые ноты), промежуток для кабелей и колонка
«to» (карта цели) — одна общая прокрутка, кабели внутри сцены. Над пулом, внутри экрана, — заголовок «Unassigned»
(не группа, не сворачивается) и кнопка «Match by number». Views стоят в экранах с запасом PAD вокруг содержимого, чтобы
плашки лежали на сетке макета (поля экрана 14 + рамка). Поверх всего —
прозрачный для мыши слой CableOverlay: на нём рисуется кабель-превью от исходных строк к курсору через границу пула
и сцены. Пустая сцена (ни заголовков, ни строк) — подсказка по центру (EMPTY_HINT).

Направление (set_direction): вид строится по profile.oriented(direction) (поле shown) одним и тем же кодом —
поток всегда слева направо: [пул] [подключённые ноты] кабели [карта цели]. В REVERSE это ноты целевой карты слева
и артикуляции исходной карты справа. Отличаются только названия карт в подсказках (цвет один: направления цветом
не различаем). Свёрнутые группы, режимы групп цели, раскрытые алиасы — свои у каждого
направления.

Порядок, группы, алиасы, высоты строк и кабели считает cable_layout (без Qt); здесь — рисование, выделение,
перетаскивание, правый клик и подсказки. Профиль — рабочая копия страницы Profiles: виджет его НЕ меняет, а
сигналами просит страницу (connect_requested / group_drop_requested / disconnect_requested / strike_requested /
write_to_requested) — правила меняет ядро (core/profile.py) через страницу. Ноты и строки
цели в сигналах — ориентированного профиля (в REVERSE ноты — целевой карты, строки цели — артикуляции исходной);
страница разбирает их по направлению.

Мышь: строки пула и колонки «from» выделяются (Ctrl/Shift — несколько) и перетаскиваются на строку цели (назначение
по совпадению номеров, см. assign_plan) или на заголовок группы цели (n → n для совпавших номеров); заголовок
группы пула тоже можно перетащить — со всеми его нотами. Кабель-превью
догоняет курсор с лёгкой пружиной (таймер ~60 кадров/с), у края сцены — автопрокрутка (пул не прокручивается:
в него не бросают, строки пула во время перетаскивания не двигаются), Esc — отмена.
Наведение на заголовок группы цели во время перетаскивания (~500 мс) показывает все её артикуляции.
Правый клик: кабель (или подключённая строка) — снять кабель; строка или группа пула — зачеркнуть
(правило delete) / вернуть (без правила). Правая кнопка с протяжкой по сцене — «росчерк» (_Swipe): каждый кабель,
который пересёк путь курсора (отрезки между событиями мыши, а не точки — быстрый росчерк ничего не пропускает),
отмечается; отпустили — все отмеченные снимаются одним шагом отмены; Esc — отмена. Во время росчерка раскладка
не перестраивается. Бейдж «+N» строки цели — меню выбора Write to.
Строка цели показывает номера, на которые идут кабели (TargetRow.lines); Write to — цветом акцента.

Подсказки (set_suggestions) — пунктирные кабели (на мышь не реагируют), у строки-подсказки — кольцо вместо точки.
Имя или подпись не помещается — полностью в подсказке.

После каждой правки — refresh(): раскладка строится заново (порядок не замораживается: снятая с кабеля нота
сразу в своей группе пула). Чтобы вид не прыгал, прокрутка каждой колонки держится за якорь — строку под курсором
или верхнюю видимую (у сцены — строки и заголовки цели). Сворачивание в пуле и раскрытие алиасов перестраивают
только свою колонку.
"""
from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QFont, QPainter, QPainterPath, QPainterPathStroker, QPen
from PySide6.QtWidgets import (
    QApplication, QGraphicsItem, QGraphicsPathItem, QGraphicsScene, QGraphicsView, QHBoxLayout, QMenu, QFrame, QWidget,
)

from ..core.notemap import primary_note
from ..core.pitch import note_tip
from ..core.profile import FORWARD, NO_RULE, REVERSE, RemapProfile, names_differ, validate_profile
from .cable_layout import (
    DELETE, KEEP, MIXED, POOL_PREFIX, TARGET_PREFIX, UNASSIGNED, Cable, CableLayout, Header, RowMetrics, Ruler,
    SourceRow, TargetRow, build_layout, initial_show_all, scene_columns, target_group_keys,
)
from . import plates, text, theme
from .field import ScreenButton
from .glass import Screen
from .split import SplitRow
from .metal import RecessedBlock
from .tips import tip

POOL_ROWS = RowMetrics(*theme.POOL_ROWS)
SCENE_ROWS = RowMetrics(*theme.SCENE_ROWS)
RADIUS = 5
PAD = 8             # поля сцены
SIDE_KEY = "layout/profiles_side"  # ширина пула
MARK_W = 24
BADGE_W = 32        # бейдж «+N» строки цели (кликабельный)
CHEVRON_W = 18      # шеврон раскрытия алиасов справа в строке
INDENT = 14         # отступ строк нот под заголовком раскрытых алиасов
PORT = theme.CABLE_PORT_RADIUS     # радиус точки подключения кабеля
CABLE_W = theme.CABLE_WIDTH        # кабели, подсказки (пунктир), превью
CABLE_HOVER_EXTRA = 1.0            # кабель под курсором — толще на столько
CABLE_HIT = 16      # ширина зоны попадания по кабелю (по 8 px в стороны)
DIMMED = 0.3        # прозрачность прочих кабелей, пока один под курсором
SWIPE_W = 6         # росчерк: ширина полосы пути курсора и кабеля при проверке пересечения, px
SUGGESTED = 0.7     # непрозрачность пунктирного кабеля подсказки

SIDES = {FORWARD: ("source", "target"), REVERSE: ("target", "source")}  # карты сторон «from» и «to» направления

FRAME_MS = 16                   # кадр кабеля-превью и автопрокрутки
STIFFNESS, DAMPING = 0.3, 0.6   # пружина конца кабеля-превью (лёгкое запаздывание, без раскачки)
SAG = 0.12                      # провис кабеля-превью: доля длины (не больше SAG_MAX px)
SAG_MAX = 48.0
EDGE = 32                       # зона автопрокрутки у верхнего/нижнего края, px
SCROLL_MAX = 18                 # px за кадр
SPRING_LOAD_MS = 500            # наведение на заголовок группы цели при перетаскивании — показать все
MAX_PREVIEW = 24                # кабелей-превью при перетаскивании многих строк

POOL, SOURCE, TARGET = "pool", "source", "target"  # роль строки: пул, колонка «from», цель

# Подсказки строк, кабелей и плашек цели (через tip(), не больше трёх строк): высота ноты, куда идёт, замечания и
# ручные правки, действие правой кнопкой. То, что видно на плашке, и жесты, которым учит обучение (перетаскивание,
# росчерк), не повторяются.
DELETED_TIP = "Deleted from converted files"
KEPT_TIP = "Kept on the same number"
# ←: ноты цели без обратного правила при сохранении не спрашиваются (полнота — статус)
REVERSE_UNASSIGNED_TIP = "No rule here: kept on the same number"
MIXED_TIP = "Different rules: shown one by one"
REMOVE_ACTION = "Right-click: remove"
DELETE_ACTION = "Right-click: delete"
RESTORE_ACTION = "Right-click: restore"
SAME_NUMBER_HINT = "Double-click: same number"
SUGGESTED_HINT = "Suggested: apply in the bar above"
SUGGESTED_WRITE_TO_HINT = "Suggested, needs a Write to note: Apply skips it"
NAMES_DIFFER_TIP = "Names differ"
NOT_WRITE_TO_TIP = "Not the Write to note ({n})"
WRITE_TO_TIP = "Write to: {n}"
NO_WRITE_TO_TIP = "Write to: not chosen"
BADGE_HINT = "Click {pill}: choose the Write to"
HAND_SET_TIP = "Set by hand: forward edits don't change it"
HAND_SET_SOME_TIP = "Set by hand ({notes})"
HAND_REMOVED_TIP = "Removed by hand: forward edits don't restore it"
HAND_REMOVED_SOME_TIP = "Removed by hand ({notes})"
TIP_LINES = 3
POOL_TITLE = "Unassigned"
POOL_TIP = ("{side} notes not connected in this direction, by instrument.\n"
            "Struck-through notes are deleted: right-click to restore")
EMPTY_HINT = "Drag notes from Unassigned onto the {side} map"
GROUP_HINT = "Right-click to delete or restore the whole group"
TARGET_GROUP_HINT = "Drop notes here to connect those with the same numbers"


def tip_lines(head: str, details: list[str], action: str = "") -> str:
    """Текст подсказки: первая строка, замечания, действие; больше TIP_LINES строк — замечания в одну строку через «·»."""
    details = [d for d in details if d]
    if len(details) + 1 + bool(action) > TIP_LINES and len(details) > 1:
        details = [" · ".join(details)]
    return "\n".join([line for line in (head, *details, action) if line])


def with_name(name: str, text: str) -> str:
    """Полное имя первой строкой подсказки; строк стало больше TIP_LINES — средние склеиваются через «·»."""
    lines = [name, *text.splitlines()]
    if len(lines) > TIP_LINES:
        lines = [lines[0], " · ".join(lines[1:-1]), lines[-1]]
    return "\n".join(lines)


def cable_path(a: QPointF, b: QPointF) -> QPainterPath:
    """Плавный кубический Безье: горизонтальные касательные на концах."""
    path = QPainterPath(a)
    dx = theme.CABLE_TANGENT
    path.cubicTo(QPointF(a.x() + dx, a.y()), QPointF(b.x() - dx, b.y()), b)
    return path


def preview_path(a: QPointF, b: QPointF) -> QPainterPath:
    """Кабель-превью: тот же Безье с лёгким провисом вниз (пропорционально длине)."""
    sag = min(SAG_MAX, math.hypot(b.x() - a.x(), b.y() - a.y()) * SAG)
    dx = max(30.0, abs(b.x() - a.x()) / 2)
    path = QPainterPath(a)
    path.cubicTo(QPointF(a.x() + dx, a.y() + sag), QPointF(b.x() - dx, b.y() + sag), b)
    return path


# --- элементы сцены ---

class _Row(QGraphicsItem):
    """Строка: фон со скруглением, номер, высота ноты, имя, бейдж «+N» и маркер справа; точка кабеля слева
    или справа. Одна строка — одна плашка с одним номером; rect — слот (зона попадания), плашка внутри.

    role — POOL / SOURCE / TARGET; model — SourceRow или TargetRow из раскладки. pill — текст бейджа («+N» —
    ещё N нот: алиасы источника или скрытые ноты артикуляции цели); badge — бейдж кликабелен (меню Write to).
    port — сторона точки кабеля ("left" / "right"); dim — имя приглушено (нет имени, нота зачёркнута).

    Цель группой (TargetRow.expanded: напротив больше одной строки) — как раскрытые алиасы слева: плашка-заголовок с
    именем (и бейджем) на строке 0 и под ней по плашке на каждый номер, даже если номер один (только номер, уже на
    INDENT справа); кабели приходят на плашки номеров.
    Состояние у каждой плашки своё: выбрана — номер, куда идёт кабель выбранной строки (lit), drop и кабель под
    курсором — тоже по номеру. Подсказка — у плашки под курсором (part_tips)."""

    def __init__(self, rect: QRectF, role: str, model: SourceRow | TargetRow, number: str, name: str,
                 *, dim=False, strike=False, italic=False, marker="", pill="", chevron: str | None = None,
                 badge=False, port: str | None = None, dashed=False, warn=False, tooltip="",
                 metrics: RowMetrics = POOL_ROWS) -> None:
        super().__init__()
        self.rect, self.role, self.model, self.metrics = rect, role, model, metrics  # rect — слот, плашка внутри
        self.number, self.name = number, name  # высота ноты (C#1) для барабанов смысла не несёт — только в подсказке
        self.dim, self.strike, self.italic, self.marker = dim, strike, italic, marker
        self.pill, self.chevron, self.badge = pill, chevron, badge  # chevron: collapsed / expanded / fixed
        self.port, self.dashed, self.warn = port, dashed, warn
        self.highlighted = False
        self.hot: int | None = None  # номер кабеля под курсором (у раскрытой цели подсвечивается его плашка)
        self.selected = False
        self.lit: set[int] = set()   # номера, куда идут кабели выбранных строк
        self.drop_zone: tuple | None = None  # строка цели под кабелем-превью: зона (см. zone_at)
        self.expanded = role == TARGET and getattr(model, "expanded", False)
        self._hover = False
        self._part: int | str | None = None  # плашка раскрытой цели под курсором: "head" или номер
        self.part_tips: dict[int | str, str] = {}
        self.tip_text = ""
        self.base_tips: tuple[str, str | None] | None = None  # подсказки без полного имени (см. _full_name)
        self.setZValue(1)
        self.setAcceptHoverEvents(True)
        self.set_tip(tooltip)

    def set_tip(self, text: str) -> None:
        """Подсказка (простой текст хранится в tip_text, Qt получает tip())."""
        self.tip_text = text
        self.setToolTip(tip(text) if text else "")

    def set_rect(self, rect: QRectF) -> None:
        """Новый слот (смена ширины колонки): элемент остаётся тем же."""
        if rect != self.rect:
            self.prepareGeometryChange()
            self.rect = rect

    @property
    def notes(self) -> tuple[int, ...]:
        return self.model.notes

    def number_rect(self, off: int) -> QRectF:
        """Зона номера на строке off блока — цель drop «ровно на эту ноту» (у раскрытой цели — слот плашки номера)."""
        width = self.rect.width() - INDENT if self.expanded else plates.NAME_OFFSET
        return QRectF(self.rect.left(), self.rect.top() + off * self.metrics.pitch, width, self.metrics.pitch)

    def head_rect(self) -> QRectF:
        """Плашка на строке 0: строка целиком или заголовок цели группой."""
        m = self.metrics
        return QRectF(self.rect.left(), self.rect.top() + m.inset, self.rect.width(), m.plate)

    def child_rect(self, off: int) -> QRectF:
        """Плашка номера раскрытой цели на строке off: уже заголовка на INDENT справа (зеркально алиасам слева)."""
        m = self.metrics
        return QRectF(self.rect.left(), self.rect.top() + off * m.pitch + m.inset, self.rect.width() - INDENT, m.plate)

    def part_at(self, pt: QPointF) -> int | str:
        """Плашка раскрытой цели под точкой: номер или "head" (заголовок и зазоры)."""
        for off, n in self.model.numbers:
            if self.number_rect(off).contains(pt):
                return n
        return "head"

    def line_center(self, off: int = 0) -> float:
        """y центра плашки на строке off блока: сюда приходит кабель."""
        m = self.metrics
        return self.rect.top() + m.inset + off * m.pitch + m.plate / 2

    def zone_at(self, pt: QPointF) -> tuple:
        """Зона drop строки цели под точкой сцены: ("badge",) — бейдж «+N» / «…» (меню нот артикуляции);
        ("line", смещение, нота) — номер на строке (ровно на эту ноту); ("row",) — остальное (назначение на артикуляцию, assign_plan)."""
        badge = self.badge_rect()
        if badge is not None and badge.contains(pt):
            return ("badge",)
        if self.role == TARGET:
            for off, n in self.model.numbers:
                if self.number_rect(off).contains(pt):
                    return ("line", off, n)
        return ("row",)

    def set_drop_zone(self, zone: tuple | None) -> None:
        if zone != self.drop_zone:
            self.drop_zone = zone
            self.update()

    def set_highlighted(self, on: bool, number: int | None = None) -> None:
        if (on, number) != (self.highlighted, self.hot):
            self.highlighted, self.hot = on, number
            self.update()

    def set_selected(self, on: bool) -> None:
        if on != self.selected:
            self.selected = on
            self.update()

    def set_lit(self, numbers: set[int]) -> None:
        if numbers != self.lit:
            self.lit = set(numbers)
            self.update()

    def boundingRect(self) -> QRectF:
        return self.rect.adjusted(-PORT - 1, 0, PORT + 1, 0)

    def _right(self) -> float:
        """Правый край содержимого (левее шеврона)."""
        return self.rect.right() - (CHEVRON_W + 4 if self.chevron else 0)

    def _pill_right(self) -> float:
        return self._right() - (MARK_W if self.marker else 0)

    def name_room(self) -> float:
        """Ширина под имя, px (имя длиннее — обрезается, полное — в подсказке)."""
        x = self.rect.left() + plates.NAME_OFFSET
        return max(0.0, self._pill_right() - (BADGE_W if self.pill else 8) - x)

    def chevron_rect(self) -> QRectF | None:
        """Зона шеврона алиасов (в координатах сцены); None — шеврона нет или он не переключается."""
        if self.chevron not in ("collapsed", "expanded"):
            return None
        return QRectF(self.rect.right() - CHEVRON_W - 4, self.rect.top(), CHEVRON_W + 4, self.metrics.pitch)

    def badge_rect(self) -> QRectF | None:
        """Зона кликабельного бейджа (меню Write to строки цели)."""
        if not self.badge or not self.pill:
            return None
        return QRectF(self._pill_right() - BADGE_W - 4, self.rect.top(), BADGE_W + 4, self.metrics.pitch)

    def hoverEnterEvent(self, event) -> None:
        self._hover = True
        self.update()

    def hoverMoveEvent(self, event) -> None:
        pos = event.scenePos()
        hot = any(r is not None and r.contains(pos) for r in (self.chevron_rect(), self.badge_rect()))
        self.setCursor(Qt.CursorShape.PointingHandCursor if hot else Qt.CursorShape.ArrowCursor)
        if self.expanded:
            self.set_part(self.part_at(pos))

    def set_part(self, part: int | str | None) -> None:
        """Плашка раскрытой цели под курсором: её подсказка и наведение."""
        if part != self._part:
            self._part = part
            self.set_tip(self.part_tips.get(part, "") if part is not None else self.part_tips.get("head", ""))
            self.update()

    def hoverLeaveEvent(self, event) -> None:
        self._hover = False
        if self.expanded:
            self.set_part(None)
        self.update()

    def state(self) -> str:
        """Состояние плашки: выбрана (у цели — в неё идёт кабель выбранной строки), с замечанием, цель перетаскивания или кабель под курсором (рамка акцентом), наведение,
        зачёркнута, подсказка."""
        zone = self.drop_zone[0] if self.drop_zone else None
        if self.selected and not (self.role == TARGET and (self.highlighted or zone)):  # у цели отклик drop важнее
            return "selected"
        if self.warn:
            return "warn"
        if self.highlighted or zone == "row":
            return "drop"
        if self._hover or zone:
            return "hover"
        if self.strike:
            return "deleted"
        return "suggested" if self.dashed else "normal"

    def part_state(self, part: int | str) -> str:
        """Состояние плашки раскрытой цели: "head" — заголовок, иначе номер."""
        zone = self.drop_zone
        if part == "head":
            if zone and zone[0] == "row":
                return "drop"
            if (zone and zone[0] == "badge") or self._part == "head":
                return "hover"
            return "suggested" if self.dashed else "normal"
        if (zone and zone[0] == "line" and zone[2] == part) or (self.highlighted and self.hot == part):
            return "drop"  # у цели отклик drop важнее выбора
        if part in self.lit:
            return "selected"
        if self._part == part:
            return "hover"
        return "suggested" if self.dashed else "normal"

    def plate_rect(self) -> QRectF:
        """Плашка в слоте (остальной слот — только зона drop); у цели группой — от заголовка до последнего номера."""
        if self.expanded:
            last = max(off for off, _ in self.model.numbers)
            return self.head_rect().united(self.child_rect(last))
        return self.head_rect()

    def _paint_expanded(self, p: QPainter) -> None:
        m = self.metrics
        head = self.head_rect()
        plates.paint_plate(p, head, self.part_state("head"), name=self.name, name_room=self.name_room(),
                           line_h=m.plate)
        if self.pill:
            pill = QRectF(self._pill_right() - BADGE_W, head.center().y() - theme.BADGE_HEIGHT / 2, BADGE_W - 6,
                          theme.BADGE_HEIGHT)
            plates.paint_badge(p, pill, self.pill, hot=bool(self.drop_zone) and self.drop_zone[0] == "badge")
        for off, n in self.model.numbers:
            plates.paint_plate(p, self.child_rect(off), self.part_state(n), numbers=[(0, str(n))], line_h=m.plate)
            if self.port:
                color = plates.cable_color(n in self.lit, self.highlighted and self.hot == n)
                plates.paint_port(p, QPointF(self.rect.left(), self.line_center(off)), PORT, color, self.dashed)

    def paint(self, p: QPainter, option, widget=None) -> None:
        if self.expanded:
            self._paint_expanded(p)
            return
        m = self.metrics
        r = self.plate_rect()
        zone = self.drop_zone[0] if self.drop_zone else None
        plates.paint_plate(p, r, self.state(), numbers=[(0, self.number)], name=self.name, name_room=self.name_room(),
                           italic=self.italic, text_deleted=self.strike, dim_name=self.dim, line_h=m.plate)
        if zone == "line":  # drop ровно на ноту: обведён только номер этой строки (уже обводки строки)
            p.setPen(QPen(theme.qcolor(theme.ACCENT), 1.2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(self.number_rect(self.drop_zone[1]).adjusted(1.5, m.inset + 1, -1.5, -m.inset - 1),
                              RADIUS - 1, RADIUS - 1)
        line = r
        if self.pill:
            pill = QRectF(self._pill_right() - BADGE_W, line.center().y() - theme.BADGE_HEIGHT / 2, BADGE_W - 6,
                          theme.BADGE_HEIGHT)
            plates.paint_badge(p, pill, self.pill, hot=zone == "badge")  # drop на бейдж — меню нот артикуляции
        if self.marker:
            text.draw_text(p, QRectF(self._right() - MARK_W, line.top(), MARK_W - 6, line.height()), self.marker,
                           text.mono(10, QFont.Weight.DemiBold), theme.SCREEN_TEXT_3, plates.RIGHT_MID)
        if self.chevron:
            plates.paint_chevron(p, r.right() - CHEVRON_W + 2, line.center().y(), self.chevron == "collapsed",
                                 self.chevron == "fixed")
        if self.port:  # точка кабеля, со своей стороны
            color = plates.cable_color(self.selected, self.highlighted)
            x = r.left() if self.port == "left" else r.right()
            plates.paint_port(p, QPointF(x, self.line_center()), PORT, color, self.dashed)


class _HeaderItem(QGraphicsItem):
    """Заголовок группы: шеврон, имя, число; клик — свернуть или развернуть (у цели — сменить режим)."""

    def __init__(self, header: Header, on_toggle: Callable[[str], None], tooltip: str, variant: str = "pool") -> None:
        super().__init__()
        self.header, self.variant = header, variant
        self.rect, self.zone = QRectF(), QRectF()  # место — set_geometry()
        self.cols = (0.0, 0.0, 0.0, 0.0)  # колонки сцены (`_scene_columns()`): у заголовка сцены подпись слева, число — над «to»
        self._on_toggle = on_toggle
        self._hover = False
        self.highlighted = False
        self.setZValue(1)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.tip_text = ""
        self.set_tip(tooltip)
        self.base_tip = tooltip  # без полной подписи (см. _full_label)

    def set_tip(self, text: str) -> None:
        self.tip_text = text
        self.setToolTip(tip(text) if text else "")

    def set_geometry(self, rect: QRectF, zone: QRectF | None = None,
                     cols: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)) -> None:
        """Место заголовка; zone — клик и drop с зазорами до соседних плашек."""
        self.prepareGeometryChange()
        self.rect, self.cols = rect, cols
        self.zone = rect.united(zone) if zone is not None else QRectF(rect)
        self.update()

    def set_highlighted(self, on: bool) -> None:
        if on != self.highlighted:
            self.highlighted = on
            self.update()

    def boundingRect(self) -> QRectF:
        return QRectF(self.zone)

    def line_center(self) -> float:
        return self.rect.center().y()

    def label_x(self) -> float:
        return self.rect.left() + plates.header_label_x(self.variant, theme.HEADER_INSET)

    def label_room(self) -> float:
        """Ширина под подпись, px (справа — место под число): заголовок сцены идёт через обе колонки, подпись — в левой."""
        right = self.rect.left() + self.cols[2] if self.variant == "scene" else self.rect.right()
        return max(0.0, right - self.label_x() - 48)

    def label_width(self) -> float:
        return plates.header_label_width(self.header.label)

    def hoverEnterEvent(self, event) -> None:
        self._hover = True
        self.update()

    def hoverLeaveEvent(self, event) -> None:
        self._hover = False
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            event.accept()
            # перестройка сцены удаляет этот элемент — не внутри его же обработчика
            QTimer.singleShot(0, lambda key=self.header.key: self._on_toggle(key))
        else:
            event.ignore()

    def paint(self, p: QPainter, option, widget=None) -> None:
        h = self.header
        count = f"{h.shown} / {h.count}" if h.shown else str(h.count)  # цель: подключённые / все артикуляции
        state = "lit" if self.highlighted else "hover" if self._hover else "normal"
        # треугольник — режим группы, а не видимость строк: ▸ — группа что-то скрывает, ▾ — показывает всё
        plates.paint_group_header(p, self.rect, h.label, count, h.collapsed, variant=self.variant, state=state,
                                  inset=theme.HEADER_INSET, label_room=self.label_room(),
                                  twin_x=self.cols[1] - self.cols[0] + theme.HEADER_INSET if self.variant == "scene"
                                  else None)


class _Bundle(QGraphicsItem):
    """Тонкая рамка вокруг раскрытых алиасов в колонке «from» и раскрытой строки цели в «to»: заголовок и плашки под
    ним читаются как один блок."""

    def __init__(self, rect: QRectF) -> None:
        super().__init__()
        self.rect = rect
        self.setZValue(0)

    def boundingRect(self) -> QRectF:
        return self.rect.adjusted(-1, -1, 1, 1)

    def set_rect(self, rect: QRectF) -> None:
        if rect != self.rect:
            self.prepareGeometryChange()
            self.rect = rect

    def paint(self, p: QPainter, option, widget=None) -> None:
        p.setPen(QPen(theme.qcolor(theme.SCREEN_DIVIDER), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(self.rect, RADIUS + 2, RADIUS + 2)


class _CableItem(QGraphicsPathItem):
    """Кабель: наведение — толще и ярче, его строки подсвечены, остальные кабели приглушены.
    Подсказка (cable.suggested) — пунктир, на мышь не реагирует (действия — у строки и в панели подсказок)."""

    def __init__(self, path: QPainterPath, cable: Cable, editor: CableEditor, src: _Row, dst: _Row,
                 tooltip: str) -> None:
        super().__init__(path)
        self.cable, self.editor, self.src, self.dst = cable, editor, src, dst
        self._hovered = False
        self.swiped = False  # отмечен росчерком правой кнопкой: снимется при отпускании
        self.setZValue(0.5)
        self.setAcceptHoverEvents(not cable.suggested)
        self.tip_text = tooltip if not cable.suggested else ""
        if self.tip_text:
            self.setToolTip(tip(self.tip_text))
        self.set_style(False)

    def set_style(self, hovered: bool) -> None:
        self._hovered = hovered
        if self.cable.suggested:
            pen = QPen(theme.qcolor(plates.cable_color(), SUGGESTED), CABLE_W, Qt.PenStyle.CustomDashLine)
            pen.setDashPattern([3, 3])
            self.setPen(pen)
            self.setZValue(0.4)
            return
        if self.swiped:  # снимется при отпускании правой кнопки — цвет ошибки, толще
            pen = QPen(theme.qcolor(theme.ERR_LED), CABLE_W + CABLE_HOVER_EXTRA, Qt.PenStyle.DashLine)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            self.setPen(pen)
            self.setZValue(0.7)
            return
        color = plates.cable_color(self.src.selected, hovered)  # кабель выбранной строки — белый
        width = theme.CABLE_SELECTED_WIDTH if self.src.selected else CABLE_W
        pen = QPen(theme.qcolor(color), width + CABLE_HOVER_EXTRA if hovered else width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        self.setPen(pen)
        self.setZValue(0.6 if hovered else 0.5)

    def set_swiped(self, on: bool) -> None:
        if on != self.swiped:
            self.swiped = on
            self.set_style(False)

    def swipe_shape(self) -> QPainterPath:
        """Полоса кабеля для проверки пересечения с путём росчерка (уже, чем зона наведения)."""
        stroker = QPainterPathStroker()
        stroker.setWidth(SWIPE_W)
        return stroker.createStroke(self.path())

    def shape(self) -> QPainterPath:
        if self.cable.suggested:
            return QPainterPath()  # не перехватывает мышь
        stroker = QPainterPathStroker()
        stroker.setWidth(CABLE_HIT)  # попасть курсором в 2-пиксельную линию
        return stroker.createStroke(self.path())

    def hoverEnterEvent(self, event) -> None:
        self.editor.hover_cable(self)

    def hoverLeaveEvent(self, event) -> None:
        self.editor.hover_cable(None)


# --- представления ---

class _ColumnView(QGraphicsView):
    """Общая настройка обеих view: своя сцена, без горизонтальной прокрутки, перерисовка при смене ширины.
    Мышь и Esc сначала отдаются редактору (handler): выделение, перетаскивание, правый клик."""

    def __init__(self, on_width_changed: Callable[[], None], parent=None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)  # фон и рамка — экран за view
        self.setBackgroundBrush(Qt.BrushStyle.NoBrush)
        self.viewport().setAutoFillBackground(False)
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setMouseTracking(True)
        self.handler: CableEditor | None = None
        self._on_width_changed = on_width_changed
        self._width = 0
        self.hint: tuple[float, float, str] | None = None  # подсказка пустой колонки: x, ширина, текст

    def set_hint(self, hint: tuple[float, float, str] | None) -> None:
        if hint != self.hint:
            self.hint = hint
            self.viewport().update()

    def drawForeground(self, p: QPainter, rect: QRectF) -> None:
        if self.hint is not None:  # по центру видимой части колонки (не зависит от высоты сцены)
            x, width, text = self.hint
            visible = self.mapToScene(self.viewport().rect()).boundingRect()
            p.setFont(self.font())
            p.setPen(theme.qcolor(theme.SCREEN_TEXT_3))
            p.drawText(QRectF(x, visible.top(), width, visible.height()),
                       Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, text)

    def width_px(self) -> int:
        return self.viewport().width()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.viewport().width() != self._width:
            self._width = self.viewport().width()
            self._on_width_changed()

    def mousePressEvent(self, event) -> None:
        if self.handler is None or not self.handler.view_press(self, event):
            super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        # второй клик двойного — как обычный (шеврон, выделение), а не событие элементов
        if self.handler is None or not self.handler.view_press(self, event):
            super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self.handler is None or not self.handler.view_move(self, event):
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self.handler is None or not self.handler.view_release(self, event):
            super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape and self.handler is not None:
            if self.handler.dragging:
                self.handler.cancel_drag()
                return
            if self.handler.swiping:
                self.handler.cancel_swipe()
                return
        super().keyPressEvent(event)

    def begin(self) -> None:
        """Очистить сцену (позиция прокрутки сохраняется в end())."""
        self._scroll = self.verticalScrollBar().value()
        self.scene().clear()

    def fit(self, height: int) -> None:
        """Размер сцены: ширина view и высота содержимого."""
        self.scene().setSceneRect(0, 0, self.width_px(), height + 2 * PAD)

    def end(self) -> None:
        self.verticalScrollBar().setValue(self._scroll)


class CableOverlay(QWidget):
    """Прозрачный для мыши слой поверх пула и сцены: кабели-превью от строк к курсору (через границу колонок)."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setStyleSheet("background: transparent;")
        self.preview: list[QPainterPath] | None = None
        self.end: QPointF | None = None
        self.valid = False  # под курсором — строка цели (кабель ярче)

    def show_preview(self, starts: list[QPointF], end: QPointF, valid: bool = False) -> None:
        self.preview = [preview_path(a, end) for a in starts]
        self.end, self.valid = end, valid
        self.update()

    def clear_preview(self) -> None:
        self.preview = self.end = None
        self.update()

    def paintEvent(self, event) -> None:
        if self.preview is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = plates.cable_color(hovered=self.valid)
        pen = QPen(theme.qcolor(color), CABLE_W)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for path in self.preview:
            p.drawPath(path)
        plates.paint_port(p, self.end, PORT, color)


@dataclass
class _Press:
    """Нажатие на строку слева: может стать перетаскиванием или кликом."""
    view: _ColumnView
    notes: frozenset[int]
    pos: QPointF                 # в координатах viewport
    select_on_release: bool      # клик по уже выделенной строке без модификаторов: выделить только её при отпускании
    header: str | None = None    # нажали на заголовок пула: клик — свернуть, перетаскивание — все его ноты


@dataclass
class _Swipe:
    """Правая кнопка нажата в сцене: без сдвига — обычный правый клик (item), со сдвигом — росчерк."""
    item: object                 # элемент под курсором при нажатии (для обычного правого клика)
    start: QPointF               # в координатах viewport
    last: QPointF                # точка сцены прошлого события — начало следующего отрезка пути
    active: bool = False         # сдвинули дальше startDragDistance — это росчерк
    shapes: dict = field(default_factory=dict)  # кабель -> полоса для пересечения (считается один раз)


@dataclass
class _Drag:
    """Перетаскивание кабеля: ноты, курсор и конец превью (догоняет курсор пружиной) в координатах CableEditor."""
    notes: tuple[int, ...]
    cursor: QPointF
    pos: QPointF
    vel: QPointF
    hover: _Row | _HeaderItem | None = None
    header: str | None = None    # тащат заголовок пула: кабель-превью — от него
    zone: tuple | None = None    # зона строки цели под курсором (_Row.zone_at)

    def step(self) -> None:
        """Шаг пружины с затуханием: конец кабеля догоняет курсор с лёгким запаздыванием."""
        self.vel = self.vel * DAMPING + (self.cursor - self.pos) * STIFFNESS
        self.pos = self.pos + self.vel


@dataclass
class _ViewState:
    """Свёрнутость вида — своя у каждого направления (ключи групп двух карт могут совпасть)."""
    collapsed: set[str] = field(default_factory=set)  # свёрнутые группы пула
    show_all: set[str] = field(default_factory=set)   # группы цели в режиме «все»
    expanded: set[str] = field(default_factory=set)   # раскрытые алиасы («<место>|<имя>»)
    seen: set[str] = field(default_factory=set)       # группы цели, начальный режим которых уже задан


POOL_HEAD_BELOW = 6  # padding-bottom заголовка пула


class _PoolHeader(QWidget):
    """Заголовок пула внутри экрана: «UNASSIGNED» акцентом слева, кнопка «Match by number» справа, линия под ними.
    Размеры — из макета: отступ сверху 8 (поле экрана), строка 30 px, под ней 6 px и линия 1 px (padding-bottom)."""

    def __init__(self, button: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._spec = text.mono(theme.POOL_HEAD_FONT, QFont.Weight.DemiBold, theme.POOL_HEAD_SPACING)
        self.setFixedHeight(PAD + theme.POOL_HEAD_H + POOL_HEAD_BELOW + 1)
        box = QHBoxLayout(self)
        box.setContentsMargins(PAD, PAD, PAD, POOL_HEAD_BELOW + 1)
        box.setSpacing(0)
        box.addStretch(1)
        box.addWidget(button, 0, Qt.AlignmentFlag.AlignVCenter)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        body = QRectF(PAD, PAD, self.width() - 2 * PAD, theme.POOL_HEAD_H)
        text.draw_text(p, body, POOL_TITLE.upper(), self._spec, theme.ACCENT)
        p.fillRect(QRectF(PAD, self.height() - 1, self.width() - 2 * PAD, 1), theme.qcolor(theme.SCREEN_DIVIDER))


class CableEditor(QWidget):
    """Пул | сцена (ряд `SplitRow`): подключённые и цель + слой для кабелей-превью поверх всего."""

    connect_requested = Signal(list, str)   # ноты, строка цели (slot): map — решает страница (Write to и т.п.)
    group_drop_requested = Signal(list, list)  # ноты, ноты группы цели: n → n для совпавших номеров
    disconnect_requested = Signal(list)     # ноты: снять кабель (правило убрать)
    strike_requested = Signal(list)         # ноты: зачеркнуть (delete) или, если все зачёркнуты, вернуть
    write_to_requested = Signal(int)        # нота цели: сделать Write to и перенаправить правила
    same_number_requested = Signal(list)    # двойной клик по строке Unassigned: ноты — на те же номера
    note_drop_requested = Signal(list, int)  # drop на номер строки цели (или выбор в меню бейджа): ровно на ноту

    def __init__(self, parent=None, *, settings=None) -> None:
        """settings — ui.ini: ширина пула (боковая колонка ряда `split`, ключ SIDE_KEY)."""
        super().__init__(parent)
        self.pool = _ColumnView(self._reflow_pool)
        self.view = _ColumnView(self._reflow_scene)
        self.pool.handler = self.view.handler = self
        # пул и сцена — экраны в утопленных блоках; view стоят с запасом PAD вокруг содержимого (см. docstring модуля)
        self.match_btn = ScreenButton("Match by number")
        self.pool_title = _PoolHeader(self.match_btn)
        self.pool_screen, self.scene_screen = Screen(), Screen()
        for screen, head, view in ((self.pool_screen, self.pool_title, self.pool),
                                   (self.scene_screen, None, self.view)):
            screen.body.setContentsMargins(*[theme.SCREEN_PAD + 1 - PAD] * 4)
            if head is not None:
                head.setParent(screen)
                screen.body.addWidget(head)
            screen.body.addWidget(view, stretch=1)
            screen.attach(view)
        self.pool_block, self.scene_block = RecessedBlock(), RecessedBlock()
        self.pool_block.body.addWidget(self.pool_screen)
        self.scene_block.body.addWidget(self.scene_screen)
        # пул — боковая колонка слева (ширина в ui.ini), сцена забирает остальное; ширины макета — минимум
        self.split = SplitRow(self.scene_block, self.pool_block, side_first=True, side_min=theme.POOL_W,
                              main_min=theme.SCENE_W, settings=settings, key=SIDE_KEY, parent=self)
        box = QHBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.addWidget(self.split)
        self.overlay = CableOverlay(self)

        self.pool_ruler = Ruler(0, (), POOL_ROWS)    # строки раскладки -> px, по текущей раскладке
        self.scene_ruler = Ruler(0, (), SCENE_ROWS)
        self.profile: RemapProfile | None = None  # рабочая копия страницы (настоящий профиль)
        self.direction = FORWARD
        self.shown: RemapProfile | None = None    # profile.oriented(direction) — по нему строится вид
        self._state = {FORWARD: _ViewState(), REVERSE: _ViewState()}  # свёрнутость — своя у направления
        self.selection: set[int] = set()                   # выделенные ноты (строки пула и колонки «from»)
        self.suggested: dict[int, str] = {}                # подсказки: нота без правила -> артикуляция цели
        self.current: CableLayout | None = None  # последняя построенная раскладка
        self.cable_items: list[_CableItem] = []
        self.suggestion_items: list[_CableItem] = []             # пунктирные кабели подсказок
        self.pool_items: dict[int, _Row] = {}                    # нота -> строка пула (у алиасов — общая)
        self.source_items: dict[int, _Row] = {}                  # нота -> строка колонки «from»
        self.pool_rows: list[_Row] = []
        self.pool_headers: dict[str, _HeaderItem] = {}           # заголовки пула по ключу
        self.scene_rows: list[_Row] = []
        self._bundles: list[tuple[_Bundle, bool, int, int]] = []  # рамки сцены: (рамка, в «from», строка, строк)
        self.target_items: dict[str, _Row] = {}                  # строки цели по slot
        self.scene_headers: dict[str, _HeaderItem] = {}          # заголовки групп цели по ключу
        self.hovered: _CableItem | None = None
        self._issues: dict[int, list[str]] = {}  # нота -> тексты замечаний (подсказка строки)
        self._press: _Press | None = None
        self._anchor: tuple[_ColumnView, frozenset[int]] | None = None  # начало диапазона Shift+клика
        self._drag: _Drag | None = None
        self._swipe: _Swipe | None = None
        self._frame = QTimer(self)
        self._frame.setInterval(FRAME_MS)
        self._frame.timeout.connect(self._tick)
        self._spring = QTimer(self)
        self._spring.setSingleShot(True)
        self._spring.setInterval(SPRING_LOAD_MS)
        self._spring.timeout.connect(self._spring_open)
        self._spring_key: str | None = None

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.overlay.setGeometry(self.rect())
        self.overlay.raise_()

    # --- направление ---

    @property
    def collapsed(self) -> set[str]:
        return self._state[self.direction].collapsed

    @collapsed.setter
    def collapsed(self, value: set[str]) -> None:
        self._state[self.direction].collapsed = set(value)

    @property
    def show_all(self) -> set[str]:
        return self._state[self.direction].show_all

    @show_all.setter
    def show_all(self, value: set[str]) -> None:
        self._state[self.direction].show_all = set(value)

    @property
    def expanded(self) -> set[str]:
        return self._state[self.direction].expanded

    @expanded.setter
    def expanded(self, value: set[str]) -> None:
        self._state[self.direction].expanded = set(value)

    @property
    def sides(self) -> tuple[str, str]:
        """Карты сторон «from» и «to» направления: "source" / "target"."""
        return SIDES[self.direction]

    def set_direction(self, direction: str) -> None:
        """Сменить направление. Вид остаётся на той же группе инструментов: группа вверху
        видимой части сцены (по normalize_name подписи) — после перестройки снова вверху; нет такой — к началу."""
        if direction == self.direction:
            return
        group = self._top_group()
        self.cancel_drag()
        self.cancel_swipe()
        self.selection.clear()
        self.direction = direction
        self._build(anchor=False)
        self._scroll_to_group(group)

    def _top_group(self) -> str | None:
        """Ключ группы цели, которой принадлежит верх видимой части сцены (None — групп нет)."""
        if self.current is None or not self.current.scene.target_headers:
            return None
        ruler = self.scene_ruler
        top = self.view.mapToScene(QPoint(0, 0)).y() - PAD + SCENE_ROWS.pitch / 2
        heads = sorted(self.current.scene.target_headers, key=lambda h: h.y)
        above = [h for h in heads if ruler.top(h.y) <= top]
        return (above[-1] if above else heads[0]).key

    def _scroll_to_group(self, key: str | None) -> None:
        h = self.current.header(key) if self.current is not None and key is not None else None
        self.view.verticalScrollBar().setValue(0 if h is None else self.scene_ruler.top(h.y))  # над заголовком — поле PAD

    # --- управление ---

    def set_profile(self, p: RemapProfile | None, reset_collapsed: bool = True, direction: str | None = None) -> None:
        """Другой профиль (или тот же после сохранения/отката, смены карты). reset_collapsed — свёрнутость по умолчанию в обоих направлениях (открытие профиля);
        direction — сразу в этом направлении (None — в текущем)."""
        self.cancel_drag()
        self.cancel_swipe()
        self.profile = p
        if direction is not None:
            self.direction = direction
        self.selection.clear()
        if reset_collapsed:
            self._state = {FORWARD: _ViewState(), REVERSE: _ViewState()}
        self._build(anchor=reset_collapsed is False)

    def reveal(self, note: int) -> None:
        """Строка ноты в сцене и номер её цели должны быть видны: минимальная прокрутка (уже видны — без
        движения, к началу не прыгает)."""
        item = self.source_items.get(note)
        if item is None:
            return
        rect = QRectF(item.rect)
        cable = next((c for c in self.cable_items if c.src is item), None)
        if cable is not None:
            dst, m = cable.dst.rect, SCENE_ROWS
            rect = rect.united(QRectF(dst.left(), PAD + self.scene_ruler.top(cable.cable.dst_y) - m.inset, dst.width(),
                                      m.pitch))
        self.view.ensureVisible(rect, 0, SCENE_ROWS.pitch // 2)

    def set_suggestions(self, suggested: dict[int, str]) -> None:
        """Подсказки для показа пунктиром (перестройка — refresh())."""
        self.suggested = dict(suggested)

    def refresh(self) -> None:
        """Правила (или подсказки) изменились: раскладка заново, прокрутка — за якорь."""
        self._build()

    def toggle_pool(self, key: str) -> None:
        """Свернуть/развернуть группу пула: перестраивается только пул."""
        self.collapsed ^= {key}
        self._build(scene=False)

    def toggle_target(self, key: str) -> None:
        """Группа цели: «только подключённые» ↔ «все»."""
        self.show_all ^= {key}
        self._build()

    def toggle_alias(self, key: str, in_pool: bool) -> None:
        """Раскрыть/свернуть алиасы: перестраивается только своя колонка."""
        self.expanded ^= {key}
        self._build(pool=in_pool, scene=not in_pool)

    def selected_notes(self) -> list[int]:
        return sorted(self.selection)

    def set_selection(self, notes: set[int]) -> None:
        self.selection = set(notes)
        for item in self.pool_rows + self.scene_rows:
            item.set_selected(bool(self.selection) and set(item.notes) <= self.selection)
        # строка цели выбрана, если в неё идёт кабель выбранной строки (как в макете: многие-в-одну — цель белая);
        # у раскрытой — плашки тех номеров, куда идут эти кабели
        lit: dict[int, set[int]] = {}
        for c in self.cable_items:
            if c.src.selected and c.cable.dst is not None:
                lit.setdefault(id(c.dst), set()).add(c.cable.dst)
        for item in self.target_items.values():
            item.set_selected(id(item) in lit)
            item.set_lit(lit.get(id(item), set()))
        for cable in self.cable_items + self.suggestion_items:
            cable.set_style(cable._hovered)  # кабель выбранной строки — белый

    # --- места для обучения (координаты CableEditor) ---

    def _scene_to_editor(self, rect: QRectF) -> QRectF:
        """Прямоугольник сцены — в координатах CableEditor, обрезанный видимой частью сцены."""
        vp = self.view.viewport()
        shift = QPointF(vp.mapTo(self, QPoint(0, 0))) - self.view.mapToScene(QPoint(0, 0))
        return rect.translated(shift).intersected(QRectF(vp.rect()).translated(QPointF(vp.mapTo(self, QPoint(0, 0)))))

    def target_column_rect(self) -> QRectF:
        """Колонка цели: по x — её строки, по y — экран сцены."""
        _lx, rx, _col2, col3 = self._scene_columns()
        x = self._scene_to_editor(QRectF(rx, self.view.mapToScene(QPoint(0, 0)).y(), col3, 1))
        screen = QRectF(self.scene_screen.rect()).translated(QPointF(self.scene_screen.mapTo(self, QPoint(0, 0))))
        return QRectF(x.left(), screen.top(), x.width(), screen.height())

    def busiest_bundle(self, reveal: bool = False) -> QRectF | None:
        """Связка кабелей в строку цели, куда их сходится больше всего (при равенстве — в верхнюю): промежуток между
        колонками от верха верхней плашки до низа нижней. `reveal` — сначала прокрутить сцену, чтобы связка встала
        посередине (под ней остаётся место для плашки обучения). Кабелей нет (или связка не видна) — None."""
        groups: dict[int, list[_CableItem]] = {}
        for cable in self.cable_items:
            groups.setdefault(id(cable.dst), []).append(cable)
        if not groups:
            return None
        bundle = max(groups.values(), key=lambda cs: (len(cs), -cs[0].dst.rect.top()))
        plates_ = [row.plate_rect() for row in [c.src for c in bundle] + [bundle[0].dst]]
        lx, rx, col2, _col3 = self._scene_columns()
        top, bottom = min(r.top() for r in plates_), max(r.bottom() for r in plates_)
        rect = QRectF(lx + col2, top, rx - lx - col2, bottom - top)
        if reveal:
            self.view.centerOn(rect.center())
        rect = self._scene_to_editor(rect)
        return None if rect.isEmpty() else rect

    def source_anchor(self, note: int) -> QPointF | None:
        """Точка строки ноты (правый край) в координатах CableEditor — начало кабеля-превью.
        None — строки не видно (свёрнута) или вид не построен."""
        for view, items in ((self.view, self.source_items), (self.pool, self.pool_items)):
            item = items.get(note)
            if item is not None:
                return self._anchor_of(view, item)
        return None

    def _anchor_of(self, view: _ColumnView, item: _Row | _HeaderItem) -> QPointF:
        """Правый край первой строки элемента (сторона кабеля); за краем видимой области — прижать к краю."""
        r = item.rect
        pt = view.mapFromScene(QPointF(r.right(), item.line_center()))
        vp = view.viewport()
        y = min(max(pt.y(), 0), vp.height())
        return QPointF(vp.mapTo(self, QPoint(pt.x(), y)))

    # --- наведение ---

    def hover_cable(self, item: _CableItem | None) -> None:
        """Кабель под курсором: он толще и ярче, его строки подсвечены, прочие кабели приглушены."""
        if self._drag is not None or self._swipe is not None:
            item = None
        self.hovered = item
        for c in self.cable_items:
            c.set_style(c is item)
            c.setOpacity(1.0 if item is None or c is item else DIMMED)
        for row in self.scene_rows:
            row.set_highlighted(item is not None and row is item.src)
        for row in self.target_items.values():
            on = item is not None and row is item.dst
            row.set_highlighted(on, item.cable.dst if on else None)

    # --- мышь ---

    @property
    def dragging(self) -> bool:
        return self._drag is not None

    def _item_at(self, view: _ColumnView, pos: QPoint):
        for item in view.items(pos):
            if isinstance(item, _CableItem) and item.cable.suggested:
                continue
            if isinstance(item, (_Row, _HeaderItem, _CableItem)):
                return item
        return None

    def view_press(self, view: _ColumnView, event) -> bool:
        """Нажатие в одной из view. True — обработано здесь (элементам сцены не передавать).
        Нажатие на кабель левой кнопкой ничего не делает (не перетаскивание и не смена выделения)."""
        pos = event.position()
        item = self._item_at(view, pos.toPoint())
        if event.button() == Qt.MouseButton.RightButton:
            if view is self.view and self._drag is None:  # в сцене: клик или росчерк — решит сдвиг
                view.setFocus()  # Esc — отмена росчерка
                self.hover_cable(None)
                self._swipe = _Swipe(item, pos, view.mapToScene(pos.toPoint()))
            else:
                self.right_click(item)
            return True
        if event.button() != Qt.MouseButton.LeftButton or self._drag is not None:
            return self._drag is not None
        if isinstance(item, _CableItem):
            return True
        scene_pt = view.mapToScene(pos.toPoint())
        if isinstance(item, _Row) and item.role == TARGET:
            badge = item.badge_rect()
            if badge is not None and badge.contains(scene_pt):
                at = view.viewport().mapToGlobal(pos.toPoint())
                QTimer.singleShot(0, lambda t=item.model: self._write_to_menu(t, at))
            return True
        if isinstance(item, _HeaderItem) and view is self.pool:
            # клик — свернуть (при отпускании), перетаскивание — все ноты заголовка
            self._press = _Press(view, frozenset(item.header.notes), pos, False, item.header.key)
            return True
        if isinstance(item, _Row):
            chevron = item.chevron_rect()
            if chevron is not None and chevron.contains(scene_pt):
                QTimer.singleShot(0, lambda k=item.model.alias, pool=view is self.pool: self.toggle_alias(k, pool))
                return True
            if (event.type() == QEvent.Type.MouseButtonDblClick and item.role == POOL
                    and item.model.state != DELETE):
                # первое нажатие двойного клика лишь выделило строку (перетаскивания без сдвига нет)
                self._press = None
                QTimer.singleShot(0, lambda notes=list(item.notes): self.same_number_requested.emit(notes))
                return True
            view.setFocus()
            self._press_row(view, item, event.modifiers(), pos)
            return True
        if item is None and not event.modifiers() & (Qt.KeyboardModifier.ControlModifier
                                                     | Qt.KeyboardModifier.ShiftModifier):
            self.set_selection(set())
        return False

    def _press_row(self, view: _ColumnView, item: _Row, mods, pos: QPointF) -> None:
        notes = frozenset(item.notes)
        later = False
        if mods & Qt.KeyboardModifier.ControlModifier:
            self.set_selection(self.selection - notes if notes <= self.selection else self.selection | notes)
            self._anchor = (view, notes)
        elif mods & Qt.KeyboardModifier.ShiftModifier and self._anchor is not None and self._anchor[0] is view:
            self.set_selection(self.selection | self._range(view, self._anchor[1], notes))
        elif notes <= self.selection:
            later = True  # возможно, перетаскивание всего выделения
        else:
            self.set_selection(set(notes))
            self._anchor = (view, notes)
        self._press = _Press(view, notes, pos, later)

    def _range(self, view: _ColumnView, a: frozenset[int], b: frozenset[int]) -> set[int]:
        """Ноты строк view между строками a и b (по порядку показа)."""
        rows = sorted(self.pool_rows if view is self.pool else self.scene_rows, key=lambda i: i.rect.top())
        idx = [i for i, row in enumerate(rows) if frozenset(row.notes) in (a, b)]
        if not idx:
            return set(b)
        return {n for row in rows[min(idx):max(idx) + 1] for n in row.notes}

    def view_move(self, view: _ColumnView, event) -> bool:
        pos = event.position()
        if self._swipe is not None:
            if view is self.view and event.buttons() & Qt.MouseButton.RightButton:
                self._swipe_to(pos)
            return True
        if self._drag is not None:
            self.drag_to(QPointF(view.viewport().mapTo(self, pos.toPoint())))
            return True
        press = self._press
        if press is not None and event.buttons() & Qt.MouseButton.LeftButton:
            if (pos - press.pos).manhattanLength() >= QApplication.startDragDistance():
                at = QPointF(view.viewport().mapTo(self, pos.toPoint()))
                if press.header is not None:
                    self.begin_drag(set(press.notes), at, header=press.header)
                else:
                    notes = self.selection if press.notes <= self.selection else set(press.notes)
                    self.begin_drag(notes, at)
            return True
        return False

    def view_release(self, view: _ColumnView, event) -> bool:
        if event.button() == Qt.MouseButton.RightButton and self._swipe is not None:
            self.end_swipe()
            return True
        if event.button() != Qt.MouseButton.LeftButton:
            return self._drag is not None
        if self._drag is not None:
            self.end_drag(drop=True)
            return True
        press, self._press = self._press, None
        if press is not None:
            if press.header is not None:
                # перестройка пула удаляет заголовок — после обработки события
                QTimer.singleShot(0, lambda key=press.header: self.toggle_pool(key))
                return True
            if press.select_on_release:
                self.set_selection(set(press.notes))
                self._anchor = (press.view, press.notes)
            return True
        return False

    # --- росчерк правой кнопкой ---

    @property
    def swiping(self) -> bool:
        """Правая кнопка нажата в сцене (клик или росчерк ещё не решён / идёт росчерк)."""
        return self._swipe is not None

    def swiped_cables(self) -> list[_CableItem]:
        return [c for c in self.cable_items if c.swiped]

    def _swipe_to(self, pos: QPointF) -> None:
        """Курсор росчерка сдвинулся (pos — viewport сцены): отметить кабели, которые пересёк отрезок от прошлой
        точки до этой. Перестройки нет — только стиль кабелей."""
        sw = self._swipe
        if not sw.active:
            if (pos - sw.start).manhattanLength() < QApplication.startDragDistance():
                return
            sw.active = True
        point = self.view.mapToScene(pos.toPoint())
        self.swipe_segment(sw.last, point)
        sw.last = point

    def swipe_segment(self, a: QPointF, b: QPointF) -> list[_CableItem]:
        """Отметить кабели, которые пересекает отрезок a–b (координаты сцены); вернуть новые отмеченные."""
        sw = self._swipe
        if sw is None:
            return []
        line = QPainterPath(a)
        line.lineTo(b)
        stroker = QPainterPathStroker()
        stroker.setWidth(SWIPE_W)
        band = stroker.createStroke(line)
        box = band.boundingRect()
        hit = []
        for c in self.cable_items:
            if c.swiped or not c.boundingRect().intersects(box):
                continue
            shape = sw.shapes.get(c)
            if shape is None:
                shape = sw.shapes[c] = c.swipe_shape()
            if shape.intersects(band):
                c.set_swiped(True)
                hit.append(c)
        return hit

    def end_swipe(self) -> None:
        """Отпустили правую кнопку: без сдвига — обычный правый клик; росчерк — снять все отмеченные кабели
        одним сигналом (одна правка — один шаг отмены)."""
        sw, self._swipe = self._swipe, None
        if sw is None:
            return
        if not sw.active:
            self.right_click(sw.item)
            return
        notes = sorted({n for c in self.swiped_cables() for n in c.cable.notes})
        if notes:
            self.disconnect_requested.emit(notes)

    def cancel_swipe(self) -> None:
        """Esc во время росчерка: отметки сняты, ничего не удаляется."""
        self._swipe = None
        for c in self.swiped_cables():
            c.set_swiped(False)

    def right_click(self, item) -> None:
        """Кабель или подключённая строка — снять кабель; строка или группа пула, строка без кабеля — зачеркнуть
        или вернуть. Сразу, без контекстного меню."""
        if self._drag is not None:
            return
        p = self.shown
        if isinstance(item, _CableItem):
            self.disconnect_requested.emit(list(item.cable.notes))
        elif isinstance(item, _Row) and item.role in (POOL, SOURCE):
            row = item.model
            if item.role == SOURCE and row.connected:
                mapped = [n for n in row.notes if p.rules.get(n) is not None and p.rules[n].action == "map"]
                self.disconnect_requested.emit(mapped)
            else:
                self.strike_requested.emit(list(row.notes))
        elif isinstance(item, _HeaderItem) and item.header.key.startswith(POOL_PREFIX) and item.header.notes:
            self.strike_requested.emit(list(item.header.notes))

    # --- перетаскивание ---

    def begin_drag(self, notes: set[int], at: QPointF, header: str | None = None) -> None:
        """Начать перетаскивание кабеля от строк с этими нотами (at — курсор в координатах CableEditor).
        header — тащат заголовок пула (кабель-превью — от него)."""
        if not notes:
            return
        self._press = None
        self.hover_cable(None)
        self._drag = _Drag(tuple(sorted(notes)), QPointF(at), QPointF(at), QPointF(0, 0), header=header)
        for v in (self.pool, self.view):
            v.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
        self._frame.start()
        self._tick()

    def drag_to(self, at: QPointF) -> None:
        if self._drag is not None:
            self._drag.cursor = QPointF(at)
            self._update_hover()

    def end_drag(self, drop: bool = True) -> None:
        """Отпустить: над строкой цели — map (через страницу, после перерисовки); иначе — ничего."""
        d = self._drag
        if d is None:
            return
        self._drag = None
        self._frame.stop()
        self._spring.stop()
        self._spring_key = None
        self.overlay.clear_preview()
        if isinstance(d.hover, _Row):
            d.hover.set_drop_zone(None)
        elif d.hover is not None:
            d.hover.set_highlighted(False)
        for v in (self.pool, self.view):
            v.viewport().unsetCursor()
        if drop and isinstance(d.hover, _Row):
            notes, slot, zone = list(d.notes), d.hover.model.slot, d.zone or ("row",)
            self.set_selection(set())
            if zone[0] == "line":  # ровно на эту ноту: без логики Write to и вопросов
                QTimer.singleShot(0, lambda: self.note_drop_requested.emit(notes, zone[2]))
            elif zone[0] == "badge":  # меню всех нот артикуляции — куда пойдёт кабель (Write to не меняется)
                t, at = d.hover.model, self._global(d.cursor)
                QTimer.singleShot(0, lambda: self._destination_menu(notes, t, at))
            else:
                # вопрос о Write to (модальный) — после того, как превью исчезло
                QTimer.singleShot(0, lambda: self.connect_requested.emit(notes, slot))
        elif drop and self._droppable(d.hover):
            notes, targets = list(d.notes), list(d.hover.header.notes)
            self.set_selection(set())
            QTimer.singleShot(0, lambda: self.group_drop_requested.emit(notes, targets))

    def cancel_drag(self) -> None:
        self._press = None
        self.end_drag(drop=False)

    @staticmethod
    def _droppable(item) -> bool:
        """Сюда можно отпустить кабель: строка цели или заголовок группы цели с нотами."""
        return isinstance(item, _Row) or (isinstance(item, _HeaderItem) and bool(item.header.notes))

    def _drop_target_at(self, at: QPointF) -> _Row | _HeaderItem | None:
        """Строка цели или заголовок группы цели под точкой (координаты CableEditor)."""
        vp = self.view.viewport()
        local = vp.mapFrom(self, at.toPoint())
        if not vp.rect().contains(local):
            return None
        for item in self.view.items(local):
            if isinstance(item, _Row) and item.role == TARGET:
                return item
            if isinstance(item, _HeaderItem) and item.header.key.startswith(TARGET_PREFIX):
                return item
        return None

    def _update_hover(self) -> None:
        d = self._drag
        target = self._drop_target_at(d.cursor)
        if target is not d.hover:
            if isinstance(d.hover, _Row):
                d.hover.set_drop_zone(None)
            elif d.hover is not None:
                d.hover.set_highlighted(False)
            d.hover = target
            if isinstance(target, _HeaderItem):
                target.set_highlighted(True)
        # строка цели: зона под курсором — номер строки, бейдж или вся строка
        d.zone = target.zone_at(self._scene_point(d.cursor)) if isinstance(target, _Row) else None
        if isinstance(target, _Row):
            target.set_drop_zone(d.zone)
        # заголовок группы со скрытыми артикуляциями: подержать курсор — показать все
        key = target.header.key if isinstance(target, _HeaderItem) and target.header.collapsed else None
        if key != self._spring_key:
            self._spring_key = key
            if key is None:
                self._spring.stop()
            else:
                self._spring.start()

    def _spring_open(self) -> None:
        key = self._spring_key
        if self._drag is None or key is None:
            return
        self._spring_key = None
        self.show_all.add(key)
        self._build(pool=False)  # пул не трогаем: строки, которые тащат, не двигаются
        self._update_hover()

    def _tick(self) -> None:
        """Кадр перетаскивания: пружина, автопрокрутка, цель под курсором, превью."""
        d = self._drag
        if d is None:
            return
        d.step()
        self._autoscroll(d.cursor)
        self._update_hover()
        self.overlay.show_preview(self._drag_anchors(d), d.pos, self._droppable(d.hover))

    def _drag_anchors(self, d: _Drag) -> list[QPointF]:
        if d.header is not None:
            item = self.pool_headers.get(d.header)
            return [self._anchor_of(self.pool, item)] if item is not None else []
        wanted = set(d.notes)
        out: list[QPointF] = []
        for view, rows in ((self.pool, self.pool_rows), (self.view, self.scene_rows)):
            for item in rows:
                if not item.model.expanded and set(item.notes) <= wanted:
                    out.append(self._anchor_of(view, item))
        return out[:MAX_PREVIEW]

    def _autoscroll(self, at: QPointF) -> None:
        """Курсор у верхнего/нижнего края сцены (или за ним) — прокрутить её; быстрее, чем ближе к краю.
        Пул не прокручивается никогда: в него не бросают, а строка, которую тащат, не должна уезжать из-под курсора
        (кабель начинается у края пула — прокрутка там двигала бы все строки пула)."""
        for view in (self.view,):
            vp = view.viewport()
            top_left = vp.mapTo(self, QPoint(0, 0))
            if not top_left.x() <= at.x() <= top_left.x() + vp.width():
                continue
            top, bottom = top_left.y(), top_left.y() + vp.height()
            if at.y() < top + EDGE:
                depth = top + EDGE - at.y()
                step = -1
            elif at.y() > bottom - EDGE:
                depth = at.y() - (bottom - EDGE)
                step = 1
            else:
                continue
            bar = view.verticalScrollBar()
            bar.setValue(bar.value() + step * max(1, min(SCROLL_MAX, round(depth / EDGE * SCROLL_MAX))))

    # --- Write to ---

    def _scene_point(self, at: QPointF) -> QPointF:
        """Точка CableEditor -> координаты сцены."""
        return self.view.mapToScene(self.view.viewport().mapFrom(self, at.toPoint()))

    def _global(self, at: QPointF) -> QPoint:
        return self.mapToGlobal(at.toPoint())

    def pick_destination(self, t: TargetRow, at: QPoint) -> int | None:
        """Меню ВСЕХ нот артикуляции (номер, высота; текущий Write to отмечен, как в меню Write to): куда пойдёт
        кабель. Write to не меняется. None — Esc или клик мимо."""
        return self._notes_menu("Connect to", t, at)

    def _destination_menu(self, notes: list[int], t: TargetRow, at: QPoint) -> None:
        n = self.pick_destination(t, at)
        if n is not None:
            self.note_drop_requested.emit(notes, n)

    def pick_write_to(self, t: TargetRow, at: QPoint) -> int | None:
        """Меню нот артикуляции (номер, высота), текущий Write to отмечен. None — ничего не выбрали."""
        return self._notes_menu("Write to", t, at)

    def notes_menu(self, title: str, t: TargetRow) -> QMenu:
        """Меню нот артикуляции t (номера) под заголовком title; текущий Write to отмечен галочкой.
        Общее для «Write to» (клик по бейджу) и «Connect to» (drop на бейдж)."""
        menu = QMenu(self)
        menu.addSection(title)
        for n in t.notes:
            action = menu.addAction(str(n))
            action.setCheckable(True)
            action.setChecked(n == t.write_to)
            action.setData(n)
        return menu

    def _notes_menu(self, title: str, t: TargetRow, at: QPoint) -> int | None:
        chosen = self.notes_menu(title, t).exec(at)
        return chosen.data() if chosen is not None and chosen.data() is not None else None

    def _write_to_menu(self, t: TargetRow, at: QPoint) -> None:
        n = self.pick_write_to(t, at)
        if n is not None and n != t.write_to:
            self.write_to_requested.emit(n)

    # --- построение ---

    def _build(self, *, pool: bool = True, scene: bool = True, anchor: bool = True) -> None:
        """Раскладка заново; pool / scene — какие колонки перерисовать; anchor — удержать прокрутку за якорь."""
        p = self.profile
        self.shown = p.oriented(self.direction) if p is not None else None
        self._init_target_groups()
        lay = build_layout(self.shown, self.collapsed, show_all=self.show_all, expanded=self.expanded,
                           suggested=self.suggested)
        if self.current is not None:  # нетронутая колонка остаётся как есть
            if not pool:
                lay.pool = self.current.pool
            if not scene:
                lay.scene = self.current.scene
        anchors = {v: self._anchors(v) if anchor else [] for v in (self.pool, self.view)}
        self.current = lay
        self._issues = {}
        if p is not None:
            for i in validate_profile(p, self.direction):
                if i.code != NO_RULE:
                    self._issues.setdefault(i.note, []).append(i.message[:1].upper() + i.message[1:])
        if self._drag is not None and self._drag.hover is not None:
            self._drag.hover = None  # элементы сейчас пересоздадутся
        if pool:
            self._draw_pool()
            self._restore_anchor(self.pool, anchors[self.pool])
        if scene:
            self._draw_scene()
            self._restore_anchor(self.view, anchors[self.view])
        visible = {n for item in self.pool_rows + self.scene_rows for n in item.notes}
        self.set_selection(self.selection & visible)

    def _init_target_groups(self) -> None:
        """Группам цели, которых вид ещё не показывал, — начальный режим (initial_show_all); уже виденные не
        трогаются: режим группы меняет только пользователь (клик по заголовку, пружина при перетаскивании)."""
        state = self._state[self.direction]
        new = set(target_group_keys(self.shown)) - state.seen
        if new:
            state.seen |= new
            state.show_all |= new & initial_show_all(self.shown)

    # --- якорь прокрутки ---

    def _anchor_items(self, view: _ColumnView) -> list[tuple[tuple, QRectF]]:
        """Элементы, за которые держится прокрутка view (ключ, прямоугольник): в пуле — строки и заголовки групп,
        в сцене — строки и заголовки цели (подключённые строки при правках переезжают, цели — нет)."""
        if view is self.pool:
            rows = [(("a", i.model.alias) if i.model.expanded else ("n", i.notes[0]), i.rect) for i in self.pool_rows]
            return rows + [(("h", k), i.rect) for k, i in self.pool_headers.items()]
        return ([(("t", k), i.rect) for k, i in self.target_items.items()]
                + [(("h", k), i.rect) for k, i in self.scene_headers.items()])

    def _anchors(self, view: _ColumnView) -> list[tuple[tuple, float]]:
        """Якоря: элемент под курсором (или верхний видимый) и следующие за ним — ключ и смещение от верха
        видимой части. После перестройки берётся первый уцелевший (строка могла уйти из пула). Курсор не над
        колонкой и она в самом верху — якоря нет: колонка остаётся вверху (первые строки не уезжают за край)."""
        items = sorted(self._anchor_items(view), key=lambda kr: kr[1].top())
        if not items:
            return []
        top = view.verticalScrollBar().value()
        vp = view.viewport()
        cursor = vp.mapFromGlobal(QCursor.pos())
        if not vp.rect().contains(cursor) and top == 0:
            return []  # курсор не здесь, а колонку не прокручивали — она и остаётся в самом верху
        y = view.mapToScene(cursor).y() if vp.rect().contains(cursor) else top
        start = next((i for i, (_, r) in enumerate(items) if r.bottom() > y), len(items))
        return [(k, r.top() - top) for k, r in items[start:]]

    def _restore_anchor(self, view: _ColumnView, anchors: list[tuple[tuple, float]]) -> None:
        if not anchors:
            return
        now = dict(self._anchor_items(view))
        for key, offset in anchors:
            if key in now:
                view.verticalScrollBar().setValue(round(now[key].top() - offset))
                return

    def _draw_pool(self) -> None:
        lay = self.current
        self.pool_items, self.pool_rows, self.pool_headers = {}, [], {}
        side = self.sides[0]
        self.pool_title.setToolTip(POOL_TIP.format(side=side.capitalize()))
        if lay is None:
            self.pool.scene().clear()
            return
        view = self.pool
        self.pool_ruler = Ruler(lay.pool.height, (h.y for h in lay.pool.headers), POOL_ROWS)
        view.begin()
        scene = view.scene()
        for h in lay.pool.headers:
            text = ("Click to expand" if h.collapsed else "Click to collapse") + f"\n{GROUP_HINT}"
            item = _HeaderItem(h, self.toggle_pool, text, "pool")
            self.pool_headers[h.key] = item
            scene.addItem(item)
        for r in lay.pool.rows:
            item = self._source_item(QRectF(), r, POOL)
            self._register(item, self.pool_items, self.pool_rows)
            scene.addItem(item)
        self._place_pool()
        view.end()

    def _place_pool(self) -> None:
        """Места строк и заголовков пула по ширине view (при смене ширины элементы не пересоздаются)."""
        view, ruler = self.pool, self.pool_ruler
        view.fit(ruler.total)
        col = view.width_px() - 2 * PAD
        for item in self.pool_headers.values():
            item.set_geometry(QRectF(PAD, PAD + ruler.top(item.header.y), col, POOL_ROWS.head))
            self._full_label(item)
        for item in self.pool_rows:
            r = item.model
            indent = INDENT if r.child else 0
            item.set_rect(QRectF(PAD + indent, PAD + ruler.top(r.y) - POOL_ROWS.inset, col - indent, POOL_ROWS.pitch))
            self._full_name(item)

    def _reflow_pool(self) -> None:
        """Ширина пула поменялась: те же элементы на новых местах."""
        if self.current is None:
            self._draw_pool()
        else:
            self._place_pool()

    @staticmethod
    def _register(item: _Row, by_note: dict[int, _Row], rows: list[_Row]) -> None:
        rows.append(item)
        if item.model.expanded:  # заголовок алиасов: ноты закреплены за их собственными строками ниже
            for n in item.notes:
                by_note.setdefault(n, item)
        else:
            for n in item.notes:
                by_note[n] = item

    # --- колонки сцены ---

    def _scene_columns(self) -> tuple[float, float, float, float]:
        """x колонки «from», x колонки «to», ширины колонок «from» и «to»: по ширине сцены (`scene_columns()`)."""
        x_from, x_to, w_from, w_to = scene_columns(self.view.width_px() - 2 * PAD)
        return PAD + x_from, PAD + x_to, w_from, w_to

    # --- полные имена в подсказках ---

    @staticmethod
    def _full_name(item: _Row) -> None:
        """Имя не помещается в строку — полное имя первой строкой подсказки (у раскрытой цели — заголовка). Повторный
        вызов (новая ширина) начинает с подсказок без имени."""
        if item.base_tips is None:
            item.base_tips = (item.tip_text, item.part_tips.get("head"))
        base, head = item.base_tips
        cut = bool(item.name) and plates.name_width(item.name, item.italic) > item.name_room()
        if item.expanded:
            item.part_tips["head"] = with_name(item.name, head) if cut else head
            if item._part in (None, "head"):
                item.set_tip(item.part_tips["head"])
        else:
            text = with_name(item.name, base) if cut else base
            if text != item.tip_text:
                item.set_tip(text)

    @staticmethod
    def _full_label(item: _HeaderItem) -> None:
        text = f"{item.header.label}\n{item.base_tip}" if item.label_width() > item.label_room() else item.base_tip
        if text != item.tip_text:
            item.set_tip(text)

    def _draw_scene(self) -> None:
        """Колонка «from» (подключённые строки, точка справа) и колонка «to» (строки цели, точка слева)."""
        lay = self.current
        self.cable_items, self.source_items, self.scene_rows, self.target_items = [], {}, [], {}
        self.suggestion_items, self.scene_headers = [], {}
        self.hovered = None
        if lay is None:
            self.view.scene().clear()
            self.view.set_hint(None)
            return
        sc = lay.scene
        self.scene_ruler = Ruler(sc.height, (h.y for h in sc.target_headers), SCENE_ROWS)
        self.view.begin()
        scene = self.view.scene()
        self._bundles = []
        for h in sc.target_headers:
            if h.key in self.show_all:
                text = "All articulations shown. Click to show connected only"
            else:
                text = "Connected only. Click to show all articulations"
            if h.shown:
                text = f"{h.shown} of {h.count} connected\n{text}"
            if h.notes:
                text += f"\n{TARGET_GROUP_HINT}"
            item = _HeaderItem(h, self.toggle_target, text, "scene")
            self.scene_headers[h.key] = item
            scene.addItem(item)
        solid = {c.target.slot for c in sc.cables if not c.suggested}
        dashed = {c.target.slot for c in sc.cables if c.suggested} - solid
        for t in sc.target_rows:
            item = self._target_item(QRectF(), t, t.slot in solid | dashed, t.slot in dashed)
            self.target_items[t.slot] = item
            scene.addItem(item)
            if t.expanded:  # рамка от заголовка до последнего номера — как у раскрытых алиасов слева
                last = max(off for off, _ in t.lines)
                self._add_bundle(False, t.y, last + 1)
        for i, r in enumerate(sc.source_rows):
            item = self._source_item(QRectF(), r, SOURCE)
            self._register(item, self.source_items, self.scene_rows)
            scene.addItem(item)
            if r.expanded:
                children = next((k for k, c in enumerate(sc.source_rows[i + 1:]) if not c.child),
                                len(sc.source_rows) - i - 1)
                self._add_bundle(True, r.y, 1 + children)
        rows_by_y = {item.model.y: item for item in self.scene_rows}
        for c in sc.cables:
            text = self._cable_text(c) if c.dst is not None else ""
            item = _CableItem(QPainterPath(), c, self, rows_by_y[c.src_y], self.target_items[c.target.slot], text)
            scene.addItem(item)
            (self.suggestion_items if c.suggested else self.cable_items).append(item)
        self._place_scene()
        self.view.end()

    def _add_bundle(self, left: bool, y: int, h: int) -> None:
        bundle = _Bundle(QRectF())
        self._bundles.append((bundle, left, y, h))
        self.view.scene().addItem(bundle)

    def _place_scene(self) -> None:
        """Места заголовков, строк, рамок и кабелей сцены по ширине view (при смене ширины элементы не
        пересоздаются)."""
        lay = self.current
        sc, m, ruler = lay.scene, SCENE_ROWS, self.scene_ruler
        self.view.fit(ruler.total)
        lx, rx, col2, col3 = self._scene_columns()
        # сцена совсем пуста (ни заголовков, ни строк — иначе подсказка ложится на них) — что делать; пул пуст —
        # подсказывать нечего
        empty = not (sc.source_rows or sc.target_rows or sc.target_headers) and bool(lay.pool.rows or lay.pool.headers)
        self.view.set_hint((lx, col2, EMPTY_HINT.format(side=self.sides[1])) if empty else None)

        def rect(left: bool, y: int, h: int = 1) -> QRectF:
            """Слот строк y..y+h-1 в колонке «from» (left) или «to»."""
            top = ruler.top(y) - m.inset
            return QRectF(lx if left else rx, PAD + top, col2 if left else col3, ruler.bottom(y, h) + m.inset - top)

        for item in self.scene_headers.values():
            y = item.header.y
            head_rect = QRectF(lx, PAD + ruler.top(y), rx + col3 - lx, m.head)
            top, bottom = ruler.head_zone(y)
            item.set_geometry(head_rect, QRectF(lx, PAD + top, head_rect.width(), bottom - top), (lx, rx, col2, col3))
            self._full_label(item)
        for item in self.target_items.values():
            item.set_rect(rect(False, item.model.y, item.model.height))
            self._full_name(item)
        for bundle, left, y, h in self._bundles:
            bundle.set_rect(rect(left, y, h).adjusted(-3, 0, 3, 0))
        for item in self.scene_rows:
            indent = INDENT if item.model.child else 0
            item.set_rect(rect(True, item.model.y).adjusted(indent, 0, 0, 0))
            self._full_name(item)
        for item in self.cable_items + self.suggestion_items:
            a = QPointF(item.src.rect.right(), item.src.line_center())
            b = QPointF(rx, PAD + ruler.top(item.cable.dst_y) + m.plate / 2)  # на свой номер в строке цели
            item.setPath(cable_path(a, b))

    def _reflow_scene(self) -> None:
        """Ширина сцены поменялась: те же элементы на новых местах."""
        if self.current is None:
            self._draw_scene()
        else:
            self._place_scene()

    def _source_item(self, r: QRectF, row: SourceRow, role: str) -> _Row:
        chevron = None
        if row.alias is not None:
            chevron = "fixed" if row.mixed else "expanded" if row.expanded else "collapsed"
        n = row.shown
        cabled = (row.connected or row.suggested) and not row.expanded
        issues = [i for n_ in row.notes for i in self._issues.get(n_, [])]
        # раскрытые алиасы: у заголовка — только имя, у строк нот — только номер (имя — в подсказке)
        return _Row(r, role, row, "" if row.expanded else str(n), "" if row.child else row.name or "—",
                    dim=row.state == DELETE or row.name is None,
                    strike=row.state == DELETE, marker="=" if row.state == KEEP else "",
                    pill=f"+{len(row.notes) - 1}" if len(row.notes) > 1 and not row.expanded else "",
                    chevron=chevron, port="right" if cabled else None,
                    dashed=row.suggested, warn=bool(issues), tooltip=self._source_text(row, issues),
                    metrics=POOL_ROWS if role == POOL else SCENE_ROWS)

    def _source_text(self, row: SourceRow, issues: list[str]) -> str:
        """Подсказка строки слева: ноты (у строки ноты под заголовком алиасов — и имя), куда идёт, замечания, действие."""
        p = self.shown
        tgt = p.target_map
        head = note_tip(row.notes)
        if row.child and row.name:
            head = f"{head} · {row.name}"
        details: list[str] = list(issues)
        action = ""
        if row.expanded:
            details += [MIXED_TIP] if row.mixed else []
        elif row.connected:
            dst = p.rules[row.note].dst
            dst_name = tgt.names.get(dst, "") if tgt is not None else ""
            head = f"{head}  →  {dst} {dst_name}".rstrip()
            details.append(self._not_write_to(dst))
            action = REMOVE_ACTION
        elif row.suggested:
            cable = next(c for c in self.current.scene.cables if c.src_y == row.y)
            if cable.dst is not None:
                head = f"{head}  →  {cable.dst} {cable.target.label}".rstrip()
                details.append(SUGGESTED_HINT)
            else:
                head = f"{head}  →  {cable.target.label}"
                details.append(SUGGESTED_WRITE_TO_HINT)
        elif row.state == DELETE:
            details.append(DELETED_TIP)
            action = RESTORE_ACTION
        else:
            if row.state == KEEP:
                where = (f": {tgt.names[row.note]}" if tgt is not None and row.note in tgt.names
                         else f" (not in the {self.sides[1]} map)")
                details.append(KEPT_TIP + where)
            elif self.direction == REVERSE and row.state == UNASSIGNED:
                details.append(REVERSE_UNASSIGNED_TIP)
            elif row.state == MIXED:
                details.append(MIXED_TIP)
            action = DELETE_ACTION
            if row.block == UNASSIGNED:
                action += f" · {SAME_NUMBER_HINT}"
        details.append(self._hand_text(row.notes, connected=row.connected and not row.suggested and not row.expanded))
        return tip_lines(head, details, action)

    def _target_item(self, r: QRectF, t: TargetRow, connected: bool, dashed: bool = False) -> _Row:
        port = "left" if connected else None
        if not t.in_map:
            side = f"{self.sides[1]} map"
            text = tip_lines(note_tip(t.notes), [f"Not in the {side}" if self.shown.target_map is not None
                                                 else f"No {side}"])
            item = _Row(r, TARGET, t, "" if t.expanded else str(t.notes[0]), "—", dim=True,
                        italic=True, port=port, dashed=dashed, tooltip=text, metrics=SCENE_ROWS)
            item.part_tips = {"head": text, t.notes[0]: text}
            return item
        many = len(t.notes) > 1
        pill = (f"+{t.hidden}" if t.hidden else "…") if many else ""
        details = []
        if many:
            wt = WRITE_TO_TIP.format(n=t.write_to) if t.write_to is not None else NO_WRITE_TO_TIP
            details = [f"{wt} · {BADGE_HINT.format(pill=pill)}"]
        text = tip_lines(note_tip(t.notes), details)
        item = _Row(r, TARGET, t, "" if t.expanded else str(t.numbers[0][1]), t.label, pill=pill, badge=many,
                    port=port, dashed=dashed, tooltip=text, metrics=SCENE_ROWS)
        if t.expanded:  # плашки номеров: номер, высота и имя (на плашке имени нет)
            item.part_tips = {"head": text}
            for _off, n in t.numbers:
                item.part_tips[n] = tip_lines(f"{note_tip([n])} · {t.label}", ["Write to" if n == t.write_to else ""])
        return item

    def _hand_text(self, notes: tuple[int, ...], connected: bool) -> str:
        """← : пометка «ручная правка» — по `reverse_overrides` прямого профиля (в → ничего не меняется)."""
        if self.direction != REVERSE or self.profile is None:
            return ""
        over = self.profile.reverse_overrides
        if connected:
            hand = [n for n in notes if over.get(n) is not None]
            if not hand:
                return ""
            return HAND_SET_TIP if len(notes) == 1 else HAND_SET_SOME_TIP.format(notes=", ".join(map(str, hand)))
        gone = [n for n in notes if n in over and over[n] is None]
        if not gone:
            return ""
        return HAND_REMOVED_TIP if len(notes) == 1 else HAND_REMOVED_SOME_TIP.format(notes=", ".join(map(str, gone)))

    def _not_write_to(self, dst: int) -> str:
        """Кабель идёт не на Write to своей артикуляции — замечание."""
        tgt = self.shown.target_map
        if tgt is None or dst not in tgt.names:
            return ""
        wt = primary_note(tgt, tgt.names[dst])
        return NOT_WRITE_TO_TIP.format(n=wt) if wt is not None and wt != dst else ""

    def _cable_text(self, c: Cable) -> str:
        """Кабель: «ноты имя  →  нота имя» по ориентированному профилю (как на картинке — слева направо), замечания
        (имена разные, не Write to, ручная правка), действие."""
        p = self.shown
        src_name = p.source_map.names.get(c.notes[0], "") if p.source_map is not None else ""
        tgt = p.target_map
        dst_name = tgt.names.get(c.dst, "") if tgt is not None else ""
        left = f"{', '.join(map(str, c.notes))} {src_name}".strip()
        right = f"{c.dst} {dst_name}".strip()
        details = [NAMES_DIFFER_TIP if names_differ(p, c.notes[0], c.dst) else "", self._not_write_to(c.dst),
                   self._hand_text(c.notes, connected=True)]
        return tip_lines(f"{left}  →  {right}", details, REMOVE_ACTION)
