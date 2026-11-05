"""Модель обратной схемы на настоящих данных и настоящей странице редактора: переход с формата 2 (эталон снят старым
кодом), случайные последовательности правок в обе стороны с инвариантами, регрессии найденных багов.

Хранилище только временное. Копии профилей лежат в tests/fixtures; tests/fixtures/reverse_golden.json снят со старой
модели скриптом Claude outputs/redesign-4-1-model/make_golden.py и руками не правится.
"""
import copy
import hashlib
import json
import os
import random
from collections import defaultdict
from pathlib import Path

import mido
import pytest

from remap.core import FORWARD, REVERSE, RemapProfile, Rule, convert
from remap.core.notemap import NoteMap, articulations, normalize_name
from remap.core.profile import with_reverse_edit, with_write_to

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "midi" / "Groove 01.mid"
GOLDEN = json.loads((FIXTURES / "reverse_golden.json").read_text(encoding="utf-8"))
HAND_SET = {"ezd3_sd3_saved.json": 22, "gm_sd3_legacy_saved.json": 0, "gp8_ezd3_saved.json": 11, "gp8_gm_saved.json": 8}
M = Rule.map_to


def load(name: str) -> RemapProfile:
    return RemapProfile.from_json((FIXTURES / name).read_text(encoding="utf-8"))


def as_lists(rules: dict[int, Rule]) -> dict[str, list]:
    return {str(k): [v.action, v.dst] for k, v in sorted(rules.items())}


def all_notes_midi(path: Path) -> None:
    midi = mido.MidiFile(type=1, ticks_per_beat=480)
    track = mido.MidiTrack()
    for n in range(128):
        track += [mido.Message("note_on", note=n, velocity=100, time=10),
                  mido.Message("note_off", note=n, velocity=0, time=10)]
    midi.tracks.append(track)
    midi.save(str(path))


def converted_hash(src: Path, dst: Path, profile: RemapProfile, direction: str) -> str:
    convert(src, dst, profile, direction=direction)
    return hashlib.sha256(dst.read_bytes()).hexdigest()


# --- переход на формат 3: всё осталось как было ---

@pytest.mark.parametrize("name", sorted(GOLDEN))
def test_migration_keeps_every_rule_of_the_saved_profile(name):
    p = load(name)
    assert as_lists(p.effective_reverse()) == GOLDEN[name]["reverse"]
    assert as_lists(p.rules) == GOLDEN[name]["forward"]
    assert len(p.reverse_overrides) == HAND_SET[name]
    assert all(rule is not None for rule in p.reverse_overrides.values())  # снятых кабелей в сохранённых нет


@pytest.mark.parametrize("name", sorted(GOLDEN))
def test_format_3_round_trip_keeps_the_migrated_profile(name):
    p = load(name)
    back = RemapProfile.from_json(p.to_json())
    assert back == p and back.to_dict() == p.to_dict() and json.loads(p.to_json())["format"] == 3


@pytest.mark.parametrize("direction", [FORWARD, REVERSE])
@pytest.mark.parametrize("name", sorted(GOLDEN))
def test_conversion_is_byte_identical_to_the_old_model(tmp_path, name, direction):
    p = load(name)
    made = tmp_path / "all.mid"
    all_notes_midi(made)
    for key, src in (("all_notes", made), ("groove01", SAMPLE)):
        assert converted_hash(src, tmp_path / "out.mid", p, direction) == GOLDEN[name]["convert"][f"{key}/{direction}"]


@pytest.mark.parametrize("name", sorted(GOLDEN))
def test_conversion_is_the_same_after_saving_in_format_3(tmp_path, name):
    p = RemapProfile.from_json(load(name).to_json())
    made = tmp_path / "all.mid"
    all_notes_midi(made)
    assert converted_hash(made, tmp_path / "out.mid", p, REVERSE) == GOLDEN[name]["convert"][f"all_notes/{REVERSE}"]


# --- Write to источника в обратном направлении ---

