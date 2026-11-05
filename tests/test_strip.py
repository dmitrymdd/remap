"""Каркас верхней полосы (`ui/strip.py`): у всех вкладок одна геометрия блока и панели."""
import pytest
from PySide6.QtCore import QPoint, QPointF, QRect
from PySide6.QtWidgets import QApplication

from remap.ui import theme
from remap.ui.main_window import PAGE_CONVERT, PAGE_MAPS, PAGE_PROFILES, MainWindow
from remap.ui.strip import StripFrame

pytestmark = pytest.mark.ui


@pytest.fixture
def window(app, storage):
    w = MainWindow(storage)
    w.resize(900, 800)
    w.show()
    yield w
    w.close()
    w.deleteLater()


def frame_geometry(window, page_index):
    """Блок полосы и панель вкладки в координатах окна."""
    window.show_page(page_index)
    QApplication.processEvents()
    strip = window.pages.widget(page_index).findChild(StripFrame)
    origin = strip.mapTo(window, QPoint(0, 0))
    return QRect(origin, strip.size()), strip.panel.geometry().translated(origin)


def test_profiles_strip_frame_follows_the_mockup(window):
    """Лицо блока 836×64 в (32, 64) (виджет на 1 px выше и на 3 px выше лица под внешние линии), панель — в 6 px."""
    block, panel = frame_geometry(window, PAGE_PROFILES)
    assert block == QRect(theme.PAGE_MARGIN, 63, theme.STRIP_W, theme.STRIP_H + 3)
    assert panel == QRect(32 + 6, 64 + 6, theme.STRIP_W - 12, theme.STRIP_H - 12)


def test_convert_and_maps_strip_frames_equal_profiles(window):
    profiles = frame_geometry(window, PAGE_PROFILES)
    assert frame_geometry(window, PAGE_CONVERT) == profiles
    assert frame_geometry(window, PAGE_MAPS) == profiles


def test_convert_strip_faces_follow_the_mockup(window):
    """Лица по макету: профиль 148 | прорезь | SOURCE 146, ⇄ 38×38, TARGET 146 | прорезь 54 | OUTPUT 226; высота 38,
    по центру панели; от краёв панели — 15 px."""
    window.show_page(PAGE_CONVERT)
    QApplication.processEvents()
    strip = window.convert_page.strip

    def face(widget):
        return widget.face_rect().translated(QPointF(widget.mapTo(window, QPoint(0, 0))))

    faces = [face(w) for w in (strip.combo, strip.source_field, strip.direction_btn, strip.target_field,
                               strip.output_btn)]
    assert [(f.x(), f.width()) for f in faces] == [(53, 148), (221, 146), (375, 38), (421, 146), (621, 226)]
    assert {(f.y(), f.height()) for f in faces} == {(77, 38)}
    assert faces[-1].right() + 15 == 38 + theme.STRIP_W - 12


def test_maps_strip_faces_follow_the_mockup(window):
    """Лица по макету: 4 клавиши 48×38 через 8 в колонке 218 | прорезь 54 | поле MY MAP, 8, Save 38×38 в колонке 522;
    высота 38, по центру панели; Save — в 15 px от правого края панели."""
    window.show_page(PAGE_MAPS)
    QApplication.processEvents()
    strip = window.maps_page.strip

    def face(widget):
        return widget.face_rect().translated(QPointF(widget.mapTo(window, QPoint(0, 0))))

    faces = [face(w) for w in (strip.new_btn, strip.import_btn, strip.export_btn, strip.more_btn, strip.field,
                               strip.save_btn)]
    assert [(f.x(), f.width()) for f in faces] == [(53, 48), (109, 48), (165, 48), (221, 48), (325, 476),
                                                  (809, 38)]
    assert {(f.y(), f.height()) for f in faces} == {(77, 38)}
    assert faces[-1].right() + 15 == 38 + theme.STRIP_W - 12
