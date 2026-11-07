"""Нижняя полоса `StatusStrip`: одна на всех вкладках — то же место, шрифт, цвета; статус слева, подсказки справа."""

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QWidget

from remap.storage import Storage
from remap.ui import text, theme
from remap.ui.main_window import PAGE_CONVERT, PAGE_MAPS, PAGE_PROFILES, MainWindow
from remap.ui.status_strip import FONT, PAD_X, STATE_COLORS, SUGGEST_GAP, StatusStrip
from test_ui_profiles import new_profile, stub_dialogs

pytestmark = pytest.mark.ui


@pytest.fixture
def window(app, tmp_path):
    theme.load_fonts()
    w = MainWindow(Storage(tmp_path / "store"))
    w.resize(*theme.WINDOW_SIZE)
    w.show()
    app.processEvents()
    yield w
    w.close()
    w.deleteLater()


def _pages(w):
    return {PAGE_CONVERT: w.convert_page, PAGE_PROFILES: w.profiles_page, PAGE_MAPS: w.maps_page}


def _ink_columns(strip: StatusStrip) -> tuple[int, int]:
    """Первый и последний столбец, где нарисовано хоть что-то (полоса сама фона не рисует)."""
    img = QImage(strip.size(), QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    strip.render(p, QPoint(0, 0), renderFlags=QWidget.RenderFlag.DrawChildren)
    p.end()
    cols = [x for x in range(img.width()) if any(img.pixelColor(x, y).alpha() > 40 for y in range(img.height()))]
    return cols[0], cols[-1]


def test_same_strip_widget_and_geometry_on_every_tab(window, app):
    geoms = set()
    for idx, page in _pages(window).items():
        window.show_page(idx)
        app.processEvents()
        strip = page.status
        assert type(strip) is StatusStrip and strip.isVisibleTo(window)
        top_left = strip.mapTo(window, QPoint(0, 0))
        geoms.add((top_left.x(), top_left.y(), strip.width(), strip.height(), strip.line_rect().getRect()))
    assert len(geoms) == 1
    x, y, w, h, _ = geoms.pop()
    assert h == theme.BAND_H and y + h <= window.height()
    screw_line = window.height() - theme.SCREW_INSET - theme.SCREW_SIZE / 2
    assert y + theme.BAND_ITEM_TOP + theme.BAND_ITEM_H / 2 == screw_line  # на линии центров нижних винтов
    assert x + PAD_X >= theme.SCREW_INSET + theme.SCREW_SIZE and x + w - PAD_X <= window.width() - 25  # между винтами


@pytest.mark.parametrize("idx", [PAGE_CONVERT, PAGE_PROFILES, PAGE_MAPS])
def test_status_is_left_aligned_and_elided_on_the_right(window, app, idx):
    window.show_page(idx)
    app.processEvents()
    strip = _pages(window)[idx].status
    strip.clear_suggestion()
    strip.set_status("Short")
    first, last = _ink_columns(strip)
    assert PAD_X <= first <= PAD_X + 2  # от левого края, на всех вкладках одинаково
    assert last < PAD_X + text.text_width("Short", FONT) + 2
    long = "Very long status message " * 20
    strip.set_status(long, "error")
    shown = strip.shown_text()
    assert shown != long and shown.endswith("…") and long.startswith(shown[:-1].rstrip())
    assert strip.tooltip_at(strip.status_rect().center()) == long  # обрезанный — целиком в подсказке
    assert strip.state() == "error"


def test_state_colours_are_theme_tokens():
    assert STATE_COLORS == {"": theme.SILK_TEXT, "ok": theme.OK_TEXT, "warn": theme.WARN_TEXT, "error": theme.ERR_TEXT}
    strip = StatusStrip()
    with pytest.raises(ValueError):
        strip.set_status("x", "bogus")


def test_suggestions_are_right_anchored_and_status_elides_before_them(app):
    strip = StatusStrip()
    strip.resize(600, theme.BAND_H)
    strip.set_status("Short")
    strip.set_suggestion("12 matches", "tip", apply_enabled=True, apply_tip="apply tip", dismiss_tip="dismiss tip")
    parts = strip.parts()
    apply_x = parts["apply"].left()
    assert parts["dismiss"].right() == strip.line_rect().right()
    assert parts["label"].right() < parts["dot"].left() < parts["apply"].left() < parts["dismiss"].left()
    strip.set_status("Very long status message " * 20)
    assert strip.parts()["apply"].left() == apply_x  # Apply не прыгает от длины статуса
    assert strip.status_rect().right() == parts["label"].left() - SUGGEST_GAP
    assert text.text_width(strip.shown_text(), FONT) <= strip.status_rect().width() + 0.5
    assert strip.tooltip_at(parts["apply"].center()) == "apply tip"
    assert strip.tooltip_at(parts["dismiss"].center()) == "dismiss tip"
    assert strip.tooltip_at(parts["label"].center()) == "tip"
    strip.clear_suggestion()
    assert strip.parts() == {} and strip.status_rect().right() == strip.line_rect().right()


def test_apply_and_dismiss_clicks(app):
    from PySide6.QtTest import QTest
    strip = StatusStrip()
    strip.resize(600, theme.BAND_H)
    strip.show()
    hits = []
    strip.apply_clicked.connect(lambda: hits.append("apply"))
    strip.dismiss_clicked.connect(lambda: hits.append("dismiss"))
    strip.set_suggestion("3 matches", apply_enabled=False)
    for name in ("apply", "dismiss", "label"):
        QTest.mouseClick(strip, Qt.MouseButton.LeftButton, pos=strip.parts()[name].center().toPoint())
    assert hits == ["dismiss"]  # недоступная Apply не нажимается
    strip.set_suggestion("3 matches", apply_enabled=True)
    QTest.mouseClick(strip, Qt.MouseButton.LeftButton, pos=strip.parts()["apply"].center().toPoint())
    assert hits == ["dismiss", "apply"]
    strip.close()


def test_profiles_suggestion_strip_drives_page(window, app):
    page = window.profiles_page
    stub_dialogs(page)
    window.show_page(PAGE_PROFILES)
    new_profile(page)
    strip = page.status
    assert strip.suggestion().endswith("matches")
    strip.dismiss_clicked.emit()
    assert strip.suggestion() is None and not page.cables.suggestion_items


def test_only_profiles_status_fades(window):
    assert window.profiles_page.status.fade_timer is not None
    assert window.convert_page.status.fade_timer is None and window.maps_page.status.fade_timer is None
    window.maps_page.status.set_status("Saved.", "ok")
    assert window.maps_page.status.opacity == 1.0


def test_paints_with_state_colour(app):
    strip = StatusStrip()
    strip.resize(300, theme.BAND_H)
    strip.set_status("█████", "error")
    img = QImage(strip.size(), QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    strip.render(p, QPoint(0, 0), renderFlags=QWidget.RenderFlag.DrawChildren)
    p.end()
    y = round(strip.line_rect().center().y())
    solid = [img.pixelColor(x, y) for x in range(img.width()) if img.pixelColor(x, y).alpha() == 255]
    assert solid and all(c.name().upper() == QColor(theme.ERR_TEXT).name().upper() for c in solid)


def test_maps_more_key_uses_the_profiles_dots_glyph(window):
    from remap.ui.keys import MAP
    more = window.maps_page.strip.more_btn
    assert more.icon_name == window.profiles_page.strip.dots_btn.icon_name == "dots"
    assert more.spec is MAP and more.face_size().width() == 48 and more.face_size().height() == 38
