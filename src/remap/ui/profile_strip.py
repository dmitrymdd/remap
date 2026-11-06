"""Полоса профиля: каркас `StripFrame` на всю ширину страницы, секции — над блоками пула и сцены (`set_sections()`). Слева — профиль, «…» и сохранение, справа — исходная карта,
«⇄» и целевая. Только виджеты и размеры из макета; логику (сигналы, подсказки, меню) подключает страница."""

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QHBoxLayout, QMenu, QWidget

from . import theme
from .cable_layout import scene_columns
from .combo import ComboBox
from .field import FaceSlot, row_spacing
from .keys import SQUARE, SWAP, Key, key_margins, key_row_spacing
from .strip import SLOT_H, StripFrame, StripSeparator


class MapCombo(ComboBox):
    """Поле «подпись + карта ▾»: лицо и текст рисует `ComboBox`, а вместо списка открывается меню выбора карты
    (кнопка с меню прежней страницы: `setMenu()` / `menu()` / `setText()` / `text()`)."""

    def __init__(self, caption: str, parent: QWidget | None = None, **font) -> None:
        """font — `value_px` / `value_weight` / `wdth` поля (`ComboBox`)."""
        super().__init__(parent, caption=caption, **font)
        self.addItem("")
        self._menu: QMenu | None = None

    def setMenu(self, menu: QMenu) -> None:
        self._menu = menu

    def menu(self) -> QMenu | None:
        return self._menu

    def setText(self, value: str) -> None:
        self.setItemText(0, value)
        self.update()

    def text(self) -> str:
        return self.itemText(0)

    def showPopup(self) -> None:
        if self._menu is None or not self.isEnabled():
            return
        face = self.face_rect()
        self._menu.popup(self.mapToGlobal(QPoint(round(face.left()), round(face.bottom()) + 2)))

    def hidePopup(self) -> None:
        if self._menu is not None:
            self._menu.hide()


class ProfileStrip(StripFrame):
    """Профиль: `combo` + `dots_btn` + `save_btn`; карты: `from_btn` (SOURCE) — `direction_btn` — `to_btn` (TARGET).
    В ← страница меняет подписи полей местами (`set_caption`)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, stretch=True)
        self.combo = ComboBox()
        self.dots_btn = Key(icon="dots", spec=SQUARE)
        self.save_btn = Key(icon="save", spec=SQUARE)
        self.from_btn = MapCombo("SOURCE")
        self.to_btn = MapCombo("TARGET")
        self.direction_btn = Key(icon="swap", spec=SWAP)
        slot = SLOT_H

        km, fm = key_margins(SQUARE), self.combo.margins()
        self._left = left = QWidget()
        lay = QHBoxLayout(left)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(FaceSlot(self.combo, slot), 1)
        lay.addSpacing(row_spacing(theme.STRIP_GAP_KEYS, self.combo, self.dots_btn))
        lay.addWidget(FaceSlot(self.dots_btn, slot))
        lay.addSpacing(key_row_spacing(theme.STRIP_GAP_KEYS, SQUARE))
        lay.addWidget(FaceSlot(self.save_btn, slot))

        self._right = right = QWidget()
        rlay = QHBoxLayout(right)
        rlay.setContentsMargins(0, 0, 0, 0)
        rlay.setSpacing(0)
        rlay.addWidget(FaceSlot(self.from_btn, slot))
        rlay.addStretch(1)
        rlay.addWidget(FaceSlot(self.direction_btn, slot))
        rlay.addStretch(1)
        rlay.addWidget(FaceSlot(self.to_btn, slot))
        self._extra = (fm.left() + km.right(), self.from_btn.margins().left() + self.to_btn.margins().right())
        self.set_sections(theme.STRIP_LEFT_W, theme.STRIP_RIGHT_W)

        self.set_face_inset(fm.left(), fm.right())
        self.panel.body.addWidget(left)
        self.panel.body.addWidget(StripSeparator(km.right(), self.from_btn.margins().left()))
        self.panel.body.addWidget(right)
        self.panel.body.addStretch(1)

    def set_sections(self, left: int, right: int) -> None:
        """Ширины секций от лица первого виджета до лица последнего (`strip.section_width()` блоков экранов): слева
        лишнее забирает комбо профиля, справа SOURCE / TARGET — над колонками сцены (`scene_columns(right)`), ⇄ — по
        центру промежутка."""
        _x_from, _x_to, w_from, w_to = scene_columns(right)
        for w, width in ((self.from_btn, w_from), (self.to_btn, w_to)):
            w.setFixedWidth(round(width) + w.margins().left() + w.margins().right())
        self._left.setFixedWidth(left + self._extra[0])
        self._right.setFixedWidth(right + self._extra[1])
        # сразу, изнутри наружу, а не по отложенному LayoutRequest: полоса идёт вслед за ручкой ряда
        for w in (self.from_btn.parentWidget(), self.to_btn.parentWidget(), self._right, self.panel):
            w.layout().activate()

    def section_widths(self) -> tuple[int, int]:
        return self._left.width() - self._extra[0], self._right.width() - self._extra[1]

    def set_actions_menu(self, menu: QMenu) -> None:
        """Меню «…»: открывается по нажатию под клавишей."""
        self.dots_btn.clicked.connect(
            lambda: menu.popup(self.dots_btn.mapToGlobal(QPoint(0, self.dots_btn.height()))))
