"""Maps в ряду SplitRow: список карт — боковая колонка слева, таблица нот забирает лишнюю ширину, секции полосы — над
блоками экранов, прорезь — над зазором."""
import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from remap.ui import theme
from remap.ui.keys import MAP, key_margins
from remap.ui.main_window import PAGE_MAPS
from remap.ui.maps_page import SIDE_KEY
from remap.ui.settings import ui_settings
from remap.ui.strip import StripSeparator
from conftest import open_window

pytestmark = pytest.mark.ui

WIDE = 1600


@pytest.fixture
def window(app, storage):
    w = open_window(storage, PAGE_MAPS, theme.WINDOW_SIZE[0])
    yield w
    w.close()
    w.deleteLater()


def rect(window, widget):
    return QRect(widget.mapTo(window, QPoint(0, 0)), widget.size())


def resize(window, width):
    window.resize(width, theme.WINDOW_SIZE[1])
    QApplication.processEvents()


def faces(window):
    """Секции полосы (лицо первого виджета … лицо последнего) и прорезь в координатах окна: (x, ширина)."""
    strip = window.maps_page.strip

    def face(w):
        return w.face_rect().translated(w.mapTo(window, QPoint(0, 0)).toPointF())

    first, last, field, save = face(strip.new_btn), face(strip.more_btn), face(strip.field), face(strip.save_btn)
    sep_x = rect(window, strip.findChild(StripSeparator)).x() - key_margins(MAP).right()  # прорезь — между лицами
    assert last.right() <= sep_x  # клавиши прижаты влево, остаток секции пуст
    return (first.x(), sep_x - first.x()), (field.x(), save.right() - field.x()), (sep_x, theme.STRIP_SEP_W)


