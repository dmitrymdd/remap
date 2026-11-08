"""Profiles в ряду SplitRow: пул — боковая колонка слева, сцена забирает лишнюю ширину (обе колонки поровну, промежуток
под кабели постоянный), секции полосы — над блоками экранов, SOURCE / TARGET — над колонками, ⇄ — над промежутком."""
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from remap.core.profile import RemapProfile
from remap.ui import theme
from remap.ui.cable_layout import CABLE_GAP
from remap.ui.cable_view import PAD, SIDE_KEY
from remap.ui.main_window import PAGE_PROFILES
from remap.ui.settings import ui_settings
from remap.ui.strip import StripSeparator, section_width
from remap.ui.tutorial import STEPS
from conftest import open_window as open_main_window
from test_ui_profiles import stub_dialogs

pytestmark = pytest.mark.ui

FIXTURES = Path(__file__).resolve().parent / "fixtures"
WIDE = 1600


def open_window(storage, width, profile="ezd3_sd3_saved.json"):
    p = RemapProfile.from_json((FIXTURES / profile).read_text(encoding="utf-8"))
    pid = storage.save_profile(p, overwrite=True)
    w = open_main_window(storage, PAGE_PROFILES, width)
    page = w.profiles_page
    stub_dialogs(page)
    page.combo.setCurrentIndex(next(i for i in range(page.combo.count()) if page.combo.itemData(i) == pid))
    QApplication.processEvents()
    assert page.cables.cable_items
    return w


@pytest.fixture
def window(app, storage):
    theme.load_fonts()
    w = open_window(storage, theme.WINDOW_SIZE[0])
    yield w
    w.close()


def rect(window, widget):
    return QRect(widget.mapTo(window, QPoint(0, 0)), widget.size())


def face(window, w):
    return w.face_rect().translated(w.mapTo(window, QPoint(0, 0)).toPointF())


def resize(window, width):
    window.resize(width, theme.WINDOW_SIZE[1])
    QApplication.processEvents()


