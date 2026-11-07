"""Выделение как в Проводнике (`ui/selection.py`, без Qt)."""
from remap.ui.selection import Selection


def sel(*selected, anchor=None):
    s = Selection("abcdef")
    for k in selected:
        s.toggle(k)
    s.anchor = anchor
    return s


def test_click_selects_only_this_and_sets_anchor():
    s = sel("a", "c")
    s.press("d")
    assert s.selected == ["d"] and s.anchor == "d"


def test_ctrl_click_toggles_and_moves_anchor():
    s = sel("a")
    s.press("c", ctrl=True)
    assert s.selected == ["a", "c"] and s.anchor == "c"
    s.press("a", ctrl=True)
    assert s.selected == ["c"] and s.anchor == "a"


def test_shift_click_replaces_with_range_from_anchor_which_stays():
    s = Selection("abcdef")
    s.press("b")
    s.press("e", shift=True)
    assert s.selected == ["b", "c", "d", "e"] and s.anchor == "b"
    s.press("a", shift=True)  # в другую сторону от того же якоря
    assert s.selected == ["a", "b"]


def test_ctrl_shift_click_adds_range():
    s = Selection("abcdef")
    s.press("a")
    s.press("e", ctrl=True)       # якорь — e
    s.press("f", ctrl=True, shift=True)
    assert s.selected == ["a", "e", "f"]


def test_shift_without_anchor_acts_as_click():
    s = Selection("abc")
    s.press("b", shift=True)
    assert s.selected == ["b"] and s.anchor == "b"
    t = Selection("abc")
    t.press("c", ctrl=True, shift=True)
    assert t.selected == ["c"] and t.anchor == "c"


def test_select_all_and_clear():
    s = Selection("abc")
    s.select_all()
    assert s.selected == ["a", "b", "c"] and len(s) == 3
    s.clear()
    assert s.selected == [] and len(s) == 0


def test_set_items_keeps_selection_of_remaining_items_in_new_order():
    s = sel("b", "d", anchor="d")
    s.set_items("dcb")
    assert s.selected == ["d", "b"] and s.anchor == "d"
    s.set_items("cb")
    assert s.selected == ["b"] and s.anchor is None


def test_targets_selected_row_acts_on_all_selected_else_only_itself():
    s = sel("a", "c")
    assert s.targets("c") == ["a", "c"]
    assert s.targets("b") == ["b"]


def test_reset_clears_selection_and_anchor_so_shift_acts_as_click():
    s = sel("a", "c", anchor="c")
    s.reset()
    assert s.selected == [] and s.anchor is None
    s.extend("d")
    assert s.selected == ["d"] and s.anchor == "d"