def test_write_to_set_in_reverse_is_not_a_hand_edit_of_notes_that_follow_it():
    src = NoteMap("S", {84: "Bow", 87: "Bow"})
    tgt = NoteMap("T", {85: "Crash"})
    p = RemapProfile("p", src, tgt, {84: M(85), 87: M(85)})
    assert p.effective_reverse() == {85: M(84)}
    q = with_write_to(p.reversed(), 84)  # Write to не было: правила не переводятся
    q.target_map.primary = {87}
    edited = with_reverse_edit(p, q.rules, q.target_map)  # значение то же, что до правки: нота не тронута
    assert edited.reverse_overrides == {} and edited.source_map.primary == {87}
    assert edited.effective_reverse() == {85: M(87)}  # и автоматика идёт за новым Write to
    assert not p.source_map.primary  # исходный профиль не меняется


# --- настоящая страница ---

qt = pytest.mark.ui
TEMPLATES = ("EZdrummer 3", "Superior Drummer 3", "General MIDI", "Guitar Pro 8")


def open_page(app, storage, profile: RemapProfile, *, fast: bool = False):
    """Окно с профилем во временном хранилище. fast — без перестройки сцены: модель та же, шаг в десятки раз дешевле."""
    from remap.ui.main_window import PAGE_PROFILES, MainWindow
    storage.save_profile(profile, profile_id="P", overwrite=True)
    window = MainWindow(storage)
    window.show_page(PAGE_PROFILES)
    page = window.profiles_page
    page.reload_list()
    page.select("P")
    page.confirm = lambda *args: True
    page.ask_save_changes = lambda: "discard"  # окно закрывается с несохранёнными правками
    page.ask_unassigned = lambda notes: set()
    page.ask_write_to = lambda name, notes, preselect=None: notes[0]
    if fast:
        for method in ("refresh", "set_profile", "set_direction", "set_suggestions"):
            setattr(page.cables, method, lambda *args, **kwargs: None)
    return window, page


def oracle(w: RemapProfile) -> dict[int, Rule]:
    """Независимая запись правила: ноты с кабелями (тот же номер, явный Write to источника, наименьшая), ручные правки,
    копии у алиасов цели."""
    over, src, tgt = w.reverse_overrides, w.source_map, w.target_map
    incoming = defaultdict(list)
    for a, rule in w.rules.items():
        if rule.action == "map":
            incoming[rule.dst].append(a)
    out: dict[int, Rule] = {}
    for b, sources in incoming.items():
        if b in over:
            continue
        flagged = [a for a in sources if src is not None and a in src.primary]
        out[b] = M(b if b in sources else min(flagged or sources))
    out.update({n: r for n, r in over.items() if r is not None})
    if tgt is not None:
        by_name = defaultdict(list)
        for n, name in tgt.names.items():
            by_name[normalize_name(name)].append(n)
        for notes in by_name.values():
            with_cables = sorted(n for n in notes if n in incoming)
            if len(notes) < 2 or not with_cables:
                continue
            flagged = [n for n in notes if n in tgt.primary]
            donor = flagged[0] if len(flagged) == 1 and flagged[0] in incoming else with_cables[0]
            for n in notes:
                if n not in incoming and n not in over and donor in out:
                    out[n] = out[donor]
    return dict(sorted(out.items()))


