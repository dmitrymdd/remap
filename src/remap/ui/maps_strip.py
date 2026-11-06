"""Полоса Maps на каркасе `StripFrame`: [новая][импорт][экспорт][…] | поле MY MAP / TEMPLATE [Save]. Только виджеты и
размеры из макета; действия, доступность и подсказки подключает страница.

Полоса на всю ширину страницы; ширины секций — над блоками экранов (`set_sections()` по ряду экранов): слева клавиши
прижаты влево, справа поле тянется, Save — у правого края; прорезь 54 — над зазором экранов.

Меню «…»: Duplicate, Rename, Delete, Revert changes (отмены на Maps нет). Save доступна только при правках, точки нет."""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRectF
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QHBoxLayout, QMenu, QWidget

from . import text, theme
from .field import BezelField, FaceSlot, row_spacing
from .icons import ICONS, draw_icon
from .keys import MAP, SQUARE, Key, key_margins, key_row_spacing
from .strip import SLOT_H, StripFrame, StripSeparator

MY_MAP, TEMPLATE_CAPTION = "MY MAP", "TEMPLATE"
LOCK_GAP = 6  # от подписи TEMPLATE до значка замка


class MapField(BezelField):
    """Статическое поле открытой карты: подпись MY MAP / TEMPLATE (у шаблона — с замком) и имя карты."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent=parent, caption=MY_MAP)
        self.locked = False

    def set_map(self, name: str, *, locked: bool) -> None:
        self.locked = locked
        self.set_texts(name, TEMPLATE_CAPTION if locked else MY_MAP)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if not (self.locked and self.value):
            return
        # замок — справа от подписи, по центру её строки (блок подписи и значения — по центру лица, как в paint_field_text)
        spec, content = self._specs.caption, self.content_rect()
        cap_h = text.line_height(spec)
        top = content.center().y() - (cap_h + 1 + text.line_height(self._specs.value)) / 2
        icon = ICONS["lock"]
        x = content.left() + text.text_width(self.caption, spec) + LOCK_GAP
        p = QPainter(self)
        draw_icon(p, "lock", QRectF(x, top + (cap_h - icon.h) / 2, icon.w, icon.h), theme.FIELD_CAPTION)


class MapsStrip(StripFrame):
    """`new_btn`, `import_btn`, `export_btn`, `more_btn` (меню `menu`: `duplicate_action`, `rename_action`,
    `delete_action`, `revert_action`) | `field` | `save_btn`."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, stretch=True)
        self.new_btn = Key(icon="map-new", spec=MAP)
        self.import_btn = Key(icon="map-import", spec=MAP)
        self.export_btn = Key(icon="map-export", spec=MAP)
        self.more_btn = Key(icon="map-more", spec=MAP)
        self.field = MapField()
        self.save_btn = Key(icon="save", spec=SQUARE)

        self.menu = QMenu(self)
        self.duplicate_action = self.menu.addAction("Duplicate")
        self.rename_action = self.menu.addAction("Rename")
        self.delete_action = self.menu.addAction("Delete")
        self.menu.addSeparator()
        self.revert_action = self.menu.addAction("Revert changes")
        self.more_btn.clicked.connect(
            lambda: self.menu.popup(self.more_btn.mapToGlobal(QPoint(0, self.more_btn.height()))))

        km, sm, fm = key_margins(MAP), key_margins(SQUARE), self.field.margins()
        self._left = left = QWidget()
        lay = QHBoxLayout(left)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(key_row_spacing(theme.STRIP_GAP_KEYS, MAP))
        for key in (self.new_btn, self.import_btn, self.export_btn, self.more_btn):
            lay.addWidget(FaceSlot(key, SLOT_H))
        lay.addStretch(1)

        self._right = right = QWidget()
        rlay = QHBoxLayout(right)
        rlay.setContentsMargins(0, 0, 0, 0)
        rlay.setSpacing(0)
        rlay.addWidget(FaceSlot(self.field, SLOT_H), 1)
        rlay.addSpacing(row_spacing(theme.STRIP_GAP_KEYS, self.field, self.save_btn))
        rlay.addWidget(FaceSlot(self.save_btn, SLOT_H))
        self._extra = (km.left() + km.right(), fm.left() + sm.right())  # поля крайних виджетов секций под тень и обод
        self.set_sections(theme.STRIP_LEFT_W, theme.STRIP_RIGHT_W)

        self.set_face_inset(km.left(), sm.right())
        self.panel.body.addWidget(left)
        self.panel.body.addWidget(StripSeparator(km.right(), fm.left()))
        self.panel.body.addWidget(right)
        self.panel.body.addStretch(1)

    def set_sections(self, left: int, right: int) -> None:
        """Ширины секций от лица первого виджета до лица последнего (`strip.section_width()` блоков экранов)."""
        self._left.setFixedWidth(left + self._extra[0])
        self._right.setFixedWidth(right + self._extra[1])

    def section_widths(self) -> tuple[int, int]:
        return self._left.width() - self._extra[0], self._right.width() - self._extra[1]

    def show_state(self, *, has_map: bool, read_only: bool, dirty: bool) -> None:
        """Доступность: Save и Revert changes — только при правках; Rename и Delete — у своих карт."""
        self.save_btn.setEnabled(dirty)
        self.revert_action.setEnabled(dirty)
        self.export_btn.setEnabled(has_map)
        self.duplicate_action.setEnabled(has_map)
        self.rename_action.setEnabled(has_map and not read_only)
        self.delete_action.setEnabled(has_map and not read_only)
        self.field.setEnabled(has_map)
