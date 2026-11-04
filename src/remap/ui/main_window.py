"""Главное окно REMAP на PySide6: корпус, шапка, вкладки Convert (ui/convert_page.py), Profiles
(ui/profiles_page.py) и Maps (ui/maps_page.py), обучение Profiles и закрытие окна с несохранёнными правками.

Запуск: python -m remap
"""
from __future__ import annotations

import os
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QButtonGroup, QHBoxLayout, QMainWindow, QStackedWidget, QVBoxLayout, QWidget

from ..core import legacy_profile
from ..storage import Storage
from . import theme
from .convert_page import ConvertPage
from .field import FaceSlot
from .keys import HELP, TAB, Key, key_margins, key_row_spacing
from .maps_page import MapsPage
from .metal import MetalBody
from .profiles_page import ProfilesPage
from .settings import ui_settings
from .shell import BrandBlock
from .theme import install_app_font, load_fonts, stylesheet
from .tips import tip
from .tutorial import TutorialOverlay, profiles_resolver

PAGE_CONVERT, PAGE_PROFILES, PAGE_MAPS = 0, 1, 2

TUTORIAL_KEY = "tutorial/profiles"  # ui.ini: обучение Profiles уже показано (при первом заходе на вкладку)
NO_TUTORIAL_ENV = "REMAP_NO_TUTORIAL"  # не показывать обучение само (тесты)


class _ToConvertPage:  # TEMP: removed in 5.5
    """Атрибут окна, который читается и пишется в `convert_page` (старые тесты обращаются к окну)."""

    def __init__(self, name: str) -> None:
        self.name = name

    def __get__(self, obj, owner=None):
        return self if obj is None else getattr(obj.convert_page, self.name)

    def __set__(self, obj, value) -> None:
        setattr(obj.convert_page, self.name, value)


_CONVERT_PROXIES = (  # TEMP: removed in 5.5 — состояние и действия Convert живут в `convert_page`, тесты переедут туда
    "sources", "outputs", "results", "output_dir", "source", "output", "out_card", "status", "profile_combo",
    "convert_btn", "copy_btn", "_convert_shortcuts", "load", "convert",
    "copy_output", "paste_file", "remove_source", "_accept_files", "choose_file", "choose_output_folder",
    "ask_output_folder", "set_output_dir", "details_dialog", "selected_profile", "reveal_in_explorer", "show_error",
    "reload_profiles", "set_status", "direction", "direction_btn",
)


