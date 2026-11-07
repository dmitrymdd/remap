"""Выделение строк пула «Unassigned» и колонки «from» (`CableEditor.pool_sel` / `from_sel`, модель `ui/selection.py`):
жесты мыши, Ctrl+A / Esc, сброс, действия над выделением."""
import pytest

pytest.importorskip("PySide6")
pytestmark = pytest.mark.ui

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from remap.core.profile import Rule
from remap.ui.cable_layout import DELETE
from remap.ui.main_window import PAGE_PROFILES, MainWindow

from test_ui_profiles import EZD3, SD3, new_profile, stub_dialogs

NO, SHIFT, CTRL = (Qt.KeyboardModifier.NoModifier, Qt.KeyboardModifier.ShiftModifier,
                   Qt.KeyboardModifier.ControlModifier)
LEFT = Qt.MouseButton.LeftButton


@pytest.fixture
def window(app, storage):
    w = MainWindow(storage)
    w.show_page(PAGE_PROFILES)
    stub_dialogs(w.profiles_page)
    w.resize(1300, 900)
    w.show()
    yield w
    w.close()
    w.deleteLater()


def editor(window, accept=False):
    """Новый профиль EZD3 → SD3 (accept — с подключёнными подсказками, чтобы колонка «from» была не пустой)."""
    page = window.profiles_page
    new_profile(page)
    if accept:
        page.apply_suggestions()
    page.dismiss_suggestions()
    QApplication.processEvents()
    return page, page.cables


def rows(ed, k=4):
    return [i for i in ed.pool_rows if not i.model.expanded and not i.model.child][:k]


def press(ed, row, mods=NO, view=None):
    ed._press_row(view or ed.pool, row, mods, row.rect.center())


def notes(*items):
    return {n for i in items for n in i.notes}


def send(ed, kind, item, mods=NO, buttons=LEFT, shift=None):
    """Событие мыши в viewport пула над строкой item (сдвиг shift)."""
    vp = ed.pool.viewport()
    pos = QPointF(ed.pool.mapFromScene(item.rect.center())) + (shift or QPointF(0, 0))
    button = Qt.MouseButton.NoButton if kind == QEvent.Type.MouseMove else LEFT
    ev = QMouseEvent(kind, pos, QPointF(vp.mapToGlobal(pos.toPoint())), button, buttons, mods)
    QApplication.sendEvent(vp, ev)


def test_click_ctrl_shift_and_ctrl_shift_follow_explorer(window):
    _page, ed = editor(window)
    a, b, c, d = rows(ed)
    press(ed, a)
    press(ed, c, SHIFT)
    assert set(ed.selected_notes()) == notes(a, b, c)
    press(ed, b, CTRL)  # снять одну, якорь — на ней
    assert set(ed.selected_notes()) == notes(a, c) and not b.selected
    press(ed, d, SHIFT)  # Shift ЗАМЕНЯЕТ выделение диапазоном от якоря
    assert set(ed.selected_notes()) == notes(b, c, d) and not a.selected
    press(ed, a, CTRL | SHIFT)  # Ctrl+Shift ДОБАВЛЯЕТ диапазон
    assert set(ed.selected_notes()) == notes(a, b, c, d)
    press(ed, c)
    ed.view_release(ed.pool, QMouseEvent(QEvent.Type.MouseButtonRelease, QPointF(), QPointF(), LEFT,
                                         Qt.MouseButton.NoButton, NO))
    assert set(ed.selected_notes()) == notes(c)  # клик без сдвига по выделенной — «только эта»


def test_alias_group_row_is_one_key(window):
    _page, ed = editor(window)
    group = next(i for i in ed.pool_rows if len(i.notes) > 1 and not i.model.expanded)
    other = next(i for i in ed.pool_rows if i is not group and not i.model.child)
    press(ed, group)
    press(ed, other, CTRL)
    assert ed.pool_sel.selected.count(("alias", group.model.alias)) == 1
    assert set(ed.selected_notes()) == notes(group, other)


def test_ctrl_click_that_deselects_does_not_start_a_drag(window):
    _page, ed = editor(window)
    a, b = rows(ed, 2)
    press(ed, a)
    send(ed, QEvent.Type.MouseButtonPress, b, CTRL)  # добавить
    send(ed, QEvent.Type.MouseButtonRelease, b, CTRL, Qt.MouseButton.NoButton)
    send(ed, QEvent.Type.MouseButtonPress, b, CTRL)  # снять
    assert not b.selected
    send(ed, QEvent.Type.MouseMove, b, CTRL, LEFT, QPointF(40, 0))
    assert not ed.dragging
    send(ed, QEvent.Type.MouseButtonRelease, b, CTRL, Qt.MouseButton.NoButton, QPointF(40, 0))
    # Ctrl-нажатие, которое добавило строку, тащит всё выделение
    send(ed, QEvent.Type.MouseButtonPress, b, CTRL)
    send(ed, QEvent.Type.MouseMove, b, CTRL, LEFT, QPointF(40, 0))
    assert ed.dragging and set(ed._drag.notes) == notes(a, b)
    ed.cancel_drag()


