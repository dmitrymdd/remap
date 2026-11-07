"""Тексты вкладки Profiles без Qt: подсказки строк, плашек цели и кабелей вида «кабелями».

Функции берут простые данные (ориентированный профиль, строки раскладки `cable_layout`, ручные обратные правки) и
возвращают простой текст; HTML подсказки (`tips.tip()`) готовит вид. Подсказка — не больше трёх строк: высота ноты,
куда идёт, замечания и ручные правки, действие правой кнопкой. То, что видно на плашке, и жесты, которым учит обучение
(перетаскивание, росчерк), не повторяются.
"""
from __future__ import annotations

from ..core.notemap import NoteMap, primary_note
from ..core.pitch import note_tip
from ..core.profile import RemapProfile, Rule, names_differ
from .cable_layout import DELETE, KEEP, MIXED, UNASSIGNED, Cable, SourceRow, TargetRow

DELETED_TIP = "Deleted from converted files"
KEPT_TIP = "Kept on the same number"
# ←: ноты цели без обратного правила при сохранении не спрашиваются (полнота — статус)
REVERSE_UNASSIGNED_TIP = "No rule here: kept on the same number"
MIXED_TIP = "Different rules: shown one by one"
REMOVE_ACTION = "Right-click: remove"
DELETE_ACTION = "Right-click: delete"
RESTORE_ACTION = "Right-click: restore"
SAME_NUMBER_HINT = "Double-click: same number"
SUGGESTED_HINT = "Suggested: apply in the bar above"
SUGGESTED_WRITE_TO_HINT = "Suggested, needs a Write to note: Apply skips it"
NAMES_DIFFER_TIP = "Names differ"
NOT_WRITE_TO_TIP = "Not the Write to note ({n})"
WRITE_TO_TIP = "Write to: {n}"
NO_WRITE_TO_TIP = "Write to: not chosen"
BADGE_HINT = "Click {pill}: choose the Write to"
HAND_SET_TIP = "Set by hand: forward edits don't change it"
HAND_SET_SOME_TIP = "Set by hand ({notes})"
HAND_REMOVED_TIP = "Removed by hand: forward edits don't restore it"
HAND_REMOVED_SOME_TIP = "Removed by hand ({notes})"
TIP_LINES = 3
POOL_TITLE = "Unassigned"
POOL_TIP = ("{side} notes not connected in this direction, by instrument.\n"
            "Struck-through notes are deleted: right-click to restore")
EMPTY_HINT = "Drag notes from Unassigned onto the {side} map"
GROUP_HINT = "Right-click to delete or restore the whole group"
TARGET_GROUP_HINT = "Drop notes here to connect those with the same numbers"

Overrides = dict[int, Rule | None]


def tip_lines(head: str, details: list[str], action: str = "") -> str:
    """Текст подсказки: первая строка, замечания, действие; больше TIP_LINES строк — замечания в одну строку через «·»."""
    details = [d for d in details if d]
    if len(details) + 1 + bool(action) > TIP_LINES and len(details) > 1:
        details = [" · ".join(details)]
    return "\n".join([line for line in (head, *details, action) if line])


def with_name(name: str, text: str) -> str:
    """Полное имя первой строкой подсказки; строк стало больше TIP_LINES — средние склеиваются через «·»."""
    lines = [name, *text.splitlines()]
    if len(lines) > TIP_LINES:
        lines = [lines[0], " · ".join(lines[1:-1]), lines[-1]]
    return "\n".join(lines)


def hand_text(notes: tuple[int, ...], overrides: Overrides | None, connected: bool) -> str:
    """Пометка «ручная правка» по `reverse_overrides` прямого профиля; `overrides` None (→) — ничего."""
    if overrides is None:
        return ""
    if connected:
        hand = [n for n in notes if overrides.get(n) is not None]
        if not hand:
            return ""
        return HAND_SET_TIP if len(notes) == 1 else HAND_SET_SOME_TIP.format(notes=", ".join(map(str, hand)))
    gone = [n for n in notes if n in overrides and overrides[n] is None]
    if not gone:
        return ""
    return HAND_REMOVED_TIP if len(notes) == 1 else HAND_REMOVED_SOME_TIP.format(notes=", ".join(map(str, gone)))


def not_write_to(target_map: NoteMap | None, dst: int) -> str:
    """Кабель идёт не на Write to своей артикуляции — замечание."""
    if target_map is None or dst not in target_map.names:
        return ""
    wt = primary_note(target_map, target_map.names[dst])
    return NOT_WRITE_TO_TIP.format(n=wt) if wt is not None and wt != dst else ""


