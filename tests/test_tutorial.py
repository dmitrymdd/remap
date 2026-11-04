"""Обучение Profiles: вырезы на местах макета, плашка, клавиши, блокировка ввода, первый заход на вкладку."""
import pytest
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from remap.core.profile import FORWARD
from remap.ui import text, theme
from remap.ui.main_window import NO_TUTORIAL_ENV, PAGE_CONVERT, PAGE_MAPS, PAGE_PROFILES, TUTORIAL_KEY, MainWindow
from remap.ui.tutorial import STEPS, Step
from test_ui_profiles import EZD3, SD3, new_profile, stub_dialogs

pytestmark = pytest.mark.ui


@pytest.fixture
def window(app, storage):
    theme.load_fonts()
    w = MainWindow(storage)
    w.resize(*theme.WINDOW_SIZE)
    w.show()
    w.show_page(PAGE_PROFILES)
    stub_dialogs(w.profiles_page)
    app.processEvents()
    yield w
    w.close()
    w.deleteLater()


def _with_cables(window):
    page = window.profiles_page
    new_profile(page, "T", EZD3, SD3)
    page.match_by_number()
    QApplication.processEvents()
    return page


def _close(a: QRectF, b: tuple, tol: float) -> bool:
    return all(abs(x - y) <= tol for x, y in zip((a.x(), a.y(), a.width(), a.height()), b, strict=True))


def test_holes_land_where_the_mockup_has_them(window):
    _with_cables(window)
    tut = window.tutorial
    tut.start()
    for i, step in enumerate(STEPS):
        tut.go(i)
        assert len(tut.holes) == len(step.spots)
        if step.spots[0].target == "cables":  # связка — та, что в профиле, а не в макете
            continue
        assert _close(tut.holes[step.anchor][0], step.mock_hole, 4), (step.title, tut.holes)
        face = tut.plate.face_rect().translated(QPointF(tut.plate.pos()))
        assert abs(face.x() - step.mock_plate[0]) <= 4 and abs(face.y() - step.mock_plate[1]) <= 4, step.title


def test_cable_step_cuts_out_the_busiest_bundle(window):
    page = _with_cables(window)
    window.tutorial.start(3)
    (hole, _r), = window.tutorial.holes
    editor = page.cables
    gap_left = editor.view.viewport().mapTo(window.centralWidget(), QPoint(0, 0)).x()
    assert hole.width() == theme.COL_GAP + 2 * 4 and hole.left() > gap_left  # промежуток между колонками ± 4
    face = window.tutorial.plate.face_rect().translated(QPointF(window.tutorial.plate.pos()))
    assert not face.intersects(hole)


def test_cable_step_without_cables_cuts_out_the_scene(window):
    new_profile(window.profiles_page, "T", EZD3, SD3)
    window.tutorial.start(3)
    (hole, _r), = window.tutorial.holes
    screen = window.profiles_page.cables.scene_screen
    assert hole.contains(QRectF(screen.rect()).translated(QPointF(screen.mapTo(window.centralWidget(), QPoint(0, 0)))))


def test_plate_sits_below_or_beside_the_hole_as_in_the_mockup():
    step = Step("t", "x", (), (100, 100, 50, 50), (80, 170))
    assert step.plate_at(QRectF(10, 600, 50, 50)) == QPointF(-10, 670)  # под вырезом: от низа
    beside = Step("t", "x", (), (150, 161, 126, 36), (304, 150))
    assert beside.plate_at(QRectF(150, 300, 126, 36)) == QPointF(304, 289)  # рядом: от верха


def test_plate_never_leaves_the_window(window):
    _with_cables(window)
    tut = window.tutorial
    tut.start()
    window.resize(900, 580)
    QApplication.processEvents()
    QApplication.processEvents()
    for i in range(len(STEPS)):
        tut.go(i)
        face = tut.plate.face_rect().translated(QPointF(tut.plate.pos()))
        assert QRectF(tut.rect()).contains(face), STEPS[i].title


def test_resize_moves_the_holes(window):
    tut = window.tutorial
    tut.start(2)  # экраны растут с высотой окна
    before = tut.holes[0][0]
    window.resize(900, 900)
    QApplication.processEvents()
    QApplication.processEvents()
    assert tut.geometry() == window.centralWidget().rect()
    assert tut.holes[0][0].height() == before.height() + 100


