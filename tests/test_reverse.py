"""Двунаправленные профили: вычисление обратных правил, ручные правки по нотам, reversed(), формат 3, обратная
конвертация."""
import json
from dataclasses import replace
from pathlib import Path

import mido
import pytest

from remap.core import FORWARD, REVERSE, ProfileFormatError, RemapProfile, Rule, analyze, convert, legacy_profile
from remap.core.legacy_map import NOTE_MAP
from remap.core.notemap import NoteMap
from remap.core.profile import (
    DST_NOT_IN_TARGET, KEEP_DIFFERENT, SRC_NOT_IN_SOURCE, derive_reverse, missing_rules, validate_profile, with_reverse_edit,
)

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = sorted(p for p in (ROOT / 'samples' / 'midi').glob('*.mid') if not p.stem.endswith('_remapped'))
M = Rule.map_to


def prof(rules, src=None, tgt=None, reverse=None):
    return RemapProfile('p', src, tgt, rules, reverse or {})


HATS = NoteMap('T', {42: 'Hat', 44: 'Hat', 46: 'Hat', 36: 'Kick', 38: 'Snare'})


# --- выведение ---

def test_many_to_one_reverse_goes_to_same_number_or_lowest():
    assert derive_reverse(prof({60: M(60), 121: M(60), 124: M(60)})) == {60: M(60)}
    assert derive_reverse(prof({124: M(60), 121: M(60)})) == {60: M(121)}
    # n -> n важнее наименьшей
    assert derive_reverse(prof({35: M(36), 36: M(36)})) == {36: M(36)}


def test_many_to_one_prefers_explicit_write_to_of_the_source_map():
    src = NoteMap('S', {84: 'Bow', 87: 'Bow', 90: 'Bell'}, primary={87})
    tgt = NoteMap('T', {85: 'Crash'})
    assert derive_reverse(prof({84: M(85), 87: M(85)}, src, tgt)) == {85: M(87)}  # тот же адрес, что drop в ←
    assert derive_reverse(prof({85: M(85), 87: M(85)}, src, tgt)) == {85: M(85)}  # тот же номер важнее
    assert derive_reverse(prof({84: M(85), 90: M(85)}, src, tgt)) == {85: M(84)}  # Write to нет среди источников
    single = NoteMap('S', {10: 'A', 20: 'B'})  # primary_note() вернул бы ноту, но явного Write to нет: наименьшая
    assert derive_reverse(prof({10: M(85), 20: M(85)}, single, tgt)) == {85: M(10)}


def test_target_aliases_follow_write_to_or_lowest_with_rule():
    # Write to (44) без входящих кабелей — берётся наименьшая нота артикуляции с правилом (42)
    p = prof({10: M(42)}, tgt=replace(HATS, primary={44}))
    assert derive_reverse(p) == {42: M(10), 44: M(10), 46: M(10)}
    # Write to (46) с правилом — алиас без кабелей (44) идёт туда же, куда Write to
    p = prof({10: M(42), 11: M(46)}, tgt=replace(HATS, primary={46}))
    assert derive_reverse(p) == {42: M(10), 44: M(11), 46: M(11)}
    # Write to не выбран — наименьшая с правилом
    p = prof({10: M(42), 11: M(46)}, tgt=HATS)
    assert derive_reverse(p) == {42: M(10), 44: M(10), 46: M(11)}


def test_untouched_notes_get_no_reverse_rule():
    p = prof({36: M(36), 40: Rule.delete(), 38: Rule.keep()}, tgt=HATS)
    assert derive_reverse(p) == {36: M(36)}  # Snare (keep) и Hat (нет кабелей) — без правил
    assert derive_reverse(prof({})) == {}


# --- reversed / oriented / полнота ---

SRC = NoteMap('S', {35: 'Kick', 36: 'Kick', 38: 'Snare', 40: 'Rim'})
TGT = NoteMap('T', {36: 'Kick', 38: 'Snare', 37: 'Stick'})


def test_reversed_swaps_maps_and_rules():
    p = prof({35: M(36), 36: M(36), 40: M(38), 38: Rule.delete()}, SRC, TGT)
    r = p.reversed()
    assert r.source_map == TGT and r.target_map == SRC
    assert r.rules == {36: M(36), 38: M(40)} and r.effective_reverse() == p.rules
    assert p.oriented(FORWARD) is p and p.oriented(REVERSE).to_dict() == r.to_dict()
    with pytest.raises(ValueError):
        p.oriented('sideways')


