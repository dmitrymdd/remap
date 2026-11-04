"""Экран OUTPUT вкладки Convert: геометрия по макету, карточки, выделение, перетаскивание, двойной клик, Ctrl+A."""
import shutil
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from remap.storage import Storage
from remap.ui.main_window import PAGE_CONVERT, MainWindow

pytestmark = pytest.mark.ui

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "midi" / "Groove 01.mid"
CTRL = Qt.KeyboardModifier.ControlModifier


@pytest.fixture
def window(app, tmp_path):
    w = MainWindow(Storage(tmp_path / "store"))
    w.resize(900, 800)
    w.show()
    w.show_page(PAGE_CONVERT)
    yield w
    w.close()
    w.deleteLater()


def converted(window, tmp_path, *names, bad=()):
    paths = []
    for name in names:
        shutil.copy(SAMPLE, tmp_path / name)
        paths.append(tmp_path / name)
    for name in bad:
        (tmp_path / name).write_bytes(b"not midi")
        paths.append(tmp_path / name)
    window.convert_page._accept_files(paths)
    window.convert_page.convert()
    QApplication.processEvents()
    return window.convert_page.output_screen


def test_screen_and_cards_follow_the_mockup(window, tmp_path):
    screen = converted(window, tmp_path, "a.mid", "b.mid")
    origin = screen.mapTo(window, QPoint(0, 0))
    assert QRect(origin, screen.size()) == QRect(600, 139, 268, 551)  # лицо блока 268×548 в (600, 140)
    first, second = screen.cards()
    pos = first.mapTo(window, QPoint(0, 0))
    assert (pos.x(), pos.y(), first.width(), first.height()) == (621, 199, 226, 54)
    assert second.mapTo(window, QPoint(0, 0)).y() - pos.y() == 62  # карточка 54 + зазор 8
    assert first.text_x() == 43  # значок 22 с полем 10 и зазор 10
    go = window.convert_page.convert_btn.mapTo(window, QPoint(0, 0))
    assert (go.y(), window.convert_page.convert_btn.height()) == (700, 68)  # место клавиши CONVERT
    assert screen.footer.text == "DRAG INTO YOUR DAW"


def test_planned_cards_and_failed_files(window, tmp_path):
    screen = converted(window, tmp_path, "a.mid", bad=("b.mid",))
    assert [(c.path.name, c.ready) for c in screen.cards()] == [("a_remapped.mid", True)]  # у ошибки карточки нет
    shutil.copy(SAMPLE, tmp_path / "c.mid")
    window.convert_page._accept_files([tmp_path / "c.mid"])  # добавление сбрасывает результаты: все — будущие
    assert [(c.path.name, c.ready) for c in screen.cards()] == [
        ("a_remapped.mid", False), ("b_remapped.mid", False), ("c_remapped.mid", False)]


def test_drag_takes_selected_or_only_the_card(window, tmp_path, monkeypatch):
    screen = converted(window, tmp_path, "a.mid", "b.mid", "c.mid")
    a, b, c = screen.cards()
    def names(card):
        return [p.name for p in screen.ready_targets(card)]

    assert names(b) == ["b_remapped.mid"]  # ничего не выделено — только она
    screen.card_pressed(a.path, Qt.KeyboardModifier.NoModifier)
    screen.card_pressed(c.path, CTRL)
    assert names(a) == ["a_remapped.mid", "c_remapped.mid"] and names(b) == ["b_remapped.mid"]
    dragged = []
    monkeypatch.setattr(screen, "drag_from", lambda card: dragged.append(names(card)))
    QTest.mousePress(c, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(20, 20))
    QTest.mouseMove(c, QPoint(60, 40))
    QTest.mouseRelease(c, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(60, 40))
    assert dragged == [["a_remapped.mid", "c_remapped.mid"]]  # нажатие на выделенную не сбросило выделение
    QTest.mouseClick(c, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(20, 20))
    assert [p.name for p in screen.selection.selected] == ["c_remapped.mid"]  # клик без перетаскивания — только она


def test_ctrl_a_goes_to_the_last_clicked_screen_and_delete_stays_on_input(window, tmp_path):
    screen = converted(window, tmp_path, "a.mid", "b.mid")
    page = window.convert_page
    QTest.keyClick(window, Qt.Key.Key_A, CTRL)  # по умолчанию — INPUT
    assert len(page.input.selection) == 2 and len(screen.selection) == 0
    page.input.clear_selection()
    QTest.mouseClick(screen.cards()[0], Qt.MouseButton.LeftButton)
    QTest.keyClick(window, Qt.Key.Key_A, CTRL)
    assert len(screen.selection) == 2 and len(page.input.selection) == 0
    QTest.keyClick(window, Qt.Key.Key_Delete)  # Delete убирает только строки INPUT — там ничего не выделено
    assert len(page.sources) == 2
