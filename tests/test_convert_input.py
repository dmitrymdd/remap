"""Экран INPUT вкладки Convert: геометрия по макету, строки файлов, выделение как в Проводнике, ×, Delete, DETAILS."""
import shutil
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from remap.core import FileResult
from remap.ui.convert_text import file_state, state_tip, totals_parts
from remap.ui.main_window import PAGE_CONVERT, MainWindow
from remap.storage import Storage

pytestmark = pytest.mark.ui

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "midi" / "Groove 01.mid"
CTRL, SHIFT = Qt.KeyboardModifier.ControlModifier, Qt.KeyboardModifier.ShiftModifier


@pytest.fixture
def window(app, tmp_path):
    w = MainWindow(Storage(tmp_path / "store"))
    w.resize(900, 800)
    w.show()
    w.show_page(PAGE_CONVERT)
    yield w
    w.close()
    w.deleteLater()


def add_files(window, tmp_path, *names):
    paths = []
    for name in names:
        shutil.copy(SAMPLE, tmp_path / name)
        paths.append(tmp_path / name)
    window.convert_page._accept_files(paths)
    QApplication.processEvents()
    return [p.resolve() for p in paths]


def click(row, modifiers=Qt.KeyboardModifier.NoModifier, pos=None):
    QTest.mouseClick(row, Qt.MouseButton.LeftButton, modifiers, pos or QPoint(200, 20))


def selected(window):
    return [p.name for p in window.convert_page.input.selection.selected]


def test_screen_and_rows_follow_the_mockup(window, tmp_path):
    add_files(window, tmp_path, "a.mid", "b.mid")
    screen = window.convert_page.input
    origin = screen.mapTo(window, QPoint(0, 0))
    assert QRect(origin, screen.size()) == QRect(32, 139, 556, 631)  # лицо блока 556×628 в (32, 140)
    rows = screen.rows()
    first = rows[0].mapTo(window, QPoint(0, 0))
    second = rows[1].mapTo(window, QPoint(0, 0))
    assert (first.x(), first.y(), rows[0].width(), rows[0].height()) == (53, 199, 514, 60)
    assert second.y() - first.y() == 68  # строка 60 + зазор 8
    head = screen.header.mapTo(window, QPoint(0, 0))
    assert (head.x(), head.y(), screen.header.height()) == (53, 161, 30)
    zone = screen.drop_zone.mapTo(window, QPoint(0, 0))
    assert zone.y() == second.y() + 60 + 12  # зазор 8 + margin-top 4
    row = rows[0]
    assert (row.led_rect().x(), row.line_rect().x(), row.remove_rect().size().toTuple()) == (23, 37, (22, 22))


def test_states_lines_and_totals(tmp_path):
    from remap.core.convert import ConversionReport
    ok = FileResult(tmp_path / "a.mid", tmp_path / "a_remapped.mid", report=ConversionReport())
    warn = FileResult(tmp_path / "b.mid", tmp_path / "b_remapped.mid", report=ConversionReport(warnings=["W1"]))
    err = FileResult(tmp_path / "c.mid", tmp_path / "c_remapped.mid", error="Not a MIDI file", details="OSError")
    assert [file_state(r) for r in (None, ok, warn, err)] == ["ready", "ok", "warn", "error"]
    assert state_tip(None) is None and state_tip(err) == ("Not converted", "Not a MIDI file")
    assert state_tip(warn)[0] == "Converted with warnings" and "W1" in state_tip(warn)[1]
    assert totals_parts([ok, warn, err]) == [("2 CONVERTED", "ok"), ("1 WITH WARNINGS", "warn"), ("1 FAILED", "error")]
    assert totals_parts([ok]) == [("1 CONVERTED", "ok")]  # нули предупреждений и ошибок не пишутся


def test_explorer_selection_with_mouse_and_ctrl_a(window, tmp_path):
    add_files(window, tmp_path, "a.mid", "b.mid", "c.mid", "d.mid")
    rows = window.convert_page.input.rows()
    click(rows[1])
    assert selected(window) == ["b.mid"] and rows[1].selected and not rows[0].selected
    click(rows[3], SHIFT)
    assert selected(window) == ["b.mid", "c.mid", "d.mid"]
    click(rows[2], CTRL)
    assert selected(window) == ["b.mid", "d.mid"]
    click(rows[0], CTRL | SHIFT)  # якорь — c (последний Ctrl+клик): добавить a..c
    assert selected(window) == ["a.mid", "b.mid", "c.mid", "d.mid"]
    click(rows[0])
    assert selected(window) == ["a.mid"]
    body = window.convert_page.input.list.widget()
    QTest.mouseClick(body, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     QPoint(10, rows[0].height() + 4))  # зазор между строками — пустое место
    assert selected(window) == []
    QTest.keyClick(window, Qt.Key.Key_A, CTRL)
    assert selected(window) == ["a.mid", "b.mid", "c.mid", "d.mid"]


def test_delete_and_remove_button_act_on_selection(window, tmp_path):
    add_files(window, tmp_path, "a.mid", "b.mid", "c.mid", "d.mid")
    page = window.convert_page
    rows = page.input.rows()
    click(rows[0])
    click(rows[1], CTRL)
    x = rows[3].remove_rect().center().toPoint()
    assert "Remove from the list" in rows[3].tooltip_at(rows[3].remove_rect().center())
    click(rows[3], pos=x)  # × у невыделенной строки — только она
    assert [p.name for p in page.sources] == ["a.mid", "b.mid", "c.mid"] and selected(window) == ["a.mid", "b.mid"]
    rows = page.input.rows()
    assert "Delete" in rows[0].tooltip_at(rows[0].remove_rect().center())
    click(rows[0], pos=rows[0].remove_rect().center().toPoint())  # × у выделенной — все выделенные
    assert [p.name for p in page.sources] == ["c.mid"] and page.status.text() == "Removed 2 files."
    QTest.keyClick(window, Qt.Key.Key_Delete)  # ничего не выделено — ничего не происходит
    assert [p.name for p in page.sources] == ["c.mid"]
    click(page.input.rows()[0])
    QTest.keyClick(window, Qt.Key.Key_Delete)
    assert page.sources == [] and page.status.text() == "Cleared."


def test_details_acts_on_its_own_row_and_esc_only_clears_selection(window, tmp_path):
    _a, b = add_files(window, tmp_path, "a.mid", "b.mid")
    page = window.convert_page
    page.convert()
    rows = page.input.rows()
    shown = []
    page.input._on_details = shown.append  # окно Details не открываем
    click(rows[0])
    click(rows[1], pos=rows[1].details_rect().center().toPoint())
    assert shown == [b] and selected(window) == ["a.mid"]  # DETAILS не трогает выделение
    assert not page.input.totals.isHidden()
    page.output_screen.card_pressed(page.output_screen.cards()[0].path, Qt.KeyboardModifier.NoModifier)
    QTest.keyClick(window, Qt.Key.Key_Escape)  # Esc снимает выделение в обоих экранах, список остаётся
    assert len(page.sources) == 2 and selected(window) == [] and page.output_screen.selection.selected == []
    assert not page.input.totals.isHidden()
