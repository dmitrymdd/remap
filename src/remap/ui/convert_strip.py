"""Полоса Convert на каркасе `StripFrame`: профиль ▾ | SOURCE ⇄ TARGET | OUTPUT ▾. Только виджеты и размеры из макета;
логику (профили, направление, папка результатов, подсказки) подключает страница.

Полоса на всю ширину страницы; ширины секций — над блоками экранов (`set_sections()` по ряду экранов): слева лишнее
забирает комбо профиля (SOURCE ⇄ TARGET своей ширины), справа тянется поле OUTPUT; прорезь 54 — над зазором экранов."""

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QWidget

from . import theme
from .combo import profile_combo
from .field import BezelField, FaceSlot, row_spacing
from .keys import SQUARE, Key
from .profile_strip import MapCombo
from .strip import SLOT_H, StripFrame, StripSeparator


def _fix_face_width(widget: QWidget, face: int) -> None:
    m = widget.margins()
    widget.setFixedWidth(face + m.left() + m.right())


def _min_face_width(widget: QWidget, face: int) -> None:
    """Лицо не уже `face`, лишнее место секции — ему."""
    m = widget.margins()
    widget.setMinimumWidth(face + m.left() + m.right())
    widget.setSizePolicy(QSizePolicy.Policy.Expanding, widget.sizePolicy().verticalPolicy())


def _row(parent: QWidget | None = None) -> tuple[QWidget, QHBoxLayout]:
    w = QWidget(parent)
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)
    return w, lay


class ConvertStrip(StripFrame):
    """`combo` — профиль; `source_field` / `target_field` — карты направления (статические поля); `direction_btn` — «⇄»;
    `output_btn` — папка результатов (поле с меню, `setMenu()`)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, stretch=True)
        self.combo = profile_combo()
        self.source_field = BezelField(caption="SOURCE", value_px=theme.FIELD_VALUE_FONT,
                                       value_weight=QFont.Weight.Normal)
        self.target_field = BezelField(caption="TARGET", value_px=theme.FIELD_VALUE_FONT,
                                       value_weight=QFont.Weight.Normal)
        self.direction_btn = Key(icon="swap", spec=SQUARE)
        self.output_btn = MapCombo("OUTPUT", value_px=theme.FIELD_VALUE_FONT, value_weight=QFont.Weight.Normal)
        _min_face_width(self.combo, theme.CONVERT_PROFILE_W)
        _fix_face_width(self.source_field, theme.CONVERT_MAP_W)
        _fix_face_width(self.target_field, theme.CONVERT_MAP_W)
        _min_face_width(self.output_btn, theme.CONVERT_OUTPUT_W)

        gap = theme.STRIP_GAP_KEYS
        # левая часть 514: профиль, прорезь на всё свободное место (с зазорами 8 по краям), карты и «⇄»
        maps_w = 2 * theme.CONVERT_MAP_W + SQUARE.w + 2 * gap
        left_sep = theme.CONVERT_LEFT_W - theme.CONVERT_PROFILE_W - maps_w
        cm, tm, om = self.combo.margins(), self.target_field.margins(), self.output_btn.margins()
        self.set_face_inset(cm.left(), om.right())
        self._left, lay = _row()
        lay.addWidget(FaceSlot(self.combo, SLOT_H), 1)
        lay.addWidget(StripSeparator(cm.right(), self.source_field.margins().left(), width=left_sep))
        lay.addWidget(FaceSlot(self.source_field, SLOT_H))
        lay.addSpacing(row_spacing(gap, self.source_field, self.direction_btn))
        lay.addWidget(FaceSlot(self.direction_btn, SLOT_H))
        lay.addSpacing(row_spacing(gap, self.direction_btn, self.target_field))
        lay.addWidget(FaceSlot(self.target_field, SLOT_H))
        self._right, rlay = _row()
        rlay.addWidget(FaceSlot(self.output_btn, SLOT_H), 1)
        self._extra = (cm.left() + tm.right(), om.left() + om.right())  # поля крайних виджетов секций под тень и обод
        self.set_sections(theme.CONVERT_LEFT_W, theme.CONVERT_OUTPUT_W)

        body = self.panel.body
        body.addWidget(self._left)
        body.addWidget(StripSeparator(tm.right(), om.left()))
        body.addWidget(self._right)
        body.addStretch(1)
