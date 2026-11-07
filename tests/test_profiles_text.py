"""Тексты подсказок Profiles (ui/profiles_text.py): чистый Python, без Qt."""
from remap.core.notemap import NoteMap
from remap.core.profile import RemapProfile, Rule
from remap.ui.cable_layout import DELETE, KEEP, MIXED, UNASSIGNED, Cable, SourceRow, TargetRow
from remap.ui.profiles_text import (
    HAND_REMOVED_TIP, HAND_SET_TIP, cable_tip, hand_text, not_write_to, source_tip, target_missing_tip,
    target_number_tip, target_tip, tip_lines, with_name,
)

SRC = NoteMap("S", {36: "Kick", 38: "Snare", 40: "Snare", 42: "Hat"})
TGT = NoteMap("T", {36: "Kick: Hit", 38: "Snare: Center", 39: "Snare: Center", 50: "Tom"}, primary={39})


def row(notes, state=UNASSIGNED, **kw):
    base = {"name": SRC.names.get(notes[0]), "connected": False, "block": None, "y": 0}
    return SourceRow(notes=tuple(notes), state=state, **{**base, **kw})


def target(notes, label="Snare: Center", write_to=None):
    return TargetRow(slot="t", label=label, notes=tuple(notes), write_to=write_to, in_map=True, y=0, height=1)


def cable(notes, t, dst, suggested=False):
    return Cable(tuple(notes), dst, 0, t, suggested=suggested)


def profile(rules=None):
    return RemapProfile("P", SRC, TGT, rules or {})


def test_tip_lines_and_with_name_keep_three_lines():
    assert tip_lines("h", ["", "a"], "act") == "h\na\nact"
    assert tip_lines("h", ["a", "b"], "act") == "h\na · b\nact"
    assert with_name("Name", "h\na\nact") == "Name\nh · a\nact"


def test_hand_text_only_with_overrides():
    over = {36: Rule.map_to(36), 38: None}
    assert hand_text((36,), None, connected=True) == ""
    assert hand_text((36,), over, connected=True) == HAND_SET_TIP
    assert hand_text((36, 40), over, connected=True) == "Set by hand (36)"
    assert hand_text((38,), over, connected=False) == HAND_REMOVED_TIP
    assert hand_text((38, 40), over, connected=False) == "Removed by hand (38)"
    assert hand_text((40,), over, connected=False) == ""


def test_not_write_to():
    assert not_write_to(TGT, 38) == "Not the Write to note (39)"
    assert not_write_to(TGT, 39) == not_write_to(TGT, 99) == not_write_to(None, 38) == ""


def test_source_tip_cases():
    p = profile({38: Rule.map_to(38)})
    assert source_tip(row([38], connected=True), [], p, None, None, "target", False) == (
        "Note 38 · D1  →  38 Snare: Center\nNot the Write to note (39)\nRight-click: remove")
    assert source_tip(row([36], DELETE), [], p, None, None, "target", False) == (
        "Note 36 · C1\nDeleted from converted files\nRight-click: restore")
    assert source_tip(row([36], KEEP), [], p, None, None, "target", False) == (
        "Note 36 · C1\nKept on the same number: Kick: Hit\nRight-click: delete")
    assert source_tip(row([42], KEEP), [], p, None, None, "source", False) == (
        "Note 42 · F#1\nKept on the same number (not in the source map)\nRight-click: delete")
    assert source_tip(row([42], block=UNASSIGNED), [], p, None, None, "target", True) == (
        "Note 42 · F#1\nNo rule here: kept on the same number\nRight-click: delete · Double-click: same number")
    assert source_tip(row([38, 40], MIXED), [], p, None, None, "target", False) == (
        "Notes 38 · D1, 40 · E1\nDifferent rules: shown one by one\nRight-click: delete")
    assert source_tip(row([40], child=True), ["Issue"], p, None, None, "target", False) == (
        "Note 40 · E1 · Snare\nIssue\nRight-click: delete")


def test_source_tip_suggested_and_hand_set():
    p = profile()
    t = target([38, 39])
    assert source_tip(row([38], suggested=True), [], p, cable((38,), t, None, suggested=True),
                      None, "target", False) == (
        "Note 38 · D1  →  Snare: Center\nSuggested, needs a Write to note: Apply skips it")
    assert source_tip(row([38], suggested=True), [], p, cable((38,), t, 39, suggested=True),
                      None, "target", False) == "Note 38 · D1  →  39 Snare: Center\nSuggested: apply in the bar above"
    p = profile({36: Rule.map_to(36)})
    assert source_tip(row([36], connected=True), [], p, None, {36: Rule.map_to(36)}, "source", True) == (
        f"Note 36 · C1  →  36 Kick: Hit\n{HAND_SET_TIP}\nRight-click: remove")


def test_cable_tip():
    p = profile({36: Rule.map_to(36), 38: Rule.map_to(38)})
    assert cable_tip(cable((36,), target([36], "Kick: Hit"), 36), p, None) == (
        "36 Kick  →  36 Kick: Hit\nNames differ\nRight-click: remove")
    assert cable_tip(cable((38, 40), target([38, 39]), 38), p, {38: Rule.map_to(38)}) == (
        "38, 40 Snare  →  38 Snare: Center\nNames differ · Not the Write to note (39) · Set by hand (38)\n"
        "Right-click: remove")
    bare = RemapProfile("P", None, None, {5: Rule.map_to(6)})
    assert cable_tip(cable((5,), target([6], ""), 6), bare, None) == "5  →  6\nRight-click: remove"


def test_target_tips():
    assert target_missing_tip(target([50]), True, "target") == "Note 50 · D2\nNot in the target map"
    assert target_missing_tip(target([50]), False, "source") == "Note 50 · D2\nNo source map"
    assert target_tip(target([36], "Kick: Hit"), "") == "Note 36 · C1"
    assert target_tip(target([38, 39], write_to=39), "+1") == (
        "Notes 38 · D1, 39 · D#1\nWrite to: 39 · Click +1: choose the Write to")
    assert target_tip(target([38, 39]), "…") == "Notes 38 · D1, 39 · D#1\nWrite to: not chosen · Click …: choose the Write to"
    assert target_number_tip(target([38, 39], write_to=39), 39) == "Note 39 · D#1 · Snare: Center\nWrite to"
    assert target_number_tip(target([38, 39], write_to=39), 38) == "Note 38 · D1 · Snare: Center"
