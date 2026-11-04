"""Полоса профиля: каркас `StripFrame` (блок 836×64 с панелью). Слева — профиль, «…» и сохранение, справа — исходная карта,
«⇄» и целевая. Только виджеты и размеры из макета; логику (сигналы, подсказки, меню) подключает страница."""

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QHBoxLayout, QMenu, QWidget

from . import theme
from .combo import ComboBox
from .field import FaceSlot, row_spacing
from .keys import SQUARE, SWAP, Key, key_margins, key_row_spacing
from .strip import SLOT_H, StripFrame, StripSeparator


class MapCombo(ComboBox):
    """Поле «подпись + карта ▾»: лицо и текст рисует `ComboBox`, а вместо списка открывается меню выбора карты
    (кнопка с меню прежней страницы: `setMenu()` / `menu()` / `setText()` / `text()`)."""

    def __init__(self, caption: str, parent: QWidget | None = None) -> None:
        super().__init__(parent, caption=caption)
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
        super().__init__(parent)
        self.combo = ComboBox()
        self.dots_btn = Key(icon="dots", spec=SQUARE)
        self.save_btn = Key(icon="save", spec=SQUARE)
        self.from_btn = MapCombo("SOURCE")
        self.to_btn = MapCombo("TARGET")
        self.direction_btn = Key(icon="swap", spec=SWAP)
        slot = SLOT_H

        km, fm = key_margins(SQUARE), self.combo.margins()
        left = QWidget()
        lay = QHBoxLayout(left)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(FaceSlot(self.combo, slot), 1)
        lay.addSpacing(row_spacing(theme.STRIP_GAP_KEYS, self.combo, self.dots_btn))
        lay.addWidget(FaceSlot(self.dots_btn, slot))
        lay.addSpacing(key_row_spacing(theme.STRIP_GAP_KEYS, SQUARE))
        lay.addWidget(FaceSlot(self.save_btn, slot))
        left.setFixedWidth(theme.STRIP_LEFT_W + fm.left() + km.right())

        right = QWidget()
        rlay = QHBoxLayout(right)
        rlay.setContentsMargins(0, 0, 0, 0)
        rlay.setSpacing(0)
        for w in (self.from_btn, self.to_btn):
            w.setFixedWidth(theme.COL_FROM + w.margins().left() + w.margins().right())
        rlay.addWidget(FaceSlot(self.from_btn, slot))
        rlay.addStretch(1)
        rlay.addWidget(FaceSlot(self.direction_btn, slot))
        rlay.addStretch(1)
        rlay.addWidget(FaceSlot(self.to_btn, slot))
        right.setFixedWidth(theme.STRIP_RIGHT_W + self.from_btn.margins().left() + self.to_btn.margins().right())

        self.set_face_inset(fm.left(), fm.right())
        self.panel.body.addWidget(left)
        self.panel.body.addWidget(StripSeparator(km.right(), self.from_btn.margins().left()))
        self.panel.body.addWidget(right)
        self.panel.body.addStretch(1)

    def set_actions_menu(self, menu: QMenu) -> None:
        """Меню «…»: открывается по нажатию под клавишей."""
        self.dots_btn.clicked.connect(
            lambda: menu.popup(self.dots_btn.mapToGlobal(QPoint(0, self.dots_btn.height()))))
