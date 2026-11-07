"""Convert в ряду SplitRow: INPUT забирает лишнюю ширину, колонка OUTPUT (с клавишей CONVERT) — боковая справа, секции
полосы — над блоками экранов, прорезь — над зазором."""
import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from remap.ui import theme
from remap.ui.convert_page import SIDE_KEY
from remap.ui.main_window import PAGE_CONVERT, MainWindow
from remap.ui.settings import ui_settings

pytestmark = pytest.mark.ui

WIDE = 1600


def open_window(storage, width):
    w = MainWindow(storage)
    w.resize(width, 800)
    w.show()
    w.show_page(PAGE_CONVERT)
    QApplication.processEvents()
    return w


@pytest.fixture
def window(app, storage):
    w = open_window(storage, theme.WINDOW_SIZE[0])
    yield w
    w.close()
    w.deleteLater()


def rect(window, widget):
    return QRect(widget.mapTo(window, QPoint(0, 0)), widget.size())


def face(window, w):
    return w.face_rect().translated(w.mapTo(window, QPoint(0, 0)).toPointF())


def resize(window, width):
    window.resize(width, 800)
    QApplication.processEvents()


def faces(window):
    """Секции полосы (лицо первого виджета … лицо последнего) и прорезь между ними в координатах окна: (x, ширина)."""
    strip = window.convert_page.strip
    combo, target, output = face(window, strip.combo), face(window, strip.target_field), face(window, strip.output_btn)
    return ((combo.x(), target.right() - combo.x()), (output.x(), output.width()),
            (target.right(), output.x() - target.right()))


def drag(page, dx):
    handle = page.split.handle
    start = QPoint(handle.width() // 2, handle.height() // 2)
    QTest.mousePress(handle, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    QTest.mouseMove(handle, start + QPoint(dx, 0))
    QTest.mouseRelease(handle, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start + QPoint(dx, 0))
    QApplication.processEvents()


def check_layout(window):
    """Секции = блоки экранов − 2 × 21, прорезь 54 — по центру зазора; SOURCE ⇄ TARGET своей ширины; CONVERT — в колонке
    OUTPUT, 12 px под лицом экрана, по центру колонки."""
    page = window.convert_page
    inp, col, handle = rect(window, page.input), rect(window, page.output_column), rect(window, page.split.handle)
    left, right, sep = faces(window)
    assert left == (inp.x() + theme.STRIP_INSET, inp.width() - 2 * theme.STRIP_INSET)
    assert right == (col.x() + theme.STRIP_INSET, col.width() - 2 * theme.STRIP_INSET)
    assert page.strip.section_widths() == (left[1], right[1])
    assert sep[1] == theme.STRIP_SEP_W and handle.width() == theme.SCREEN_GAP
    assert sep[0] + sep[1] / 2 == handle.x() + handle.width() / 2
    strip = page.strip
    assert face(window, strip.source_field).width() == face(window, strip.target_field).width() == theme.CONVERT_MAP_W
    combo = face(window, strip.combo)
    assert combo.width() == left[1] - (theme.CONVERT_LEFT_W - theme.CONVERT_PROFILE_W)  # лишнее — комбо профиля
    go = face(window, page.convert_btn)
    assert (go.width(), go.height()) == (268, 68)
    assert go.center().x() == col.x() + col.width() / 2 and go.y() == 700


def test_strip_sections_at_900_follow_the_mockup(window):
    page = window.convert_page
    assert page.strip.section_widths() == (theme.CONVERT_LEFT_W, theme.CONVERT_OUTPUT_W) == (514, 226)
    assert rect(window, page.strip).width() == theme.STRIP_W
    assert (page.input.width(), page.output_column.width()) == (theme.CONVERT_INPUT_W, theme.CONVERT_RIGHT_W)
    assert face(window, page.strip.combo).width() == theme.CONVERT_PROFILE_W
    assert face(window, page.convert_btn).toRect() == QRect(600, 700, 268, 68)
    check_layout(window)


def test_wide_window_gives_the_rest_to_input(window):
    resize(window, WIDE)
    page = window.convert_page
    row_w = WIDE - 2 * theme.PAGE_MARGIN
    assert rect(window, page.strip).width() == row_w
    assert page.output_column.width() == theme.CONVERT_RIGHT_W
    assert page.input.width() == row_w - theme.SCREEN_GAP - theme.CONVERT_RIGHT_W
    check_layout(window)


def test_dragging_handle_moves_slot_and_convert(window):
    resize(window, WIDE)
    page = window.convert_page
    drag(page, -150)  # ручка влево — колонка OUTPUT шире
    assert page.output_column.width() == theme.CONVERT_RIGHT_W + 150
    check_layout(window)
    assert face(window, page.strip.output_btn).width() == theme.CONVERT_OUTPUT_W + 150
    drag(page, 400)  # уже макета нельзя
    assert page.output_column.width() == theme.CONVERT_RIGHT_W
    check_layout(window)


def test_saved_width_restored_after_narrow_then_wide(app, storage):
    w = open_window(storage, WIDE)
    try:
        drag(w.convert_page, -200)
        assert ui_settings(storage).value(SIDE_KEY, type=int) == theme.CONVERT_RIGHT_W + 200
        resize(w, theme.WINDOW_SIZE[0])
        assert w.convert_page.output_column.width() == theme.CONVERT_RIGHT_W
        check_layout(w)
        resize(w, WIDE)
        assert w.convert_page.output_column.width() == theme.CONVERT_RIGHT_W + 200
        check_layout(w)
    finally:
        w.close()
    again = open_window(storage, WIDE)  # новое окно читает ширину из ui.ini
    try:
        assert again.convert_page.output_column.width() == theme.CONVERT_RIGHT_W + 200
        check_layout(again)
    finally:
        again.close()


def strip_geometry(window):
    """Секции полосы, прорезь и поле OUTPUT в координатах окна."""
    strip = window.convert_page.strip
    sep = strip._left.parentWidget().layout().itemAt(1).widget()
    return [rect(window, w) for w in (strip._left, sep, strip._right, strip.output_btn)]


def test_window_resize_places_strip_at_once(app, storage):
    """Колонка OUTPUT шире макета, окно сужается: секции полосы встают на место в самом resize(), без отложенного
    LayoutRequest (иначе до следующего прохода цикла событий прорезь и OUTPUT стоят на старом x — дрожь при протяжке
    края окна)."""
    w = open_window(storage, theme.WINDOW_SIZE[0])  # окно открыто узким и расширено (так шаги ниже ловят сдвиг)
    try:
        resize(w, 1400)
        page = w.convert_page
        drag(page, -(600 - page.output_column.width()))  # колонка 600: шире, чем позволит узкое окно
        for width in (1300, 1200, 1100, 1000, 900):
            w.resize(width, 800)  # без processEvents
            at_once = strip_geometry(w)
            left, right, _sep = faces(w)
            inp, col = rect(w, page.input), rect(w, page.output_column)
            assert left == (inp.x() + theme.STRIP_INSET, inp.width() - 2 * theme.STRIP_INSET)
            assert right == (col.x() + theme.STRIP_INSET, col.width() - 2 * theme.STRIP_INSET)
            QApplication.processEvents()
            assert strip_geometry(w) == at_once
    finally:
        w.close()
