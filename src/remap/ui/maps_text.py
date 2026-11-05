"""Тексты и данные вкладки Maps без Qt: ссылка на карту в списке, раскладка строк таблицы нот по группам, подписи,
подсказки и сообщения."""
from __future__ import annotations

import html
from dataclasses import dataclass

from ..core.notemap import NoteMap, display_group, group_sort_key, instrument_group
from ..core.notenames import ParseIssue

TEMPLATE, USER = "template", "user"

COL_NOTE, COL_NAME = range(2)
COLUMNS = ("NOTE", "NAME")  # высота ноты (C#1) для барабанов смысла не несёт — только в подсказке ячейки
COLUMN_TIPS = ("MIDI note number (the pitch name, 60 = C3, is in the cell tooltip)",
               "Articulation name. Empty = the note is not in the map. +N — the name is on N more notes")
# клик по заголовку столбца: по возрастанию → по убыванию → по группам инструментов (вид по умолчанию)
SORT_TIPS = ("Click to list notes in ascending order", "Click to list notes in ascending order",
             "Click to group notes by instrument")

EDIT_TIP = "Double-click or type to edit a name · Empty name: remove the note · Delete: clear selected names"

UNNAMED_GROUP = "\0unnamed"  # служебный ключ группы нот без имени (не совпадёт с normalize_name инструмента)

TEMPLATE_TIP = "Built-in template: read-only. Duplicate it to make your own map."
TEMPLATE_CHIP, OLD_TXT_CHIP = "🔒 TEMPLATE · READ-ONLY", "LEGACY .TXT"
TEMPLATE_CHIP_TIP = "Duplicate the template to edit a copy."
OLD_TXT_CHIP_TIP = "Old REAPER .txt map. Saving converts it to JSON."
NO_MAP_TITLE, NO_MAP_HINT = "No map selected", "Select a map on the left, or create one."


@dataclass(frozen=True)
class MapRef:
    """Элемент списка: встроенный шаблон (только чтение) или карта пользователя из хранилища."""
    kind: str  # TEMPLATE / USER
    id: str

    @property
    def read_only(self) -> bool:
        return self.kind == TEMPLATE


@dataclass(frozen=True)
class LayoutRow:
    """Строка таблицы: заголовок группы инструмента (note is None) или нота."""
    group: str | None  # ключ группы (normalize_name инструмента или служебный); None — плоский список
    note: int | None = None
    label: str = ""    # текст заголовка

    @property
    def is_header(self) -> bool:
        return self.note is None


def group_rows(names: dict[int, str], notes: list[int], unnamed_label: str = "Not in the map",
               ) -> list[LayoutRow]:
    """Строки с заголовками групп instrument_group() (только для показа).

    Группы — в общем порядке GROUP_ORDER (group_rank, как на Profiles), одинаковый ранг — по первой (меньшей) ноте;
    ноты внутри — в порядке notes. Если ни у одного имени нет группы
    (General MIDI) — плоский список без заголовков. Именованные ноты без группы — в «Other»,
    ноты без имени — в последней группе unnamed_label.
    """
    if not any(instrument_group(names[n]) for n in notes if n in names):
        return [LayoutRow(None, n) for n in notes]
    groups: dict[str, tuple[str, list[int]]] = {}
    for n in notes:
        key, label = display_group(names[n]) if n in names else (UNNAMED_GROUP, unnamed_label)
        groups.setdefault(key, (label, []))[1].append(n)
    order = sorted(groups, key=lambda k: group_sort_key(groups[k][0], groups[k][1][0], last=k == UNNAMED_GROUP))
    rows: list[LayoutRow] = []
    for key in order:
        label, members = groups[key]
        rows.append(LayoutRow(key, None, label))
        rows.extend(LayoutRow(key, n) for n in members)
    return rows


def subtitle(m: NoteMap, legacy: bool = False) -> str:
    """Вторая строка записи в списке карт: старая карта .txt и источник."""
    parts = ["legacy .txt"] if legacy else []
    parts.append(m.meta.source or "source not recorded")
    return " · ".join(parts)


def map_tooltip(m: NoteMap, extra: str = "") -> str:
    lines = [m.name, f"Source: {m.meta.source or 'not recorded'}"]
    if m.meta.notes:
        lines.append(f"Notes: {m.meta.notes}")
    if extra:
        lines.append(extra)
    return "\n".join(lines)


def legacy_tip(file_name: str) -> str:
    return f"Legacy REAPER .txt map ({file_name}). Saving converts it to JSON."


def map_info(m: NoteMap) -> str:
    """Источник, заметки и число нот с именем — под заголовком открытой карты."""
    lines = [f"Source: {m.meta.source or 'not recorded'}"]
    if m.meta.notes:
        lines.append(f"Notes: {m.meta.notes}")
    lines.append(f"{len(m.names)} named notes")
    return "\n".join(lines)


def issues_text(errors: list[str], load_issues: int) -> str:
    """Ошибки карты и число проблем чтения .txt (сами проблемы — в подсказке)."""
    parts = []
    if errors:
        parts.append("Errors: " + "; ".join(errors))
    if load_issues:
        parts.append(f"{load_issues} issue(s) when reading the .txt file (see the tooltip).")
    return "\n".join(parts)


def wrapped_tooltip(text: str) -> str:
    """Подсказка с переносом строк: длинный обычный текст Qt показывает одной строкой и обрезает краем экрана."""
    return "<qt>" + html.escape(text).replace("\n", "<br>") + "</qt>" if text else ""


def format_parse_issues(issues: list[ParseIssue], limit: int = 30) -> str:
    lines = [(f"line {i.line}: " if i.line else "") + i.message for i in issues[:limit]]
    if len(issues) > limit:
        lines.append(f"… and {len(issues) - limit} more")
    return "\n".join(lines)
