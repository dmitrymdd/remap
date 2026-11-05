"""Экран нот вкладки Maps: геометрия по макету (Maps.dc.html), выделение как в Проводнике, Delete, Esc, Ctrl+A."""
import pytest
from PySide6.QtCore import QEvent, QPoint, QRect, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from remap.core.notemap import NoteMap
from remap.storage import Storage
from remap.ui.main_window import PAGE_MAPS, MainWindow
from remap.ui.maps_text import COL_NAME, TEMPLATE, USER, MapRef

pytestmark = pytest.mark.ui

CTRL, SHIFT = Qt.KeyboardModifier.ControlModifier, Qt.KeyboardModifier.ShiftModifier
NONE = Qt.KeyboardModifier.NoModifier
KIT = {35: "Kick: Hit", 36: "Kick: Open", 38: "Snare: Center", 40: "Snare: Rimshot", 42: "Hi-Hat: Closed",
       46: "Hi-Hat: Open"}


@pytest.fixture
def window(app, tmp_path):
    storage = Storage(tmp_path / "store")
    storage.save_map(NoteMap("Kit", dict(KIT)))
    w = MainWindow(storage)
    w.resize(900, 800)
    w.show()
    w.show_page(PAGE_MAPS)
    page = w.maps_page
    page.confirm = lambda *a: page.asked.append(a[1]) or False
    page.asked = []
    page.ask_save_changes = lambda: "discard"
    page.select(MapRef(USER, "Kit"))
    QApplication.processEvents()
    yield w
    w.close()
    w.deleteLater()


def at(window, widget):
    return widget.mapTo(window, QPoint(0, 0))


def row_point(page, note):
    view = page.notes.table
    rect = view.visualRect(page.proxy.mapFromSource(page.model.note_index(note, COL_NAME)))
    return QPoint(rect.left() + 40, rect.center().y())


def click(page, note, modifiers=NONE):
    QTest.mouseClick(page.notes.table.viewport(), Qt.MouseButton.LeftButton, modifiers, row_point(page, note))


def key(page, k, modifiers=NONE, text=""):
    QApplication.sendEvent(page.notes.table, QKeyEvent(QEvent.Type.KeyPress, k, modifiers, text))


def selected(page):
    return page.notes.selection.selected


# --- геометрия ---

def test_screens_header_rows_and_totals_follow_the_mockup(window):
    page = window.maps_page
    notes, lst = page.notes, page.list
    # блоки 260×628 в (32, 140) и 564×628 в (304, 140); виджет блока — +1 px сверху и +2 снизу под внешние линии
    assert QRect(at(window, lst), lst.size()) == QRect(32, 139, 260, 631)
    assert QRect(at(window, notes), notes.size()) == QRect(304, 139, 564, 631)
    screen = notes.screen
    assert QRect(at(window, screen), screen.size()) == QRect(310, 146, 552, 616)  # поле блока 6
    # содержимое 522 px от 325 (поле экрана 14 + рамка): поиск 34, зазор 10, заголовок 28 + линия, итоги 26 + линия
    search, header, view, totals = notes.search, notes.header, notes.table, notes.totals
    assert (at(window, search).x(), at(window, search).y(), search.height()) == (325, 161, 34)
    check = notes.named_only
    assert at(window, check).x() + check.width() == 847  # флажок у правого края содержимого
    assert at(window, check).x() + 2 - (at(window, search).x() + search.width()) == 14  # зазор 14 (запас под кольцо 2)
    assert (at(window, header).x(), at(window, header).y(), header.width(), header.height()) == (325, 205, 522, 29)
    assert (at(window, view).y(), view.height()) == (234, 486)
    assert (at(window, totals).y(), totals.height(), at(window, totals).y() + totals.height()) == (720, 27, 747)
    # дорожка полосы прокрутки: 86 px от внутреннего края экрана, 3 px в 5 px от правого внутреннего края
    page.select(MapRef(TEMPLATE, "Superior Drummer 3"))
    QApplication.processEvents()
    bar = notes.bar
    assert bar.isVisible() and at(window, bar).y() == 146 + 1 + 86 and bar.height() == 616 - 2 - 86 - 60
    assert at(window, bar).x() + bar.handle_rect().left() == 310 + 552 - 1 - 5 - 3


def test_row_heights_group_header_and_note_columns(window):
    page = window.maps_page
    view = page.notes.table
    kinds = [page.proxy.source_row(r).is_header for r in range(page.proxy.rowCount())]
    assert kinds[:3] == [True, False, False]  # KICK, 35, 36
    assert [view.rowHeight(r) for r in range(3)] == [30, 28, 28]
    assert view.columnWidth(0) == 64 and view.columnWidth(1) == 522 - 64
    assert view.columnSpan(0, 0) == 2 and view.columnSpan(1, 0) == 1