class Fuzz:
    """Случайные правки через методы страницы, инварианты — после каждого шага."""

    def __init__(self, page, storage, seed: int) -> None:
        self.page, self.storage, self.rng = page, storage, random.Random(seed)
        self.undo_trail: list[dict] = []
        self.redo_trail: list[dict] = []
        self.counts: dict[str, int] = defaultdict(int)

    def notes(self, q: RemapProfile) -> list[int]:
        pool = sorted(q.source_map.names) if q.source_map else list(range(128))
        return self.rng.sample(pool, self.rng.randint(1, 3))

    def mapped(self, q: RemapProfile) -> int | None:
        options = sorted(n for n, r in q.rules.items() if r.action == "map")
        return self.rng.choice(options) if options else None

    # --- действия: (вид, ноты, которых действие касается; None — всех) ---
    def op_add(self, q):
        notes = self.notes(q)
        self.page.assign_note(notes, self.rng.choice(sorted(q.target_map.names)))
        return "edit", set(notes)

    def op_add_articulation(self, q):
        notes = self.notes(q)
        self.page.connect_to(notes, "a:" + self.rng.choice(sorted(articulations(q.target_map))))
        return "edit", set(notes)

    def op_cut(self, q):
        n = self.mapped(q)
        if n is None:
            return "skip", set()
        cutting = self.page.direction == REVERSE
        if cutting:  # было ли у ноты вычисленное значение (без её собственной ручной правки)
            bare = copy.deepcopy(self.page.work)
            bare.reverse_overrides.pop(n, None)
            derived = n in oracle(bare)
        self.page.clear_rules([n])
        if cutting:
            w = self.page.work
            assert n not in w.effective_reverse()
            # снят вычисленный кабель — нота ручная и сам он не вернётся; проведённый только в ← — нота снова автоматическая
            assert (w.reverse_overrides[n] is None) if derived else (n not in w.reverse_overrides)
        return "edit", {n}

    def op_strike(self, q):
        notes = self.notes(q)
        self.page.toggle_strike(notes)
        return "edit", set(notes)

    def op_group_drop(self, q):
        notes = self.notes(q)
        self.page.group_drop(notes, self.rng.sample(sorted(q.target_map.names), min(20, len(q.target_map.names))))
        return "edit", set(notes)

    def op_match(self, q):
        self.page.match_by_number()
        return "edit", None

    def op_write_to(self, q):
        several = [v for v in articulations(q.target_map).values() if len(v) > 1]
        if not several:
            return "skip", set()
        self.page.set_write_to(self.rng.choice(self.rng.choice(several)))
        return "write_to", None

    def op_map(self, q):
        from remap.ui.maps_text import TEMPLATE, MapRef
        self.page.choose_map(self.rng.choice(("source", "target")), MapRef(TEMPLATE, self.rng.choice(TEMPLATES)))
        return "map", None

    def step(self) -> None:
        page, rng = self.page, self.rng
        page.set_direction(rng.choice((FORWARD, REVERSE)))
        w = page.work
        direction, before, last = page.direction, w.to_dict(), page._undo[-1] if page._undo else None
        rules, target, over = dict(w.rules), w.target_map, dict(w.reverse_overrides)
        effective = w.effective_reverse()
        action = rng.choices(("add", "add_articulation", "cut", "strike", "group_drop", "match", "write_to", "map", "undo",
                              "redo", "revert", "save"), (20, 12, 16, 8, 6, 2, 6, 1, 10, 6, 2, 3))[0]
        self.counts[action] += 1
        if action == "undo":
            self.check_undo(w)
            return
        if action == "redo":
            self.check_redo()
            return
        if action == "revert":
            page.revert()
            assert page.work.to_dict() == page.base.to_dict() and not page._dirty and not page.save_btn.isEnabled()
            self.note_step(before, last)
            return
        if action == "save":
            assert page.save()
            loaded = self.storage.load_profile("P")
            assert loaded.to_dict() == page.work.to_dict() and loaded.reverse_overrides == page.work.reverse_overrides
            assert not page._dirty
            self.note_step(before, last)
            return
        kind, touched = getattr(self, f"op_{action}")(page._oriented())
        self.note_step(before, last)
        self.check_model()
        w = page.work
        if kind == "map":
            assert w.reverse_overrides == {}
        elif direction == FORWARD:
            assert w.reverse_overrides == over  # ручные ноты правкой → не меняются
            after = w.effective_reverse()
            assert all(after.get(n) == effective.get(n) for n in over)
        else:
            assert w.rules == rules and w.target_map == target  # правка ← прямую схему не трогает
            if touched is not None:
                assert all(w.reverse_overrides.get(n, "auto") == v for n, v in over.items() if n not in touched)

    def note_step(self, before: dict, last) -> None:
        """Действие попало в стек отмены — его состояние «до» в наш журнал (стек ограничен, журнал вместе с ним)."""
        undo = self.page._undo
        if (undo[-1] if undo else None) is not last:
            self.undo_trail.append(before)
            del self.undo_trail[:-len(undo)]
            self.redo_trail.clear()

    def check_undo(self, w: RemapProfile) -> None:
        if not self.page._undo:
            return
        expected = self.undo_trail.pop()
        now = w.to_dict()
        assert self.page.undo()
        assert self.page.work.to_dict() == expected
        self.redo_trail.append(now)
        self.check_model()

    def check_redo(self) -> None:
        if not self.page._redo:
            return
        expected, now = self.redo_trail.pop(), self.page.work.to_dict()
        assert self.page.redo()
        assert self.page.work.to_dict() == expected
        self.undo_trail.append(now)
        self.check_model()

    def check_model(self) -> None:
        w = self.page.work
        effective = w.effective_reverse()
        assert effective == oracle(w)  # нетронутые равны вычисленному, ручные — своему значению
        assert not {n for n, r in w.reverse_overrides.items() if r is None} & set(effective)  # снятый вычисленный не вернулся
        back = RemapProfile.from_json(w.to_json())
        assert back.to_dict() == w.to_dict() and back.reverse_overrides == w.reverse_overrides


