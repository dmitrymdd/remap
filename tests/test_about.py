"""Логотип шапки (пререндер по DPR, наведение, свечение без обрезки) и слой About (тексты, ссылки, закрытие)."""
import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

import remap
from remap.ui import about, shell, theme
from remap.ui.main_window import MainWindow

pytestmark = pytest.mark.ui


@pytest.fixture
def window(app, storage):
    theme.load_fonts()
    w = MainWindow(storage)
    w.resize(*theme.WINDOW_SIZE)
    w.show()
    app.processEvents()
    yield w
    w.close()
    w.deleteLater()


def _face_center(logo) -> QPoint:
    return logo.face_rect().center().toPoint()


@pytest.mark.parametrize(("dpr", "scale"), [(0.75, 1), (1.0, 1), (1.25, 2), (1.5, 2), (2.0, 2), (2.5, 3), (3.0, 3),
                                            (4.0, 3)])
def test_logo_scale_by_device_pixel_ratio(dpr, scale):
    assert shell.logo_scale(dpr) == scale


def test_logo_pixmaps_match_the_chosen_scale(app):
    w, h = theme.LOGO_SIZE
    pad = theme.LOGO_GLOW_PAD
    for dpr, n in ((1.0, 1), (1.25, 2), (3.0, 3)):
        assert shell.logo_pixmap("logo", dpr).size().toTuple() == (w * n, h * n)
        assert shell.logo_pixmap("logo_hover", dpr).size().toTuple() == (w * n, h * n)
        assert shell.logo_pixmap("logo_glow", dpr).size().toTuple() == ((w + 2 * pad) * n, (h + 2 * pad) * n)


def test_logo_face_sits_at_header_padding_and_glow_fits_the_brand_block(window):
    logo = window.brand.logo
    face = logo.face_rect().translated(QPointF(logo.mapTo(window.centralWidget(), QPoint(0, 0))))
    assert face.left() == theme.HEADER_PAD_X and face.size().toTuple() == theme.LOGO_SIZE
    assert abs(face.center().y() - theme.HEADER_H / 2) <= 0.5
    # свечение — весь виджет логотипа: он целиком внутри блока, и блок его не обрезает
    assert window.brand.rect().contains(logo.geometry())
    assert logo.width() == theme.LOGO_SIZE[0] + 2 * theme.LOGO_GLOW_PAD


def test_logo_hover_toggles_only_over_the_face(window):
    logo = window.brand.logo
    QTest.mouseMove(logo, _face_center(logo))
    assert logo.hovered and logo.lit
    QTest.mouseMove(logo, QPoint(2, 2))  # поле под свечение — не кнопка
    assert not logo.hovered
    QTest.mouseMove(logo, _face_center(logo))
    assert logo.hovered
    QTest.mouseMove(window.brand, QPoint(window.brand.width() - 2, 2))  # ушли с логотипа
    assert not logo.hovered and not logo.lit


def test_logo_hover_paints_glow_outside_the_slot(window):
    logo = window.brand.logo
    corner = QPoint(theme.LOGO_GLOW_PAD - 3, logo.height() // 2)  # слева от лица, внутри поля свечения
    before = logo.grab().toImage().pixelColor(corner)
    logo._set_hovered(True)
    after = logo.grab().toImage().pixelColor(corner)
    assert after.alpha() > before.alpha()


def test_clicking_the_logo_opens_about_and_esc_closes_it(window):
    logo = window.brand.logo
    QTest.mouseClick(logo, Qt.MouseButton.LeftButton, pos=QPoint(2, 2))  # мимо лица
    assert not window.about.isVisible()
    QTest.mouseClick(logo, Qt.MouseButton.LeftButton, pos=_face_center(logo))
    assert window.about.isVisible() and logo.on
    assert window.about.geometry() == window.centralWidget().rect()
    QTest.keyClick(window.about, Qt.Key.Key_Escape)
    assert not window.about.isVisible() and not logo.on


def test_close_key_closes_and_backdrop_click_does_not(window):
    window.show_about()
    QTest.mouseClick(window.about, Qt.MouseButton.LeftButton, pos=QPoint(5, 5))
    assert window.about.isVisible()
    key = window.about.plate.close_key
    QTest.mouseClick(key, Qt.MouseButton.LeftButton, pos=key.face_rect().center().toPoint())
    assert not window.about.isVisible()


def test_about_swallows_window_shortcuts(window):
    window.show_about()
    tab = window.pages.currentIndex()
    QTest.keyClick(window.about, Qt.Key.Key_S, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClick(window.about, Qt.Key.Key_Tab)
    assert window.about.isVisible() and window.pages.currentIndex() == tab


def test_about_contents(window):
    plate = window.about.plate
    assert remap.__version__ == "0.1.0"
    assert plate.title.version == "v0.1.0"
    assert about.HANDLE == "dmitry.mdd" and about.AUTHOR == "Dmitry Mysyakov"
    assert [(r.link.label, r.link.value, r.link.url) for r in plate.links] == [
        ("GitHub", "github.com/dmitrymdd", "https://github.com/dmitrymdd"),
        ("Discord", "dmitry.mdd", ""),
        ("Email", "dmitrymdd@gmail.com", "mailto:dmitrymdd@gmail.com"),
    ]
    assert " ".join(plate.license.lines).startswith("© 2026 Dmitry Mysyakov · GPL-3.0 · no warranty")
    assert "LGPL-3.0" in " ".join(plate.license.lines) and "SIL OFL 1.1" in " ".join(plate.license.lines)
    assert len(plate.license.lines) == 2  # обе строки помещаются по ширине экрана
    assert plate.face_rect().width() == theme.ABOUT_W


def test_links_open_in_browser_and_discord_copies(window, monkeypatch):
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url.toString()) or True)
    window.show_about()
    github, discord, email = window.about.plate.links
    github.click()
    email.click()
    assert opened == ["https://github.com/dmitrymdd", "mailto:dmitrymdd@gmail.com"]
    discord.click()
    assert QApplication.clipboard().text() == "dmitry.mdd"
    assert discord.shown == about.COPIED.upper()
    discord.flash(None)
    assert discord.shown == "dmitry.mdd"