# --- выделение ---

def test_click_ctrl_shift_select_like_explorer(window):
    page = window.maps_page
    click(page, 35)
    assert selected(page) == [35]
    click(page, 40, SHIFT)  # диапазон от якоря — через заголовок SNARE, но заголовки не выделяются
    assert selected(page) == [35, 36, 38, 40]
    click(page, 46, CTRL)
    assert selected(page) == [35, 36, 38, 40, 46]
    click(page, 36, CTRL)
    assert selected(page) == [35, 38, 40, 46]
    click(page, 42, CTRL | SHIFT)  # Ctrl+Shift — диапазон от якоря (36) добавляется
    assert selected(page) == [35, 36, 38, 40, 42, 46]
    # клик по заголовку группы сворачивает её: скрытые ноты из выделения уходят, остальное не меняется
    head = page.notes.table.visualRect(page.proxy.index(0, 0)).center()
    QTest.mouseClick(page.notes.table.viewport(), Qt.MouseButton.LeftButton, NONE, head)
    assert page.proxy.source_row(0).group in page.proxy.collapsed
    page.proxy.toggle_group(page.proxy.source_row(0).group)  # вернуть раскрытой
    assert selected(page) == [38, 40, 42, 46]
    # клик по пустому месту под строками — снять
    QTest.mouseClick(page.notes.table.viewport(), Qt.MouseButton.LeftButton, NONE, QPoint(200, 470))
    assert selected(page) == []


def test_ctrl_a_esc_and_collapsed_groups(window):
    page = window.maps_page
    kick = page.proxy.source_row(0).group
    page.proxy.toggle_group(kick)  # свёрнутая группа: её ноты в Ctrl+A не входят
    key(page, Qt.Key.Key_A, CTRL, "\x01")
    assert selected(page) == [38, 40, 42, 46]
    key(page, Qt.Key.Key_Escape)
    assert selected(page) == []
    page.proxy.toggle_group(kick)
    key(page, Qt.Key.Key_A, CTRL, "\x01")
    assert selected(page) == [35, 36, 38, 40, 42, 46]


def test_selection_survives_sort_and_filter_for_visible_rows(window):
    page = window.maps_page
    click(page, 36)
    click(page, 42, CTRL)
    page.sort_by(0)  # по номеру
    assert selected(page) == [36, 42]
    page.notes.search.setText("hat")
    assert selected(page) == [42]
    page.notes.search.setText("")
    assert selected(page) == [42]  # 36 пропадала из вида — выделение с неё снято


def test_delete_clears_selected_names_in_one_step(window):
    page = window.maps_page
    edits = []
    page.model.edited.connect(lambda: edits.append(1))
    click(page, 38)
    click(page, 40, SHIFT)
    click(page, 46, CTRL)
    key(page, Qt.Key.Key_Delete)
    assert edits == [1] and page.dirty
    assert set(page.work.names) == {35, 36, 42}


def test_esc_while_editing_cancels_edit_first(window):
    from PySide6.QtWidgets import QLineEdit
    page = window.maps_page
    click(page, 35)
    click(page, 36, CTRL)
    key(page, Qt.Key.Key_F2)
    QApplication.processEvents()
    editor = page.notes.table.findChild(QLineEdit)
    assert editor is not None and editor.isVisible() and editor.text() == "Kick: Open"
    QApplication.sendEvent(editor, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, NONE))
    QApplication.processEvents()
    assert page.notes.table.delegate.edit_index is None and selected(page) == [35, 36]  # выделение осталось
    key(page, Qt.Key.Key_Escape)
    assert selected(page) == []
    key(page, Qt.Key.Key_Return)  # Enter — правка текущей строки
    QApplication.processEvents()
    assert page.notes.table.delegate.edit_index is not None


def test_arrow_keys_move_and_shift_extends(window):
    page = window.maps_page
    click(page, 36)
    key(page, Qt.Key.Key_Down)  # через заголовок SNARE
    assert selected(page) == [38]
    key(page, Qt.Key.Key_Down, SHIFT)
    assert selected(page) == [38, 40]


def test_template_delete_asks_duplicate_and_map_change_clears_selection(window):
    page = window.maps_page
    click(page, 35)
    page.select(MapRef(TEMPLATE, "EZdrummer 3"))
    assert selected(page) == []
    page.notes.table.select_note(36)
    key(page, Qt.Key.Key_Delete)
    assert page.asked == ["Duplicate to My Maps to edit?"] and 36 in page.work.names