def test_reversed_twice_gives_the_same_rules():
    p = prof({35: M(36), 36: M(36), 40: M(38)}, SRC, TGT)
    back = p.reversed().reversed()
    assert (back.rules, back.source_map, back.target_map) == (p.rules, p.source_map, p.target_map)
    q = prof(p.rules, SRC, TGT, {36: M(35), 37: Rule.delete(), 38: None})
    assert q.reversed().rules == q.effective_reverse() == {36: M(35), 37: Rule.delete()}
    assert q.reversed().reversed().effective_reverse() == q.effective_reverse()


def test_missing_rules_per_direction():
    p = prof({35: M(36), 36: M(36)}, SRC, TGT)
    assert missing_rules(p, FORWARD) == [38, 40]
    assert missing_rules(p, REVERSE) == [37, 38]
    assert missing_rules(prof({35: M(36)}), REVERSE) == []  # без карты — пусто


# --- ручные правки по нотам ---

def test_untouched_notes_follow_forward_edits():
    p = prof({35: M(36)}, SRC, TGT)
    assert p.effective_reverse() == {36: M(35)}
    p.rules[40] = M(38)  # новый кабель
    assert p.effective_reverse() == {36: M(35), 38: M(40)}
    p.rules[36] = M(36)  # n -> n забирает обратное правило
    assert p.effective_reverse()[36] == M(36)
    p.rules = {}  # кабели сняты — правила уходят
    assert p.effective_reverse() == {}


def test_hand_set_notes_never_change_on_forward_edits():
    p = prof({35: M(36), 40: M(38)}, SRC, TGT, {36: M(40), 38: None, 37: Rule.delete()})
    expected = {36: M(40), 37: Rule.delete()}
    assert p.effective_reverse() == expected
    for rules in ({}, {36: M(36)}, {38: M(38), 40: M(36)}, {35: M(37), 36: M(37)}):
        p.rules = rules
        assert p.effective_reverse() == expected


def test_reverse_edit_marks_only_changed_notes_and_keeps_forward():
    p = prof({35: M(36), 40: M(38)}, SRC, TGT)
    q = with_reverse_edit(p, {36: M(40), 38: M(40), 37: Rule.delete()})
    assert q.reverse_overrides == {36: M(40), 37: Rule.delete()} and q.rules == p.rules and not p.reverse_overrides


def test_reverse_edit_equal_to_derived_is_automatic_again():
    p = prof({35: M(36)}, SRC, TGT, {36: M(40)})
    assert with_reverse_edit(p, {36: M(35)}).reverse_overrides == {}
    q = with_reverse_edit(p, {36: M(36)})  # другое значение — остаётся ручной
    assert q.reverse_overrides == {36: M(36)}


def test_cut_of_a_derived_cable_stays_cut():
    p = prof({35: M(36)}, SRC, TGT)
    cut = with_reverse_edit(p, {})
    assert cut.reverse_overrides == {36: None} and cut.effective_reverse() == {}
    cut.rules = {}  # вычисленного больше нет, а отметка остаётся
    cut.rules = {40: M(36)}
    assert cut.effective_reverse() == {}


def test_cut_of_a_cable_drawn_only_in_reverse_is_automatic_again():
    p = prof({35: M(36)}, SRC, TGT)
    drawn = with_reverse_edit(p, {36: M(35), 37: M(38)})
    assert drawn.reverse_overrides == {37: M(38)}
    gone = with_reverse_edit(drawn, {36: M(35)})  # снят кабель, которого нет в прямой схеме
    assert gone.reverse_overrides == {}
    gone.rules[38] = M(37)
    assert gone.effective_reverse()[37] == M(38)  # прямой кабель на эту ноту снова даёт обратное правило


def test_restoring_a_struck_note_with_no_derived_rule_is_automatic():
    p = prof({}, SRC, TGT)
    struck = with_reverse_edit(p, {37: Rule.delete()})
    assert with_reverse_edit(struck, {}).reverse_overrides == {}  # зачёркивание — не кабель