def test_keys_move_between_steps_and_esc_closes(window):
    tut = window.tutorial
    tut.start()
    assert not tut.plate.back.isVisible() and tut.plate.next.text() == "Next"
    QTest.keyClick(tut, Qt.Key.Key_Return)
    assert tut.index == 1 and tut.plate.back.isVisible()
    QTest.keyClick(tut, Qt.Key.Key_Left)
    assert tut.index == 0
    tut.go(len(STEPS) - 1)
    assert tut.plate.next.text() == "Done" and not tut.plate.skip.isVisible()
    QTest.keyClick(tut, Qt.Key.Key_Escape)
    assert not tut.isVisible()
    assert window.settings.value(TUTORIAL_KEY, False, type=bool)


def test_buttons_drive_the_steps(window):
    tut = window.tutorial
    tut.start()
    tut.plate.next.click()
    tut.plate.back.click()
    assert tut.index == 0
    tut.go(len(STEPS) - 1)
    tut.plate.next.click()  # DONE
    assert not tut.isVisible()
    tut.start()
    tut.plate.skip.click()
    assert not tut.isVisible()


def test_input_under_the_overlay_is_blocked(window):
    page = _with_cables(window)
    rules = dict(page.work.rules)
    window.tutorial.start(5)  # вырез над «⇄»
    hole = window.tutorial.holes[0][0]
    QTest.mouseClick(window.tutorial, Qt.MouseButton.LeftButton, pos=hole.center().toPoint())
    assert page.direction == FORWARD
    QTest.keyClick(window.tutorial, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)  # Undo не срабатывает
    assert page.work.rules == rules
    bar = page.cables.view.verticalScrollBar()
    value = bar.value()
    pos = QPointF(window.tutorial.rect().center())
    wheel = QWheelEvent(pos, window.tutorial.mapToGlobal(pos), QPoint(), QPoint(0, -120), Qt.MouseButton.NoButton,
                        Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(window.tutorial, wheel)
    assert bar.value() == value
    QTest.keyClick(window.tutorial, Qt.Key.Key_Escape)
    page.undo()
    assert page.work.rules != rules  # после обучения отмена снова работает


def test_scene_scroll_is_restored_after_the_tutorial(window):
    page = _with_cables(window)
    bar = page.cables.view.verticalScrollBar()
    bar.setValue(0)
    window.start_tutorial()
    window.tutorial.go(3)  # связку центрирует
    window.tutorial.finish()
    assert bar.value() == 0


def test_help_key_only_on_profiles(window):
    assert not window.help_btn.isHidden() and "Show the tutorial" in window.help_btn.toolTip()
    window.show_page(PAGE_CONVERT)
    assert window.help_btn.isHidden()
    window.show_page(PAGE_MAPS)
    assert window.help_btn.isHidden()
    window.start_tutorial()
    assert not window.tutorial.isVisible()
    window.show_page(PAGE_PROFILES)
    window.help_btn.click()
    assert window.tutorial.isVisible()


def test_help_key_face_left_of_the_tabs(window):
    root = window.centralWidget()
    face = window.help_btn.face_rect().translated(QPointF(window.help_btn.mapTo(root, QPoint(0, 0))))
    tab = window.nav_convert.face_rect().translated(QPointF(window.nav_convert.mapTo(root, QPoint(0, 0))))
    assert (face.x(), face.y(), face.width()) == (438, 14, 36) and tab.x() - face.right() == theme.HELP_GAP


def test_first_visit_to_profiles_shows_it_once(app, storage, monkeypatch):
    monkeypatch.delenv(NO_TUTORIAL_ENV, raising=False)
    w = MainWindow(storage)
    w.show()
    w.show_page(PAGE_PROFILES)
    app.processEvents()
    assert w.tutorial.isVisible()
    w.tutorial.finish()
    w.show_page(PAGE_CONVERT)
    w.show_page(PAGE_PROFILES)
    app.processEvents()
    assert not w.tutorial.isVisible()
    w.close()
    w2 = MainWindow(storage)  # ui.ini помнит
    w2.show()
    w2.show_page(PAGE_PROFILES)
    app.processEvents()
    assert not w2.tutorial.isVisible()
    w2.close()


def test_prose_keeps_case_and_wraps(app):
    theme.load_fonts()
    spec = text.prose(theme.TUT_TEXT_FONT)
    assert text.text_width("abc", spec) < text.text_width("ABC", spec)
    lines = text.wrap(STEPS[3].text, spec, 282)
    assert " ".join(lines) == STEPS[3].text
    assert all(text.text_width(line, spec) <= 282 for line in lines) and len(lines) == 3  # три строки, как в макете