class MainWindow(QMainWindow):
    def __init__(self, storage: Storage | None = None) -> None:
        super().__init__()
        self.storage = storage if storage is not None else Storage()
        self.settings = ui_settings(self.storage)
        seed_error = ""
        self._tutorial_scroll = 0  # прокрутка сцены Profiles до обучения
        try:  # первый запуск: схема первой версии — обычный профиль (удалённый не вернётся)
            self.storage.seed_profiles([legacy_profile()])
        except OSError as e:
            seed_error = f"Cannot create the profiles folder: {e}"

        self.setWindowTitle("REMAP")
        self.setMinimumSize(900, 580)
        self._default_size()
        self.setAcceptDrops(True)
        self.setStyleSheet(stylesheet())
        self._build_ui()
        if seed_error:
            self.convert_page.set_status(seed_error, "error")

    def _default_size(self) -> None:
        """900×800, но не больше 90 % доступной области экрана (и не меньше минимального размера)."""
        width, height = theme.WINDOW_SIZE
        screen = self.screen() or QApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            width, height = min(width, int(area.width() * 0.9)), min(height, int(area.height() * 0.9))
        self.resize(max(width, self.minimumWidth()), max(height, self.minimumHeight()))

    # --- построение UI ---

    def _build_ui(self) -> None:
        central = MetalBody()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.nav_convert = Key("Convert", "tab-convert", spec=TAB, checkable=True)
        self.nav_profiles = Key("Profiles", "tab-profiles", spec=TAB, checkable=True)
        self.nav_maps = Key("Maps", "tab-maps", spec=TAB, checkable=True)
        head = QHBoxLayout()
        head.setContentsMargins(theme.HEADER_PAD_X, 0, theme.HEADER_PAD_X - key_margins(TAB).right(), 0)  # лицо — в 40 px от края
        head.setSpacing(key_row_spacing(theme.KEY_TAB_GAP))
        head.addWidget(BrandBlock())
        head.addStretch(1)
        self.help_btn = Key("?", spec=HELP)
        self.help_btn.setToolTip(tip("Show the tutorial"))
        self.help_btn.clicked.connect(self.start_tutorial)
        policy = self.help_btn.sizePolicy()
        policy.setRetainSizeWhenHidden(True)  # скрытая «?» не сдвигает шапку
        self.help_btn.setSizePolicy(policy)
        self.help_btn.setVisible(False)  # открыта Convert
        head.addWidget(FaceSlot(self.help_btn, theme.HEADER_H - theme.RECESS_EDGE_TOP))
        head.addSpacing(theme.HELP_GAP - key_margins(HELP).right() - key_margins(TAB).left() - head.spacing())
        self.nav_group = QButtonGroup(self)  # клавиши лежат в разных контейнерах: взаимное исключение — через группу
        for i, b in enumerate((self.nav_convert, self.nav_profiles, self.nav_maps)):
            self.nav_group.addButton(b, i)
            b.clicked.connect(lambda _=False, page=i: self.show_page(page))
            head.addWidget(FaceSlot(b, theme.HEADER_H - theme.RECESS_EDGE_TOP))
        self.nav_convert.setChecked(True)
        header = QWidget()
        header.setFixedHeight(theme.HEADER_H - theme.RECESS_EDGE_TOP)  # страница начинается на линию выше: лицо блока — ровно на 64-м px
        header.setLayout(head)
        root.addWidget(header)

        self.pages = QStackedWidget()
        root.addWidget(self.pages, stretch=1)
        self.convert_page = ConvertPage(self.storage, self.settings)
        self.pages.addWidget(self.convert_page)
        self.profiles_page = ProfilesPage(self.storage)
        self.profiles_page.profiles_changed.connect(self.convert_page.reload_profiles)
        self.pages.addWidget(self.profiles_page)
        self.maps_page = MapsPage(self.storage)
        self.pages.addWidget(self.maps_page)
        self.setCentralWidget(central)
        self.tutorial = TutorialOverlay(central, profiles_resolver(self))
        self.tutorial.finished.connect(self._tutorial_finished)


    # --- вкладки ---

    def show_page(self, page: int) -> None:
        """Переключение вкладок. Несохранённые правки карты и профиля при этом не теряются."""
        self.pages.setCurrentIndex(page)
        (self.nav_convert, self.nav_profiles, self.nav_maps)[page].setChecked(True)
        self.convert_page.set_shortcuts_enabled(page == PAGE_CONVERT)
        self.help_btn.setVisible(page == PAGE_PROFILES)  # обучение есть только у Profiles: на других вкладках «?» нет
        if (page == PAGE_PROFILES and self.isVisible() and not os.environ.get(NO_TUTORIAL_ENV)
                and not self.settings.value(TUTORIAL_KEY, False, type=bool)):
            QTimer.singleShot(0, self.start_tutorial)  # первый заход на вкладку: после раскладки страницы

    # --- обучение ---

    def start_tutorial(self) -> None:
        if self.pages.currentIndex() != PAGE_PROFILES or self.tutorial.isVisible():
            return
        self._tutorial_scroll = self.profiles_page.cables.view.verticalScrollBar().value()
        self.tutorial.start()

    def _tutorial_finished(self) -> None:
        """Обучение закрыто: прокрутка сцены — как до него (шаг REMOVE CABLES мог её сдвинуть), больше само не
        показывается."""
        self.profiles_page.cables.view.verticalScrollBar().setValue(self._tutorial_scroll)
        self.settings.setValue(TUTORIAL_KEY, True)

    def closeEvent(self, event) -> None:
        for page_index, page in ((PAGE_PROFILES, self.profiles_page), (PAGE_MAPS, self.maps_page)):
            if page.dirty:
                self.show_page(page_index)
                if not page.maybe_leave():
                    event.ignore()
                    return
        super().closeEvent(event)


    # --- DnD внутрь окна: файлы принимает Convert с любой вкладки ---

    def dragEnterEvent(self, event) -> None:
        self.convert_page.drag_enter(event)

    def dragLeaveEvent(self, event) -> None:
        self.convert_page.drag_leave()

    def dropEvent(self, event) -> None:
        if self.convert_page.drop_files(event):
            self.show_page(PAGE_CONVERT)


for _name in _CONVERT_PROXIES:  # TEMP: removed in 5.5
    setattr(MainWindow, _name, _ToConvertPage(_name))


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("REMAP")
    load_fonts()  # до стилей: они берут имена семейств
    install_app_font()
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