def test_target_aliases_copy_a_hand_set_donor():
    p = prof({10: M(42)}, tgt=HATS)
    assert p.effective_reverse() == {42: M(10), 44: M(10), 46: M(10)}
    p.reverse_overrides = {42: M(11)}
    assert p.effective_reverse() == {42: M(11), 44: M(11), 46: M(11)}
    p.reverse_overrides = {42: None}
    assert p.effective_reverse() == {}
    p.reverse_overrides = {42: M(11), 46: Rule.delete()}  # ручная нота донора не копирует
    assert p.effective_reverse() == {42: M(11), 44: M(11), 46: Rule.delete()}


# --- JSON ---

def test_json_format_3_round_trip_with_hand_set_reverse():
    src = replace(SRC, primary={36})
    p = prof({35: M(36), 36: M(36), 40: M(38)}, src, TGT, {36: M(35), 37: Rule.delete(), 38: None})
    data = json.loads(p.to_json())
    assert data['format'] == 3 and data['source_map']['primary'] == [36]
    assert data['reverse_rules'] == [{'src': 36, 'action': 'map', 'dst': 35}, {'src': 37, 'action': 'delete'}]
    assert data['reverse_manual'] == [36, 37, 38]  # 38 в списке и не в правилах: кабель снят
    back = RemapProfile.from_json(p.to_json())
    assert back == p and back.reverse_overrides == {36: M(35), 37: Rule.delete(), 38: None}
    assert back.source_map.primary == {36}


def test_json_format_3_recomputes_automatic_notes():
    data = json.loads(prof({35: M(36), 40: M(38)}, SRC, TGT).to_json())
    assert data['reverse_rules'] == [{'src': 36, 'action': 'map', 'dst': 35}, {'src': 38, 'action': 'map', 'dst': 40}]
    assert data['reverse_manual'] == []
    data['reverse_rules'] = []  # значения автоматических нот из файла не читаются
    back = RemapProfile.from_json(json.dumps(data))
    assert back.reverse_overrides == {} and back.effective_reverse() == {36: M(35), 38: M(40)}


def test_format_2_reads_differences_as_hand_set():
    p = prof({35: M(36), 40: M(38)}, SRC, TGT)
    data = json.loads(p.to_json())
    del data['reverse_manual']
    data['format'] = 2
    back = RemapProfile.from_json(json.dumps(data))
    assert back.reverse_overrides == {} and back == p  # равны вычисленным — ручных нет
    data['reverse_rules'] = [{'src': 36, 'action': 'map', 'dst': 40}, {'src': 37, 'action': 'delete'}]
    back = RemapProfile.from_json(json.dumps(data))
    assert back.reverse_overrides == {36: M(40), 37: Rule.delete(), 38: None}  # 38 в файле нет: кабель снят
    assert back.effective_reverse() == {36: M(40), 37: Rule.delete()}


def test_format_2_keeps_alias_values_next_to_a_hand_set_donor():
    data = json.loads(prof({10: M(42)}, tgt=HATS).to_json())
    del data['reverse_manual']
    data['format'] = 2
    data['reverse_rules'] = [{'src': 42, 'action': 'map', 'dst': 11}, {'src': 44, 'action': 'map', 'dst': 10},
                             {'src': 46, 'action': 'map', 'dst': 11}]
    back = RemapProfile.from_json(json.dumps(data))
    assert back.effective_reverse() == {42: M(11), 44: M(10), 46: M(11)}  # точно как в файле


def test_format_1_still_reads():
    text = json.dumps({'format': 1, 'name': 'old', 'rules': [{'src': 35, 'action': 'map', 'dst': 36}],
                       'reverse_rules': [{'src': 36, 'action': 'delete'}]})  # у формата 1 поле не читается
    p = RemapProfile.from_json(text)
    assert p.reverse_overrides == {} and p.effective_reverse() == {36: M(35)}
    p2 = RemapProfile.from_json(json.dumps({'format': 2, 'name': 'x', 'rules': []}))  # формат 2 без поля
    assert p2.reverse_overrides == {}