def drag(page, dx):
    handle = page.split.handle
    start = QPoint(handle.width() // 2, handle.height() // 2)
    QTest.mousePress(handle, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    QTest.mouseMove(handle, start + QPoint(dx, 0))
    QTest.mouseRelease(handle, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start + QPoint(dx, 0))
    QApplication.processEvents()


def check_strip_over_blocks(window):
    """Секции = блоки экранов − 2 × 21, прорезь 54 — по центру зазора 12 px."""
    page = window.maps_page
    lst, notes, handle = rect(window, page.list), rect(window, page.notes), rect(window, page.split.handle)
    left, right, sep = faces(window)
    assert left == (lst.x() + theme.STRIP_INSET, lst.width() - 2 * theme.STRIP_INSET)
    assert right == (notes.x() + theme.STRIP_INSET, notes.width() - 2 * theme.STRIP_INSET)
    assert page.strip.section_widths() == (left[1], right[1])
    assert handle.width() == theme.SCREEN_GAP
    assert sep[0] + sep[1] / 2 == handle.x() + handle.width() / 2
    assert left[0] + left[1] == sep[0] and sep[0] + sep[1] == right[0]


def test_strip_sections_at_900_follow_the_mockup(window):
    page = window.maps_page
    assert page.strip.section_widths() == (theme.STRIP_LEFT_W, theme.STRIP_RIGHT_W) == (218, 522)
    assert rect(window, page.strip).width() == theme.STRIP_W
    assert (page.list.width(), page.notes.width()) == (theme.POOL_W, theme.SCENE_W)
    check_strip_over_blocks(window)


def test_wide_window_gives_the_rest_to_notes(window):
    resize(window, WIDE)
    page = window.maps_page
    row_w = WIDE - 2 * theme.PAGE_MARGIN
    assert rect(window, page.strip) == QRect(theme.PAGE_MARGIN, 63, row_w, theme.STRIP_H + 3)
    assert page.list.width() == theme.POOL_W
    assert page.notes.width() == row_w - theme.SCREEN_GAP - theme.POOL_W
    check_strip_over_blocks(window)
    # Save — у правого края панели, поле тянется
    strip = page.strip
    save = strip.save_btn.face_rect().translated(strip.save_btn.mapTo(window, QPoint(0, 0)).toPointF())
    assert save.right() + theme.STRIP_PAD_X == theme.PAGE_MARGIN + row_w - theme.RECESS_PAD
    assert strip.field.face_rect().width() > 476


def test_wide_window_screws_in_corners_and_tabs_at_right(window):
    resize(window, WIDE)
    body = window.centralWidget()
    corners = {(s.x(), s.y()) for s in body.screws}
    far_x = WIDE - theme.SCREW_INSET - theme.SCREW_SIZE
    assert {x for x, _ in corners} == {theme.SCREW_INSET, far_x}
    tab = rect(window, window.nav_maps)
    assert tab.right() > WIDE - 100  # вкладки прижаты вправо


def test_dragging_handle_moves_strip_slot(window):
    resize(window, WIDE)
    page = window.maps_page
    drag(page, 150)
    assert page.list.width() == theme.POOL_W + 150
    check_strip_over_blocks(window)
    drag(page, -400)  # уже макета нельзя
    assert page.list.width() == theme.POOL_W
    check_strip_over_blocks(window)


def test_saved_width_restored_after_narrow_then_wide(app, storage):
    w = open_window(storage, PAGE_MAPS, WIDE)
    try:
        drag(w.maps_page, 200)
        assert ui_settings(storage).value(SIDE_KEY, type=int) == theme.POOL_W + 200
        resize(w, theme.WINDOW_SIZE[0])
        assert w.maps_page.list.width() == theme.POOL_W
        check_strip_over_blocks(w)
        resize(w, WIDE)
        assert w.maps_page.list.width() == theme.POOL_W + 200
        check_strip_over_blocks(w)
    finally:
        w.close()
    again = open_window(storage, PAGE_MAPS, WIDE)  # новое окно читает ширину из ui.ini
    try:
        assert again.maps_page.list.width() == theme.POOL_W + 200
        check_strip_over_blocks(again)
    finally:
        again.close()


def strip_geometry(window):
    """Секции полосы, прорезь, поле карты и Save в координатах окна."""
    strip = window.maps_page.strip
    return [rect(window, w) for w in (strip._left, strip.findChild(StripSeparator), strip._right, strip.field,
                                      strip.save_btn)]


def handle_event(handle, kind, start, dx):
    """Событие мыши ручке в точке `start` (глобальная, нажатие) + dx."""
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QMouseEvent
    glob = QPointF(start + QPoint(dx, 0))
    local = QPointF(handle.mapFromGlobal(glob.toPoint()))
    button = Qt.MouseButton.NoButton if kind == QEvent.Type.MouseMove else Qt.MouseButton.LeftButton
    buttons = Qt.MouseButton.NoButton if kind == QEvent.Type.MouseButtonRelease else Qt.MouseButton.LeftButton
    QApplication.sendEvent(handle, QMouseEvent(kind, local, glob, button, buttons,
                                               Qt.KeyboardModifier.NoModifier))


def test_handle_moves_place_strip_at_once(app, storage):
    """Протяжка ручки: в проходе, где схлопнутое движение раскладывается, секции полосы уже на месте (без отложенного
    LayoutRequest), Save у правого края не двигается ни в одном промежуточном состоянии; два движения до прохода —
    одна раскладка по последнему."""
    from PySide6.QtCore import QEvent
    w = open_window(storage, PAGE_MAPS, 1300)
    try:
        page = w.maps_page
        handle = page.split.handle
        save_x = rect(w, page.strip.save_btn).x()
        start = handle.mapToGlobal(QPoint(handle.width() // 2, handle.height() // 2))
        handle_event(handle, QEvent.Type.MouseButtonPress, start, 0)
        for moves in ((15,), (40,), (41,), (70,), (30,), (80, 90)):
            for dx in moves:
                handle_event(handle, QEvent.Type.MouseMove, start, dx)
            assert rect(w, page.strip.save_btn).x() == save_x
            handle._apply()  # проход цикла событий, в котором срабатывает схлопнутое движение (без processEvents)
            assert page.split.saved == theme.POOL_W + moves[-1]
            at_once = strip_geometry(w)
            assert at_once[-1].x() == save_x
            check_strip_over_blocks(w)
            QApplication.processEvents()
            assert strip_geometry(w) == at_once
        handle_event(handle, QEvent.Type.MouseButtonRelease, start, 90)
        QApplication.processEvents()
        assert rect(w, page.strip.save_btn).x() == save_x
    finally:
        w.close()