def drag(window, dx):
    handle = window.profiles_page.cables.split.handle
    start = QPoint(handle.width() // 2, handle.height() // 2)
    QTest.mousePress(handle, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    QTest.mouseMove(handle, start + QPoint(dx, 0))
    QTest.mouseRelease(handle, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start + QPoint(dx, 0))
    QApplication.processEvents()


def check_layout(window):
    """Секции полосы над блоками, SOURCE / TARGET над колонками сцены, ⇄ по центру промежутка, прорезь над зазором."""
    page, ed = window.profiles_page, window.profiles_page.cables
    strip = page.strip
    pool, scene, handle = rect(window, ed.pool_block), rect(window, ed.scene_block), rect(window, ed.split.handle)
    assert handle.width() == theme.SCREEN_GAP and pool.right() + 1 == handle.x() and handle.right() + 1 == scene.x()
    combo, save = face(window, strip.combo), face(window, strip.save_btn)
    assert combo.x() == pool.x() + theme.STRIP_INSET
    assert save.right() == pool.right() + 1 - theme.STRIP_INSET
    assert strip.section_widths() == (section_width(pool.width()), section_width(scene.width()))
    sep = rect(window, strip.findChild(StripSeparator))
    assert abs(sep.center().x() + 0.5 - (handle.x() + handle.width() / 2)) <= 1
    # колонки сцены в координатах окна
    vp = ed.view.viewport().mapTo(window, QPoint(0, 0)) - QPoint(0, round(ed.view.mapToScene(QPoint(0, 0)).y()))
    lx, rx, col2, col3 = ed._scene_columns()
    src, dst, swap = face(window, strip.from_btn), face(window, strip.to_btn), face(window, strip.direction_btn)
    assert (src.x(), src.width()) == (vp.x() + lx, col2)
    assert (dst.x(), dst.width()) == (vp.x() + rx, col3)
    assert dst.x() - src.right() == CABLE_GAP
    assert abs(swap.center().x() - (src.right() + dst.x()) / 2) <= 1
    assert src.x() == scene.x() + theme.STRIP_INSET and dst.right() == scene.right() + 1 - theme.STRIP_INSET
    return lx, rx, col2, col3


def test_at_900_nothing_changes(window):
    ed = window.profiles_page.cables
    assert check_layout(window) == (PAD, PAD + 322, 200, 200)
    assert window.profiles_page.strip.section_widths() == (theme.STRIP_LEFT_W, theme.STRIP_RIGHT_W)
    assert (ed.pool_block.width(), ed.scene_block.width()) == (theme.POOL_W, theme.SCENE_W)
    assert rect(window, window.profiles_page.strip).width() == theme.STRIP_W


def test_wide_window_gives_the_rest_to_the_scene(window):
    resize(window, WIDE)
    ed = window.profiles_page.cables
    row_w = WIDE - 2 * theme.PAGE_MARGIN
    assert ed.pool_block.width() == theme.POOL_W
    assert ed.scene_block.width() == row_w - theme.SCREEN_GAP - theme.POOL_W
    assert rect(window, window.profiles_page.strip).width() == row_w
    _lx, _rx, col2, col3 = check_layout(window)
    extra = ed.scene_block.width() - theme.SCENE_W
    assert col2 + col3 == 400 + extra and col3 - col2 in (0, 1)
    # заголовки групп цели — через обе колонки
    for h in ed.scene_headers.values():
        assert h.rect.width() == section_width(ed.scene_block.width())


def test_dragging_handle_moves_everything(window):
    resize(window, WIDE)
    drag(window, 150)
    ed = window.profiles_page.cables
    assert ed.pool_block.width() == theme.POOL_W + 150
    check_layout(window)
    drag(window, -400)
    assert ed.pool_block.width() == theme.POOL_W
    check_layout(window)


def test_saved_width_restored_after_narrow_then_wide(app, storage):
    theme.load_fonts()
    w = open_window(storage, WIDE)
    try:
        drag(w, 200)
        assert ui_settings(storage).value(SIDE_KEY, type=int) == theme.POOL_W + 200
        resize(w, theme.WINDOW_SIZE[0])
        assert w.profiles_page.cables.pool_block.width() == theme.POOL_W
        check_layout(w)
        resize(w, WIDE)
        assert w.profiles_page.cables.pool_block.width() == theme.POOL_W + 200
        check_layout(w)
    finally:
        w.close()
    again = open_window(storage, WIDE)
    try:
        assert again.profiles_page.cables.pool_block.width() == theme.POOL_W + 200
        check_layout(again)
    finally:
        again.close()


def test_width_change_keeps_scroll_and_rows_vertically(window):
    resize(window, WIDE)
    ed = window.profiles_page.cables
    bar = ed.view.verticalScrollBar()
    bar.setValue(bar.maximum() // 2)
    QApplication.processEvents()
    top = bar.value()
    assert top > 0
    row = min((r for r in ed.target_items.values() if r.rect.top() >= top), key=lambda r: r.rect.top())
    key, y = row.model.slot, row.rect.top()
    drag(window, 180)
    assert bar.value() == top and ed.target_items[key].rect.top() == y
    resize(window, 1300)
    assert bar.value() == top and ed.target_items[key].rect.top() == y


def test_cable_endpoints_on_ports_at_wide(window):
    resize(window, WIDE)
    ed = window.profiles_page.cables
    for c in ed.cable_items:
        a, b = c.path().pointAtPercent(0), c.path().pointAtPercent(1)
        assert a.x() == c.src.rect.right() and a.y() == c.src.line_center()
        assert b.x() == c.dst.rect.left() and c.dst.rect.top() <= b.y() <= c.dst.rect.bottom()


def test_tutorial_holes_on_their_widgets_at_wide(window):
    resize(window, WIDE)
    tut = window.tutorial
    body = window.centralWidget()
    ed = window.profiles_page.cables
    targets = {"strip": window.profiles_page.strip, "pool": ed.pool_screen, "scene": ed.scene_screen}
    tut.start()
    for i in range(len(STEPS)):
        tut.go(i)
        for hole, _r in tut.holes:
            assert QRectF(body.rect()).contains(hole)
            # вырез — на одном из виджетов страницы (с полями ± 12)
            assert any(QRectF(rect(body, w)).adjusted(-12, -12, 12, 12).intersects(hole)
                       for w in [*targets.values(), *window.profiles_page.strip.findChildren(type(ed.match_btn))])
    tut.go(3)
    (hole, _r), = tut.holes
    lx, _rx, col2, _col3 = ed._scene_columns()
    gap_left = ed.view.viewport().mapTo(body, QPoint(0, 0)).x() + lx + col2
    assert abs(hole.left() + 4 - gap_left) <= 1 and hole.width() == CABLE_GAP + 2 * 4


def test_drag_during_width_change_ends_cleanly(window):
    resize(window, WIDE)
    ed = window.profiles_page.cables
    note = next(iter(ed.source_items))
    ed.begin_drag({note}, QPointF(ed.source_anchor(note)))
    resize(window, 1300)
    drag(window, 100)
    ed.cancel_drag()
    QApplication.processEvents()
    assert not ed.dragging


def editor_state(ed):
    """Снимок вида: пиксели обеих колонок и подсказки всех элементов."""
    QApplication.processEvents()
    pixels = [v.viewport().grab().toImage() for v in (ed.pool, ed.view)]
    tips = [i.toolTip() for v in (ed.pool, ed.view) for i in v.scene().items()]
    return pixels, sorted(tips)


@pytest.mark.parametrize("dx", [180, -60])
def test_width_change_moves_items_and_matches_full_rebuild(window, dx):
    """Смена ширины не пересоздаёт элементы: те же строки, заголовки и кабели на новых местах — картинка и подсказки
    как после полной перестройки при той же ширине, прокрутка на месте."""
    resize(window, WIDE)
    ed = window.profiles_page.cables
    ed.set_selection({next(iter(ed.source_items))})
    bar = ed.view.verticalScrollBar()
    bar.setValue(bar.maximum() // 2)
    QApplication.processEvents()
    top = bar.value()
    before = {id(i) for v in (ed.pool, ed.view) for i in v.scene().items()}
    drag(window, dx)
    assert {id(i) for v in (ed.pool, ed.view) for i in v.scene().items()} == before
    assert bar.value() == top
    moved = editor_state(ed)
    ed._build(anchor=False)
    assert bar.value() == top
    rebuilt = editor_state(ed)
    assert moved[1] == rebuilt[1]
    assert all(a == b for a, b in zip(moved[0], rebuilt[0], strict=True))