@pytest.mark.parametrize('reverse', [
    {},                                                                        # не список
    [{'src': 36, 'action': 'keep'}, {'src': 36, 'action': 'delete'}],          # дубль
    [{'src': 200, 'action': 'keep'}],
    [{'src': 36, 'action': 'map'}],                                            # map без dst
])
def test_bad_reverse_rules_raise_format_error(reverse):
    with pytest.raises(ProfileFormatError):
        RemapProfile.from_json(json.dumps({'format': 2, 'name': 'x', 'rules': [], 'reverse_rules': reverse}))


@pytest.mark.parametrize('manual', [{}, [200], [36, 36], ['36'], 36])
def test_bad_reverse_manual_raises_format_error(manual):
    with pytest.raises(ProfileFormatError):
        RemapProfile.from_json(json.dumps({'format': 3, 'name': 'x', 'rules': [], 'reverse_rules': [],
                                           'reverse_manual': manual}))


# --- обратная конвертация ---

def note_events(path):
    out, now = [], 0
    for msg in mido.MidiFile(str(path)).tracks[0]:
        now += msg.time
        if msg.type in ('note_on', 'note_off'):
            out.append((now, msg.type, msg.note, msg.velocity))
    return out


def test_reverse_conversion_uses_reverse_rules(tmp_path):
    src = tmp_path / 'in.mid'
    midi = mido.MidiFile(type=1, ticks_per_beat=480)
    track = mido.MidiTrack()
    for i, n in enumerate((36, 38, 50)):
        track += [mido.Message('note_on', note=n, velocity=100, time=0 if i == 0 else 10),
                  mido.Message('note_off', note=n, velocity=0, time=5)]
    midi.tracks.append(track)
    midi.save(str(src))
    p = prof({35: M(36), 36: M(36), 40: M(38)}, SRC, TGT)
    assert analyze(src, p, REVERSE).unresolved == [50]
    report = convert(src, tmp_path / 'out.mid', p, direction=REVERSE)
    assert [e[2] for e in note_events(tmp_path / 'out.mid')] == [36, 36, 40, 40, 50, 50]
    assert report.unresolved_kept == [50] and report.notes[38].dst == 40
    with pytest.raises(ValueError):
        convert(src, tmp_path / 'x.mid', p, direction='sideways')


@pytest.mark.parametrize('sample', SAMPLES, ids=lambda p: p.name)
def test_round_trip_on_samples(tmp_path, sample):
    """GM -> SD3 по схеме первой версии и обратно: основные ноты возвращаются на свои номера,
    прочие — на основную ноту своей цели."""
    p = legacy_profile()
    convert(sample, tmp_path / 'fwd.mid', p)
    convert(tmp_path / 'fwd.mid', tmp_path / 'back.mid', p, direction=REVERSE)
    rev = p.effective_reverse()
    expected = {a: rev[b].dst for a, b in NOTE_MAP.items()}
    original = [e for e in note_events(sample) if e[2] in NOTE_MAP]
    back = note_events(tmp_path / 'back.mid')
    assert {e[2] for e in back} == {expected[e[2]] for e in original}
    if all(expected[e[2]] == e[2] for e in original):  # все ноты файла — основные: файл возвращается как был
        assert back == original


# --- замечания в обратном направлении ---

def test_validate_profile_reverse_names_profile_maps():
    src = NoteMap("S", {36: "Kick", 38: "Snare"})
    tgt = NoteMap("T", {36: "Kick", 40: "Snare"})
    p = prof({36: M(36)}, src, tgt, reverse={36: M(50), 41: M(36), 40: Rule.keep()})
    issues = {(i.code, i.note): i.message for i in validate_profile(p, REVERSE)}
    assert issues[(DST_NOT_IN_TARGET, 36)] == "note 36 is mapped to 50, which is not in the source map"
    assert issues[(SRC_NOT_IN_SOURCE, 41)] == "rule for note 41, which is not in the target map"
    assert issues[("keep_not_in_target_map", 40)] == "note 40 is kept, but the source map has no note 40"
    # в прямом направлении — как раньше
    p2 = prof({38: Rule.keep()}, src, NoteMap("T", {38: "Tom"}))
    (issue,) = [i for i in validate_profile(p2) if i.code == KEEP_DIFFERENT]
    assert issue.message == 'note 38 is kept, but it is "Snare" in the source map and "Tom" in the target map'
