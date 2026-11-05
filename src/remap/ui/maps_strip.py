"""Кнопки и надписи управления картой на вкладке Maps (старые виджеты на QSS): действия со списком карт, заголовок
открытой карты с отметками «шаблон» / «старый .txt» и «есть правки», строка статуса, Revert и Save.

Сигналы подключает страница; раскладку она берёт готовой: `actions` — сетка кнопок под списком карт, `head` — строка
над таблицей, `bottom` — строка статуса с Revert и Save."""
from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QPushButton

from .maps_text import NO_MAP_TITLE
from .theme import repolish


class MapsStrip:
    """Виджеты управления картой; родителя им даёт раскладка страницы."""

    def __init__(self) -> None:
        self.new_btn = QPushButton("New")
        self.import_btn = QPushButton("Import .txt…")
        self.duplicate_btn = QPushButton("Duplicate")
        self.rename_btn = QPushButton("Rename")
        self.delete_btn = QPushButton("Delete")
        self.export_btn = QPushButton("Export .txt")
        self.new_btn.setToolTip("Create an empty map")
        self.import_btn.setToolTip("Import a REAPER MIDI note name map (.txt)")
        self.duplicate_btn.setToolTip("Copy the selected map. This is the only way to edit a built-in template")
        self.export_btn.setToolTip("Export the map as it is shown in the editor to a REAPER .txt file")
        self.actions = QGridLayout()
        self.actions.setSpacing(6)
        for i, b in enumerate((self.new_btn, self.import_btn, self.duplicate_btn, self.rename_btn,
                               self.delete_btn, self.export_btn)):
            self.actions.addWidget(b, i // 2, i % 2)

        self.title = QLabel(NO_MAP_TITLE)
        self.title.setObjectName("mapTitle")
        self.kind_chip = QLabel()
        self.kind_chip.setObjectName("chip")
        self.dirty_label = QLabel("● Unsaved changes")
        self.dirty_label.setObjectName("dirty")
        self.edit_copy_btn = QPushButton("Duplicate to edit")
        self.edit_copy_btn.setObjectName("primary")
        self.edit_copy_btn.setToolTip("Built-in templates are read-only. Make your own copy to edit it")
        self.head = QHBoxLayout()
        self.head.addWidget(self.title, stretch=1)
        self.head.addWidget(self.edit_copy_btn)
        self.head.addWidget(self.dirty_label)
        self.head.addWidget(self.kind_chip)

        self.revert_btn = QPushButton("Revert")
        self.save_btn = QPushButton("Save")
        self.save_btn.setObjectName("primary")
        self.status = QLabel()
        self.status.setObjectName("status")
        self.status.setWordWrap(True)
        self.bottom = QHBoxLayout()
        self.bottom.addWidget(self.status, stretch=1)
        self.bottom.addWidget(self.revert_btn)
        self.bottom.addWidget(self.save_btn)

    def show_state(self, *, has_map: bool, read_only: bool, dirty: bool) -> None:
        """Доступность кнопок. У шаблона сохранять нечего: вместо Save/Revert — кнопка «Duplicate to edit»."""
        self.dirty_label.setVisible(dirty)
        self.save_btn.setEnabled(dirty)
        self.revert_btn.setEnabled(dirty)
        self.save_btn.setHidden(read_only)
        self.revert_btn.setHidden(read_only)
        self.edit_copy_btn.setVisible(read_only)
        self.duplicate_btn.setEnabled(has_map)
        self.export_btn.setEnabled(has_map)
        self.rename_btn.setEnabled(has_map and not read_only)
        self.delete_btn.setEnabled(has_map and not read_only)

    def set_kind(self, text: str, tip: str) -> None:
        """Отметка у заголовка («шаблон» / «старый .txt»); пустой текст — скрыта."""
        self.kind_chip.setVisible(bool(text))
        if text:
            self.kind_chip.setText(text)
            self.kind_chip.setToolTip(tip)

    def set_status(self, text: str, state: str = "") -> None:
        self.status.setText(text)
        repolish(self.status, "state", state)