def _idle_details(row: SourceRow, target_map: NoteMap | None, target_side: str, reverse: bool) -> tuple[list[str], str]:
    """Строка без кабеля и не зачёркнутая: keep / нет правила / разные правила; действие — delete."""
    details = []
    if row.state == KEEP:
        where = (f": {target_map.names[row.note]}" if target_map is not None and row.note in target_map.names
                 else f" (not in the {target_side} map)")
        details.append(KEPT_TIP + where)
    elif reverse and row.state == UNASSIGNED:
        details.append(REVERSE_UNASSIGNED_TIP)
    elif row.state == MIXED:
        details.append(MIXED_TIP)
    action = DELETE_ACTION
    if row.block == UNASSIGNED:
        action += f" · {SAME_NUMBER_HINT}"
    return details, action


def source_tip(row: SourceRow, issues: list[str], shown: RemapProfile, cable: Cable | None,
               overrides: Overrides | None, target_side: str, reverse: bool) -> str:
    """Подсказка строки слева: ноты (у строки ноты под заголовком алиасов — и имя), куда идёт, замечания, действие.
    `shown` — ориентированный профиль, `cable` — пунктирный кабель строки-подсказки, `target_side` — «source» /
    «target» (карта справа), `reverse` — направление ←."""
    tgt = shown.target_map
    head = note_tip(row.notes)
    if row.child and row.name:
        head = f"{head} · {row.name}"
    details: list[str] = list(issues)
    action = ""
    if row.expanded:
        details += [MIXED_TIP] if row.mixed else []
    elif row.connected:
        dst = shown.rules[row.note].dst
        dst_name = tgt.names.get(dst, "") if tgt is not None else ""
        head = f"{head}  →  {dst} {dst_name}".rstrip()
        details.append(not_write_to(tgt, dst))
        action = REMOVE_ACTION
    elif row.suggested:
        if cable.dst is not None:
            head = f"{head}  →  {cable.dst} {cable.target.label}".rstrip()
            details.append(SUGGESTED_HINT)
        else:
            head = f"{head}  →  {cable.target.label}"
            details.append(SUGGESTED_WRITE_TO_HINT)
    elif row.state == DELETE:
        details.append(DELETED_TIP)
        action = RESTORE_ACTION
    else:
        more, action = _idle_details(row, tgt, target_side, reverse)
        details += more
    details.append(hand_text(row.notes, overrides, connected=row.connected and not row.suggested and not row.expanded))
    return tip_lines(head, details, action)


def cable_tip(c: Cable, shown: RemapProfile, overrides: Overrides | None) -> str:
    """Кабель: «ноты имя  →  нота имя» по ориентированному профилю (как на картинке — слева направо), замечания
    (имена разные, не Write to, ручная правка), действие."""
    src_name = shown.source_map.names.get(c.notes[0], "") if shown.source_map is not None else ""
    tgt = shown.target_map
    dst_name = tgt.names.get(c.dst, "") if tgt is not None else ""
    left = f"{', '.join(map(str, c.notes))} {src_name}".strip()
    right = f"{c.dst} {dst_name}".strip()
    details = [NAMES_DIFFER_TIP if names_differ(shown, c.notes[0], c.dst) else "", not_write_to(tgt, c.dst),
               hand_text(c.notes, overrides, connected=True)]
    return tip_lines(f"{left}  →  {right}", details, REMOVE_ACTION)


def target_missing_tip(t: TargetRow, has_target_map: bool, target_side: str) -> str:
    """Строка цели вне карты (или карты справа нет)."""
    side = f"{target_side} map"
    return tip_lines(note_tip(t.notes), [f"Not in the {side}" if has_target_map else f"No {side}"])


def target_tip(t: TargetRow, pill: str) -> str:
    """Строка цели: ноты; у артикуляции на нескольких нотах — Write to и бейдж `pill`, которым его выбирают."""
    details = []
    if len(t.notes) > 1:
        wt = WRITE_TO_TIP.format(n=t.write_to) if t.write_to is not None else NO_WRITE_TO_TIP
        details = [f"{wt} · {BADGE_HINT.format(pill=pill)}"]
    return tip_lines(note_tip(t.notes), details)


def target_number_tip(t: TargetRow, n: int) -> str:
    """Плашка номера раскрытой группы цели: номер, высота и имя (на плашке имени нет)."""
    return tip_lines(f"{note_tip([n])} · {t.label}", ["Write to" if n == t.write_to else ""])