# сколько последовательностей на профиль; REMAP_FUZZ — для долгого прогона
SEQUENCES = int(os.environ.get("REMAP_FUZZ", "4"))
STEPS = 120


@qt
@pytest.mark.parametrize("seed", range(SEQUENCES))
@pytest.mark.parametrize("name", sorted(GOLDEN))
def test_random_edit_sequences_keep_the_invariants(app, storage, name, seed):
    window, page = open_page(app, storage, load(name), fast=True)
    fuzz = Fuzz(page, storage, seed)
    for _ in range(STEPS):
        fuzz.step()
    window.close()
    window.deleteLater()


@qt
@pytest.mark.parametrize("name", sorted(GOLDEN))
def test_random_edits_with_the_real_scene(app, storage, name):
    """То же с настоящей перестройкой сцены: вид не падает на любой последовательности."""
    window, page = open_page(app, storage, load(name))
    fuzz = Fuzz(page, storage, 1000)
    for _ in range(25):
        fuzz.step()
    window.close()
    window.deleteLater()


# --- регрессии найденных багов ---

def simple_profile(reverse=None) -> RemapProfile:
    src = NoteMap("S", {34: "Kick Open", 35: "Kick Hit", 36: "Kick Open", 38: "Snare", 40: "Rim", 50: "Tom"})
    tgt = NoteMap("T", {35: "Kick Hit", 38: "Snare", 40: "Rim", 44: "Pedal", 46: "Pedal", 50: "Tom", 51: "Ride"})
    rules = {34: M(35), 35: M(35), 36: M(35), 38: M(38), 40: M(38)}
    return RemapProfile("P", src, tgt, rules, reverse or {})


@qt
def test_revert_keeps_a_hand_rule_that_matched_the_derived_one(app, storage):
    """Ручное 38 -> 40; снимаем 38 -> 38, вычисленное становится тем же 40; Revert не должен потерять ручное правило."""
    window, page = open_page(app, storage, simple_profile({38: M(40)}))
    saved = page.work.to_dict()
    page.clear_rules([38])
    assert page._dirty and page.work.effective_reverse()[38] == M(40)
    page.revert()
    assert page.work.to_dict() == saved == page.base.to_dict() and not page._dirty
    assert page.work.reverse_overrides == {38: M(40)}
    window.close()


@qt
def test_hand_cut_cable_does_not_return_after_forward_edits(app, storage):
    """В ← сняли 38 -> 38; в → убрали оба кабеля на 38 и провели новый: обратный кабель сам не появляется."""
    window, page = open_page(app, storage, simple_profile())
    page.set_direction(REVERSE)
    page.clear_rules([38])
    page.set_direction(FORWARD)
    page.clear_rules([38, 40])
    page.assign_note([50], 38)
    assert page.work.reverse_overrides == {38: None} and 38 not in page.work.effective_reverse()
    page.set_direction(REVERSE)
    page.assign_note([38], 50)  # вернуть можно только руками
    assert page.work.effective_reverse()[38] == M(50) and page.work.reverse_overrides == {}
    window.close()


