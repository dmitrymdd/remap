"""Геометрия главного окна между запусками (ui.ini, window/geometry)."""
import pytest
from PySide6.QtCore import QRect

from remap.ui import main_window, theme
from remap.ui.main_window import GEOMETRY_KEY, MainWindow
from remap.ui.maps_page import SIDE_KEY

pytestmark = pytest.mark.ui


AREA = QRect(0, 0, 1920, 1040)


@pytest.fixture(autouse=True)
def screen(monkeypatch):
    """Экран offscreen меньше минимума окна — подставляем 1920×1040."""
    monkeypatch.setattr(main_window, "screen_areas", lambda: [AREA])


def area():
    return AREA


def saved(storage, rect: QRect):
    """Окно с заданной геометрией закрывается — как прошлый запуск."""
    w = MainWindow(storage)
    w.setGeometry(rect)
    w.close()
    return w.settings.value(GEOMETRY_KEY)


def reopen(storage, data=None):
    w = MainWindow(storage)
    if data is not None:
        w.settings.setValue(GEOMETRY_KEY, data)
    w.restore_window_geometry()
    return w


def default_size(w):
    width, height = theme.WINDOW_SIZE
    a = area()
    return min(width, int(a.width() * 0.9)), min(height, int(a.height() * 0.9))


def test_roundtrip(app, storage):
    a = area()
    rect = QRect(a.left() + 20, a.top() + 20, 900, 650)
    assert saved(storage, rect) is not None
    w = reopen(storage)
    assert w.size() == rect.size()  # положение Qt подгоняет под настоящий экран (offscreen — 800×800)


def test_nothing_saved_uses_default_centered(app, storage):
    w = reopen(storage)
    width, height = default_size(w)
    assert (w.width(), w.height()) == (max(width, 900), max(height, 580))
    assert abs(w.frameGeometry().center().x() - area().center().x()) <= 1


def test_off_screen_falls_back(app, storage):
    a = area()
    data = saved(storage, QRect(a.right() + 5000, a.bottom() + 5000, 960, 600))
    w = reopen(storage, data)
    assert a.contains(w.frameGeometry().center())


def test_too_large_falls_back(app, storage):
    a = area()
    data = saved(storage, QRect(a.left(), a.top(), a.width() + 600, a.height() + 600))
    w = reopen(storage, data)
    assert w.width() <= a.width() and w.height() <= a.height()


def test_minimum_size_still_applies(app, storage):
    w = reopen(storage)
    assert w.minimumWidth() == 900 and w.minimumHeight() == 580


def test_side_width_restored_on_wide_window(app, storage):
    a = area()
    width = 1000
    w = MainWindow(storage)
    w.settings.setValue(SIDE_KEY, 420)
    w.setGeometry(QRect(a.left(), a.top(), width, 600))
    w.close()
    again = reopen(storage)
    row = again.maps_page.split
    assert row.saved == 420
    row.resize(1500, 400)
    row._relayout()  # окно не показано: resizeEvent не придёт
    assert row.side_width() == 420 and row.side.width() == 420
