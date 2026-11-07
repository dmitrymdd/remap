"""Подсказки вкладки Profiles через настоящий UI: снимок всех подсказок строк, плашек цели и кабелей в нескольких
состояниях профиля (→ и ←, ручные правки, keep, delete, не Write to, без целевой карты) совпадает с эталоном
`tests/fixtures/profiles_tips_golden.json` побайтно. Эталон снят до переноса текстов в `ui/profiles_text.py`;
перезаписать — `REMAP_WRITE_TIPS=1` (только при сознательной смене текстов)."""
import json
import os
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytestmark = pytest.mark.ui

from PySide6.QtWidgets import QApplication

from remap.core.notemap import articulations, primary_note
from remap.core.profile import REVERSE, Rule
from remap.ui.profiles_text import (
    DELETED_TIP, HAND_REMOVED_TIP, HAND_SET_TIP, KEPT_TIP, NAMES_DIFFER_TIP, REMOVE_ACTION, RESTORE_ACTION,
    REVERSE_UNASSIGNED_TIP,
)
from remap.ui.main_window import MainWindow, PAGE_PROFILES

from test_ui_profiles import EZD3, SD3, new_profile, stub_dialogs

GOLDEN = Path(__file__).resolve().parent / "fixtures" / "profiles_tips_golden.json"


def base(item) -> tuple[str, str | None]:
    """Подсказки строки без полного имени: добавится ли оно, зависит от ширины шрифта (загружен ли он уже)."""
    return item.base_tips or (item.tip_text, item.part_tips.get("head"))


def snapshot(ed) -> dict[str, str]:
    """Все подсказки редактора: строки пула и «from», плашки цели (с частями раскрытых групп), кабели."""
    out = {}
    for kind, items in (("pool", ed.pool_rows), ("from", ed.scene_rows)):
        for item in items:
            out[f"{kind} {item.model.y} {item.model.note}"] = base(item)[0]
    for slot, item in ed.target_items.items():
        out[f"to {slot}"], head = base(item)
        for part, text in item.part_tips.items():
            out[f"to {slot} [{part}]"] = head if part == "head" else text
    for item in ed.cable_items + ed.suggestion_items:
        c = item.cable
        out[f"cable {c.notes} {c.dst} {c.suggested}"] = item.tip_text
    return out


@pytest.fixture
def page(app, storage):
    w = MainWindow(storage)
    w.show_page(PAGE_PROFILES)
    stub_dialogs(w.profiles_page)
    w.resize(1300, 900)
    w.show()
    yield w.profiles_page
    w.close()
    w.deleteLater()


def scenarios(page) -> dict[str, dict[str, str]]:
    ed = page.cables
    shots = {}
    new_profile(page)  # подсказки ещё не приняты: пунктирные кабели
    QApplication.processEvents()
    shots["suggested"] = snapshot(ed)
    page.apply_suggestions()
    page.dismiss_suggestions()
    page.match_by_number()
    work = page.work
    tgt = work.target_map
    other = next(n for name, notes in articulations(tgt).items() for n in notes
                 if primary_note(tgt, name) not in (None, n))
    free = sorted(work.source_map.names)[::-1]  # их правила перезаписываются
    work.rules[free[0]] = Rule.map_to(other)          # не на Write to
    work.rules[free[1]] = Rule.keep()                 # keep на номер цели
    work.rules[free[2]] = Rule.delete()
    outside = next((n for n in free[3:] if n not in tgt.names), None)
    if outside is not None:
        work.rules[outside] = Rule.keep()             # keep на номер вне целевой карты
    ed.refresh()
    QApplication.processEvents()
    shots["forward"] = snapshot(ed)
    page.set_direction(REVERSE)
    ed = page.cables
    rows = ed.current.scene.source_rows
    cabled = [r for r in rows if r.connected and len(r.notes) == 1]
    bundle = next(r for r in rows if r.connected and len(r.notes) > 1)
    page.work.reverse_overrides = {cabled[0].note: Rule.map_to(cabled[0].note), cabled[1].note: None,
                                   bundle.notes[1]: page.work.effective_reverse()[bundle.notes[1]]}
    ed.refresh()
    QApplication.processEvents()
    shots["reverse"] = snapshot(ed)
    page.set_direction("forward")
    page.answers["text"] = ["NoTarget"]
    page.new_profile()
    assert page.choose_map("source", EZD3)
    page.work.rules = {n: Rule.map_to(n) for n in sorted(page.work.source_map.names)[:4]}
    ed.refresh()
    QApplication.processEvents()
    shots["no target"] = snapshot(page.cables)
    assert SD3  # цель второго профиля намеренно не выбрана
    return shots


def test_profiles_tooltips_match_golden(page):
    shots = scenarios(page)
    if os.environ.get("REMAP_WRITE_TIPS"):
        GOLDEN.write_text(json.dumps(shots, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    assert shots == json.loads(GOLDEN.read_text(encoding="utf-8"))


def test_profiles_tooltips_cover_representative_cases(page):
    """Эталон действительно содержит нужные случаи (иначе сравнение с ним ничего не доказывает)."""
    shots = scenarios(page)
    fwd, rev = "\n".join(shots["forward"].values()), "\n".join(shots["reverse"].values())
    assert "Suggested: apply in the bar above" in "\n".join(shots["suggested"].values())
    assert DELETED_TIP in fwd and RESTORE_ACTION in fwd and KEPT_TIP in fwd and REMOVE_ACTION in fwd
    assert NAMES_DIFFER_TIP in fwd and "Not the Write to note (" in fwd and "  →  " in fwd
    assert "Write to: " in fwd and "· Click " in fwd
    assert HAND_SET_TIP in rev and HAND_REMOVED_TIP in rev
    assert REVERSE_UNASSIGNED_TIP in rev or "Right-click: delete" in rev
    assert "No target map" in "\n".join(shots["no target"].values())
