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
SORT_TIPS = ("Click to list notes in ascending order", "Click to list notes in descending order",
             "Click to group notes by instrument")

EDIT_TIP = "Double-click or type to edit a name · Empty name: remove the note · Delete: clear selected names"

UNNAMED_GROUP, UNNAMED_LABEL = "\0unnamed", "Unnamed"  # служебный ключ группы нот без имени (не совпадёт с normalize_name инструмента)

TEMPLATE_TIP = "Built-in template: read-only. Duplicate it to make your own map."
NO_MAP_TITLE, NO_MAP_HINT = "No map selected", "Select a map on the left, or create one."

# экран нот: поиск, флажок, строка итогов
SEARCH_PLACEHOLDER = "Search: name or note number"
NAMED_ONLY, NAMED_ONLY_TIP = "NAMED ONLY", "Hide notes that are not in the map"
EDIT_HINT = "ENTER · SAVE NAME\u00a0\u00a0ESC · CANCEL"
READ_ONLY_HINT = "READ-ONLY TEMPLATE"
GROUP_TIP = "Click to collapse or expand the group"

# полоса: подсказки клавиш (подписи — из макета) и вопрос при первой попытке править шаблон
NEW_TIP = "New map"
IMPORT_TIP = "Import a REAPER note name map (.txt)"
EXPORT_TIP = "Export the map to a REAPER .txt file"
MORE_TIP = "Duplicate / Rename / Delete"
SAVE_TIP = "Save map (Ctrl+S)"
DUPLICATE_TO_EDIT = "Duplicate to My Maps to edit?"
DUPLICATE_TO_EDIT_DETAILS = "Built-in templates are read-only. Your copy keeps the template's notes."


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


def group_rows(names: dict[int, str], notes: list[int], unnamed_label: str = UNNAMED_LABEL,
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
    """Вторая строка записи в списке карт: старая карта .txt и источник (нет источника — заметки)."""
    parts = ["legacy .txt"] if legacy else []
    parts.append(m.meta.source or m.meta.notes or "source not recorded")
    return " · ".join(parts)


def map_tooltip(m: NoteMap, extra: str = "") -> str:
    """Тело подсказки записи (заголовок — имя карты): источник и заметки целиком, затем `extra`."""
    lines = [f"Source: {m.meta.source or 'not recorded'}"]
    if m.meta.notes:
        lines.append(f"Notes: {m.meta.notes}")
    if extra:
        lines.append(extra)
    return "\n".join(lines)


def legacy_tip(file_name: str) -> str:
    return f"Legacy REAPER .txt map ({file_name}). Saving converts it to JSON."


def next_sort(sort: tuple[int, bool] | None, column: int) -> tuple[int, bool] | None:
    """Клик по заголовку колонки: по возрастанию → по убыванию → снова по группам инструментов (вид по умолчанию);
    клик по другой колонке — сразу по возрастанию."""
    if sort is None or sort[0] != column:
        return column, False
    return (column, True) if not sort[1] else None


def sort_tip(sort: tuple[int, bool] | None, column: int) -> str:
    """Подсказка заголовка колонки: что она показывает и что сделает следующий клик."""
    after = next_sort(sort, column)
    return COLUMN_TIPS[column] + "\n" + SORT_TIPS[2 if after is None else int(after[1])]


def totals_text(named: int, errors: list[str]) -> tuple[str, bool]:
    """Левая часть строки итогов и признак ошибки: число нот с именем; ошибки карты (validate_map) — вместо него."""
    if errors:
        return (f"{len(errors)} ERROR{'S' if len(errors) > 1 else ''} IN THE MAP"), True
    return f"{named} NAMED NOTE{'' if named == 1 else 'S'}", False


def totals_tip(errors: list[str], load_issues: list[ParseIssue]) -> str:
    """Подсказка строки итогов: ошибки карты и проблемы чтения старой карты .txt."""
    parts = []
    if errors:
        parts.append("Errors:\n" + "\n".join(errors))
    if load_issues:
        parts.append(f"{len(load_issues)} issue(s) when reading the .txt file:\n" + format_parse_issues(load_issues))
    return "\n\n".join(parts)


def badge_tip(note: int, notes: list[int]) -> str:
    """Подсказка бейджа «+N»: остальные номера с этим именем."""
    others = [n for n in notes if n != note]
    return f"Also on note{'s' if len(others) > 1 else ''} {', '.join(map(str, others))}"


def wrapped_tooltip(text: str) -> str:
    """Подсказка с переносом строк: длинный обычный текст Qt показывает одной строкой и обрезает краем экрана."""
    return "<qt>" + html.escape(text).replace("\n", "<br>") + "</qt>" if text else ""


def format_parse_issues(issues: list[ParseIssue], limit: int = 30) -> str:
    lines = [(f"line {i.line}: " if i.line else "") + i.message for i in issues[:limit]]
    if len(issues) > limit:
        lines.append(f"… and {len(issues) - limit} more")
    return "\n".join(lines)