def test_selection_lives_in_one_column(window):
    _page, ed = editor(window, accept=True)
    a, b = rows(ed, 2)
    src = ed.scene_rows[:2]
    press(ed, a)
    press(ed, b, CTRL)
    press(ed, src[0], CTRL, view=ed.view)  # любой щелчок в другой колонке снимает выделение первой
    assert set(ed.selected_notes()) == notes(src[0]) and not a.selected and ed.pool_sel.anchor is None
    press(ed, src[1], SHIFT, view=ed.view)
    assert set(ed.selected_notes()) == notes(*src)
    press(ed, a, SHIFT)  # якоря в пуле нет: как обычный клик
    assert set(ed.selected_notes()) == notes(a) and not ed.from_sel.selected


def test_ctrl_a_takes_last_clicked_column_skips_collapsed_groups_and_esc_clears(window):
    page, ed = editor(window, accept=True)
    key = next(iter(ed.pool_headers))
    hidden = set(ed.pool_headers[key].header.notes)
    ed.toggle_pool(key)  # свернуть группу: её строк в выделении быть не может
    QTest.keyClick(window, Qt.Key.Key_A, CTRL)
    pool = {n for i in ed.pool_rows for n in i.notes}
    assert pool and set(ed.selected_notes()) == pool and not hidden & pool
    press(ed, ed.scene_rows[0], view=ed.view)
    page._select_all()
    assert set(ed.selected_notes()) == {n for i in ed.scene_rows for n in i.notes} and not ed.pool_sel.selected
    QTest.keyClick(window, Qt.Key.Key_Escape)
    assert not ed.selection


def test_profile_direction_and_map_change_reset_selection_and_anchor(window):
    page, ed = editor(window)
    for change in (lambda: page.choose_map("target", EZD3), lambda: new_profile(page, "Q", SD3, EZD3),
                   page.toggle_direction):
        if ed.pool_rows:
            press(ed, ed.pool_rows[0])
        else:  # все ноты ушли на сцену подсказками
            press(ed, ed.scene_rows[0], view=ed.view)
        assert ed.selection and (ed.pool_sel.anchor is not None or ed.from_sel.anchor is not None)
        change()
        assert not ed.selection and ed.pool_sel.anchor is None and ed.from_sel.anchor is None


def test_right_click_on_selection_strikes_all_in_one_undo_step(window):
    page, ed = editor(window)
    a, b, c, d = rows(ed)
    press(ed, a)
    press(ed, c, SHIFT)
    before = dict(page.work.rules)
    ed.right_click(b)
    QApplication.processEvents()
    assert all(page.work.rules.get(n) == Rule.delete() for n in notes(a, b, c))
    assert d.notes[0] not in page.work.rules
    page.undo()
    assert page.work.rules == before
    ed.right_click(next(i for i in ed.pool_rows if set(i.notes) == set(d.notes)))  # не выделена — только она
    assert {n for n, r in page.work.rules.items() if r == Rule.delete()} == set(d.notes)


def test_double_click_on_selection_connects_all_same_numbers_in_one_undo_step(window):
    page, ed = editor(window)
    tgt = page.work.target_map.names
    a, b, c = [i for i in rows(ed, 30) if all(n in tgt for n in i.notes)][:3]
    press(ed, a)
    press(ed, b, CTRL)
    press(ed, c, CTRL)
    before = dict(page.work.rules)
    # первое нажатие двойного клика сводит выделение к строке при отпускании — двойной его возвращает
    send(ed, QEvent.Type.MouseButtonPress, b)
    send(ed, QEvent.Type.MouseButtonRelease, b, buttons=Qt.MouseButton.NoButton)
    send(ed, QEvent.Type.MouseButtonDblClick, b)
    send(ed, QEvent.Type.MouseButtonRelease, b, buttons=Qt.MouseButton.NoButton)
    QApplication.processEvents()
    assert all(page.work.rules[n] == Rule.map_to(n) for n in notes(a, b, c))
    page.undo()
    assert page.work.rules == before


def test_dragging_a_pool_header_skips_struck_notes(window):
    page, ed = editor(window)
    header = next(h for h in ed.pool_headers.values() if len(h.header.notes) > 1)
    struck = header.header.notes[0]
    page.toggle_strike([struck])
    QApplication.processEvents()
    header = next(h for h in ed.pool_headers.values() if h.header.key == header.header.key)
    assert any(i.model.state == DELETE for i in ed.pool_rows if struck in i.notes)
    send(ed, QEvent.Type.MouseButtonPress, header)
    send(ed, QEvent.Type.MouseMove, header, buttons=LEFT, shift=QPointF(40, 0))
    assert ed.dragging and struck not in ed._drag.notes and ed._drag.notes
    ed.cancel_drag()