@qt
def test_cable_drawn_only_in_reverse_and_right_clicked_away_leaves_the_note_automatic(app, storage):
    """В ← провели лишний кабель 51 -> 40 и сняли правым кликом; прямой кабель на 51 снова даёт обратное правило."""
    window, page = open_page(app, storage, simple_profile())
    page.set_direction(REVERSE)
    page.assign_note([51], 40)
    assert page.work.reverse_overrides == {51: M(40)}
    page.cables.right_click(page.cables.source_items[51])
    app.processEvents()
    assert page.work.reverse_overrides == {} and 51 not in page.work.effective_reverse()
    page.set_direction(FORWARD)
    page.assign_note([50], 51)
    assert page.work.effective_reverse()[51] == M(50) and page.work.reverse_overrides == {}
    window.close()


@qt
def test_hand_rule_equal_to_derived_at_some_moment_stays_hand_set(app, storage):
    window, page = open_page(app, storage, simple_profile({38: M(40)}))
    page.clear_rules([38])  # вычисленное стало равно ручному
    page.assign_note([38], 38)  # и снова другое
    assert page.work.effective_reverse()[38] == M(40)  # ручное за прямыми не пошло
    window.close()


@qt
@pytest.mark.parametrize("gesture", ["drop", "group", "match", "double_click"])
def test_occupied_number_behaves_the_same_for_every_gesture(app, storage, gesture):
    """Новый кабель 35 -> 35 на занятый номер забирает обратное правило нетронутой ноты при любом жесте."""
    src = NoteMap("S", {34: "Kick", 35: "Kick", 36: "Kick"})
    tgt = NoteMap("T", {35: "Kick"})
    window, page = open_page(app, storage, RemapProfile("P", src, tgt, {34: M(35), 36: M(35)}))
    assert page.work.effective_reverse()[35] == M(34)
    if gesture == "drop":
        page.connect_to([35], "a:kick")
    elif gesture == "group":
        page.group_drop([35], [35])
    elif gesture == "match":
        page.match_by_number()
    else:
        page.connect_same_number([35])
    assert page.work.rules[35] == M(35)
    assert page.work.effective_reverse()[35] == M(35) and page.work.reverse_overrides == {}
    window.close()


@qt
def test_occupied_number_leaves_a_hand_set_note_alone(app, storage):
    src = NoteMap("S", {34: "Kick", 35: "Kick", 36: "Kick"})
    window, page = open_page(app, storage, RemapProfile("P", src, NoteMap("T", {35: "Kick"}), {34: M(35), 36: M(35)},
                                                        {35: M(36)}))
    page.match_by_number()
    assert page.work.rules[35] == M(35) and page.work.effective_reverse()[35] == M(36)
    window.close()


@qt
def test_write_to_in_reverse_moves_automatic_notes_without_marking_them(app, storage):
    src = NoteMap("S", {84: "Bow", 87: "Bow", 90: "Bell"})
    tgt = NoteMap("T", {85: "Crash"})
    window, page = open_page(app, storage, RemapProfile("P", src, tgt, {84: M(85), 87: M(85)}))
    page.set_direction(REVERSE)
    assert page.work.effective_reverse() == {85: M(84)}
    page.set_write_to(87)
    assert page.work.source_map.primary == {87}
    assert page.work.effective_reverse() == {85: M(87)} and page.work.reverse_overrides == {}
    window.close()


@qt
def test_undo_restores_hand_edits_and_reverse_edit_is_one_step(app, storage):
    window, page = open_page(app, storage, simple_profile())
    before = page.work.to_dict()
    page.set_direction(REVERSE)
    steps = len(page._undo)
    page.clear_rules([38])
    assert len(page._undo) == steps + 1
    assert page.undo() and page.work.to_dict() == before and page.work.reverse_overrides == {}
    assert page.redo() and page.work.reverse_overrides == {38: None}
    window.close()
