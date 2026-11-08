"""Смоук-тесты менеджера/редактора карт (PySide6, платформа Qt offscreen, диалоги подменены)."""
import shutil
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytestmark = pytest.mark.ui

from PySide6.QtCore import Qt

from remap.core.notemap import NoteMap
from remap.core.pitch import pitch_name
from remap.core.notenames import parse_notenames
from remap.templates import load_map_template
from remap.ui import theme
from remap.ui.main_window import PAGE_MAPS, MainWindow
from remap.ui.maps_table import OTHERS_ROLE
from remap.ui.maps_text import COL_NAME, COL_NOTE, TEMPLATE, USER, MapRef

FIXTURE = Path(__file__).parent / "fixtures" / "reaper_custom_with_order.txt"


@pytest.fixture
def window(app, storage):
    w = MainWindow(storage)
    w.show_page(PAGE_MAPS)
    page = w.maps_page
    # диалоги не открываем: тест задаёт ответы
    page.answers = {"text": [], "confirm": True, "save_changes": "discard"}
    page.ask_text = lambda *a: page.answers["text"].pop(0) if page.answers["text"] else None
    page.confirm = lambda *a: page.answers["confirm"]
    page.ask_save_changes = lambda: page.answers["save_changes"]
    page.show_error = lambda text: page.answers.setdefault("errors", []).append(text)
    page.ask_keep_import = lambda *a: page.answers.setdefault("issues", []).append(a) or page.answers.get("keep", True)
    yield w
    w.close()
    w.deleteLater()


def refs(page):
    return page.list.refs()



def test_manager_lists_templates_and_opens_read_only(window):
    page = window.maps_page
    templates = [r for r in refs(page) if r.kind == TEMPLATE]
    assert {r.id for r in templates} >= {"Superior Drummer 3", "EZdrummer 3"}
    page.select(MapRef(TEMPLATE, "Superior Drummer 3"))
    assert page.current == MapRef(TEMPLATE, "Superior Drummer 3")
    assert page.model.read_only
    idx = page.model.note_index(36, COL_NAME)
    assert not page.model.flags(idx) & Qt.ItemFlag.ItemIsEditable
    assert not page.model.setData(idx, "X")
    assert not page.strip.rename_action.isEnabled() and not page.strip.delete_action.isEnabled()
    assert page.strip.duplicate_action.isEnabled()
    assert not hasattr(page, "status_chip")  # статус карты в UI не показывается
    assert "verified" not in page.list.entry(page.current).tip.casefold()
    # у шаблона сохранять нечего: Save недоступна; поле — TEMPLATE с замком, полное имя — в подсказке
    assert not page.strip.save_btn.isEnabled() and not page.strip.revert_action.isEnabled()
    field = page.strip.field
    assert field.caption == "TEMPLATE" and field.locked and field.value == "Superior Drummer 3"
    assert "Superior Drummer 3" in field.toolTip() and "read-only" in field.toolTip()


def test_template_edit_attempt_offers_duplicate_once(window, app):
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QKeyEvent
    page = window.maps_page
    page.select(MapRef(TEMPLATE, "Superior Drummer 3"))
    asked = []
    page.confirm = lambda *a: asked.append(a[1]) or False
    table = page.notes.table
    table.setFocus()
    for _ in range(2):
        app.sendEvent(table, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_A, Qt.KeyboardModifier.NoModifier, "a"))
    assert asked == ["Duplicate to My Maps to edit?"]  # один раз на открытие
    assert page.current == MapRef(TEMPLATE, "Superior Drummer 3") and not page.dirty
    # согласие — копия в My Maps
    page.select(MapRef(TEMPLATE, "EZdrummer 3"))
    page.confirm = lambda *a: True
    page.answers["text"] = ["EZD copy"]
    app.sendEvent(table, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier))
    assert page.current == MapRef(USER, "EZD copy") and page.strip.field.caption == "MY MAP"


def test_duplicate_edit_save_reload(window, storage, app):
    page = window.maps_page
    page.select(MapRef(TEMPLATE, "EZdrummer 3"))
    page.answers["text"] = ["My EZD3"]
    page.duplicate()
    assert page.current == MapRef(USER, "My EZD3") and not page.model.read_only
    assert not page.strip.save_btn.isEnabled() and not page.strip.field.locked
    assert page.work.meta.notes.endswith("Based on template EZdrummer 3")
    assert page.work.meta.status == "verified"

    # правка имени — unverified
    assert page.model.setData(page.model.note_index(38, COL_NAME), "  Snare: Center X  ")
    assert page.dirty and window.nav_maps.text() == "Maps"  # у вкладки нет отметки «не сохранено»
    assert page.strip.save_btn.isEnabled() and page.strip.revert_action.isEnabled()
    page._shortcuts[0].activated.emit()  # Ctrl+S
    assert not page.dirty
    saved, _ = storage.load_map("My EZD3")
    assert saved.names[38] == "Snare: Center X" and saved.meta.status == "unverified"
    assert saved.meta.source == load_map_template("EZdrummer 3").meta.source

    # перезагрузка окна: карта на месте
    w2 = MainWindow(storage)
    w2.maps_page.select(MapRef(USER, "My EZD3"))
    assert w2.maps_page.work.names[38] == "Snare: Center X"
    w2.close()


def test_primary_kept_in_file_but_not_editable(window, storage):
    # Write to на вкладке Maps не правится, но в JSON остаётся (старые файлы читаются и сохраняются как есть)
    storage.save_map(NoteMap("Kit", {35: "Kick", 36: "Kick", 38: "Snare", 39: "Clap"}, primary={36}))
    page = window.maps_page
    page.reload_list()
    page.select(MapRef(USER, "Kit"))
    m = page.model
    assert all(not m.flags(m.index(r, c)) & Qt.ItemFlag.ItemIsUserCheckable
               for r in range(m.rowCount()) for c in range(m.columnCount()))
    m.set_name(38, "Snare 2")
    assert page.save()
    assert storage.load_map("Kit")[0].primary == {36}
    # переименование ноты Write to в другую артикуляцию снимает флаг
    m.set_name(36, "Something else")
    assert 36 not in page.work.primary


def test_same_name_badge(window, storage, app):
    storage.save_map(NoteMap("Kit", {35: "Kick", 36: "kick ", 38: "Snare"}))
    page = window.maps_page
    page.reload_list()
    page.select(MapRef(USER, "Kit"))
    m = page.model
    assert m.data(m.note_index(36, COL_NAME), OTHERS_ROLE) == 1
    assert m.data(m.note_index(38, COL_NAME), OTHERS_ROLE) == 0
    assert m.badge_tip(35) == "Also on note 36"
    # дубли без Write to больше не подсвечиваются и не попадают в замечания
    assert m.data(m.note_index(36, COL_NAME), Qt.ItemDataRole.BackgroundRole) is None
    assert page.notes.totals.left == "3 NAMED NOTES" and not page.notes.totals.error
    window.resize(1000, 700)
    window.show()
    app.processEvents()
    assert not page.notes.table.grab().isNull()  # бейдж рисуется без ошибок


def test_filter_named_only_and_search(window):
    page = window.maps_page
    page.select(MapRef(TEMPLATE, "Superior Drummer 3"))
    n_named = len(page.work.names)
    assert len(page.proxy.note_rows()) == n_named
    page.notes.named_only.setChecked(False)
    assert sorted(page.proxy.note_rows()) == list(range(128))
    page.notes.search.setText("36")
    assert page.proxy.note_rows() == [36] and page.proxy.rowCount() == 2  # нота + заголовок её группы
    page.notes.search.setText("c1")  # название высоты
    assert page.proxy.note_rows() == [36]
    page.notes.search.setText("kick")
    assert 0 < len(page.proxy.note_rows()) < n_named
    # пустые группы скрыты: видимые заголовки — только группы найденных нот
    headers = [page.model.row_at(page.proxy.mapToSource(page.proxy.index(r, 0)).row())
               for r in range(page.proxy.rowCount())]
    assert [h.label for h in headers if h.is_header] == ["Kick"]


def test_clearing_name_removes_note_and_prunes_order(window, storage):
    m, _ = parse_notenames(FIXTURE.read_text(encoding="utf-8"), "Ordered")
    assert m.order
    storage.save_map(m)
    page = window.maps_page
    page.reload_list()
    page.select(MapRef(USER, "Ordered"))
    victim = next(n for n in m.order if n in m.names)
    page.model.setData(page.model.note_index(victim, COL_NAME), "")
    assert victim not in page.work.names
    assert page.save()
    saved, _ = storage.load_map("Ordered")
    assert victim not in saved.names and victim not in saved.order
    assert saved.extra_lines == m.extra_lines
    assert [n for n in saved.order] == [n for n in m.order if n != victim]


def test_unsaved_prompt_on_switch(window, storage):
    page = window.maps_page
    storage.save_map(NoteMap("A", {36: "Kick"}))
    storage.save_map(NoteMap("B", {38: "Snare"}))
    page.reload_list()
    page.select(MapRef(USER, "A"))
    page.model.set_name(36, "Kick 2")

    page.answers["save_changes"] = "cancel"
    page.select(MapRef(USER, "B"))
    assert page.current == MapRef(USER, "A") and page.dirty
    assert page.list.current == MapRef(USER, "A")

    page.answers["save_changes"] = "save"
    page.select(MapRef(USER, "B"))
    assert page.current == MapRef(USER, "B")
    assert storage.load_map("A")[0].names[36] == "Kick 2"

    page.model.set_name(38, "Snare 2")
    page.answers["save_changes"] = "discard"
    page.select(MapRef(USER, "A"))
    assert storage.load_map("B")[0].names[38] == "Snare"


def test_close_with_unsaved_changes_can_be_cancelled(window, storage):
    page = window.maps_page
    storage.save_map(NoteMap("A", {36: "Kick"}))
    page.reload_list()
    page.select(MapRef(USER, "A"))
    page.model.set_name(36, "Kick 2")
    page.answers["save_changes"] = "cancel"
    window.show()
    assert not window.close()
    page.answers["save_changes"] = "discard"
    assert window.close()


def test_revert(window, storage):
    page = window.maps_page
    storage.save_map(NoteMap("A", {36: "Kick"}))
    page.reload_list()
    page.select(MapRef(USER, "A"))
    page.model.set_name(37, "Stick")
    page.strip.revert_action.trigger()  # «…» → Revert changes
    assert not page.dirty and page.work.names == {36: "Kick"} and not page.strip.save_btn.isEnabled()


def test_new_rename_delete(window, storage):
    page = window.maps_page
    page.answers["text"] = ["Fresh"]
    page.new_map()
    assert page.current == MapRef(USER, "Fresh") and not page.notes.named_only.isChecked()

    storage.save_map(NoteMap("Taken"))
    page.reload_list()
    page.answers["text"] = ["Taken", "Renamed"]  # первое имя занято — спросит ещё раз
    page.rename()
    assert page.answers["errors"] and "already exists" in page.answers["errors"][0]
    assert page.current == MapRef(USER, "Renamed")
    ids = [e.id for e in storage.list_maps()[0]]
    assert "Fresh" not in ids and "Renamed" in ids

    page.answers["confirm"] = False
    page.delete()
    assert "Renamed" in [e.id for e in storage.list_maps()[0]]
    page.answers["confirm"] = True
    page.delete()
    assert "Renamed" not in [e.id for e in storage.list_maps()[0]]
    assert page.current is None


def test_legacy_txt_map_marked_and_saved_as_json(window, storage):
    storage.maps_dir.mkdir(parents=True)
    shutil.copy(FIXTURE, storage.maps_dir / "Old.txt")
    page = window.maps_page
    page.reload_list()
    entry = page.list.entry(MapRef(USER, "Old"))
    assert entry.sub.startswith("legacy .txt") and "Legacy REAPER .txt map" in entry.tip
    page.select(MapRef(USER, "Old"))
    assert page.legacy and "Legacy REAPER .txt map" in page.strip.field.toolTip()
    n = next(iter(page.work.names))
    page.model.set_name(n, "Renamed note")
    assert page.save()
    assert (storage.maps_dir / "Old.json").is_file() and not (storage.maps_dir / "Old.txt").exists()
    assert not page.legacy


def test_import_shows_issues_after_import(window, storage, tmp_path):
    src = tmp_path / "broken.txt"
    src.write_text("# MIDI note/CC name map\n36 Kick\n300 Bad\nwhat is this\n", encoding="utf-8")
    page = window.maps_page
    page.choose_open_file = lambda: str(src)
    page.import_txt()  # имя не дали — отмена: ни карты, ни окна проблем
    assert storage.list_maps()[0] == [] and "issues" not in page.answers

    page.answers["text"] = ["Imported"]
    page.import_txt()
    m, _ = storage.load_map("Imported")
    assert m.names == {36: "Kick"} and m.meta.status == "unverified"
    assert page.current == MapRef(USER, "Imported")
    [(_title, text, details)] = page.answers["issues"]  # проблемы — сразу после импорта
    assert "2 issue(s)" in text and "line 3" in details


def test_export_full_map(window, storage, tmp_path):
    storage.save_map(NoteMap("Kit", {35: "Kick", 36: "Kick", 38: "Snare", 51: "Ride", 59: "Ride"},
                             primary={51}))
    page = window.maps_page
    page.reload_list()
    page.select(MapRef(USER, "Kit"))
    full = tmp_path / "full.txt"
    page.choose_save_file = lambda name: str(full)
    page.strip.export_btn.click()
    assert parse_notenames(full.read_text(encoding="utf-8"), "x")[0].names.keys() == {35, 36, 38, 51, 59}
    assert page.status.text() == f"Exported to {full}."


def test_maps_tab_disables_convert_shortcuts(window):
    assert not any(sc.isEnabled() for sc in window.convert_page._convert_shortcuts)
    window.show_page(0)
    assert all(sc.isEnabled() for sc in window.convert_page._convert_shortcuts)


def test_columns_without_write_to(window, storage):
    from remap.ui.maps_text import COLUMNS
    page = window.maps_page
    page.select(MapRef(TEMPLATE, "EZdrummer 3"))
    assert COLUMNS == ("NOTE", "NAME") and page.model.columnCount() == 2  # высоты (C#1) нет — только в подсказке
    m = page.model
    assert m.data(m.note_index(37, COL_NOTE), Qt.ItemDataRole.ToolTipRole) == "Note 37 · C#1"
    assert m.badge_tip(37) == "Also on notes 67, 127"  # «Snare: Sidestick» — на 3 нотах
    single = next(n for n in m.map.names if len(m.group(n)) == 1)
    assert m.data(m.note_index(single, COL_NOTE), Qt.ItemDataRole.ToolTipRole) == f"Note {single} · {pitch_name(single)}"
    assert not any("C#1" in str(m.data(m.note_index(37, c))) for c in (COL_NOTE, COL_NAME))
    assert "+N" in page.model.headerData(COL_NAME, Qt.Orientation.Horizontal, Qt.ItemDataRole.ToolTipRole)


def test_rows_grouped_by_instrument(window):
    from remap.core.notemap import instrument_group
    page = window.maps_page
    page.select(MapRef(TEMPLATE, "Superior Drummer 3"))
    m = page.model
    headers = [r for r in m.rows if r.is_header]
    assert m.grouped and "Kick" in [h.label for h in headers]
    # каждая нота стоит под заголовком своей группы
    current = None
    for r in m.rows:
        if r.is_header:
            current = r.label
        elif r.note in page.work.names:
            assert instrument_group(page.work.names[r.note]) == current
    # строка-заголовок на всю ширину и не выделяется
    h = page.proxy.index(0, 0)
    assert page.notes.table.columnSpan(0, 0) == 2
    assert not page.proxy.flags(h) & Qt.ItemFlag.ItemIsSelectable
    # General MIDI — группы по ключевым словам (префиксов нет)
    page.select(MapRef(TEMPLATE, "General MIDI"))
    labels = [r.label for r in page.model.rows if r.is_header]
    assert page.model.grouped and {"Kick", "Snare", "Toms", "Percussion"} <= set(labels)


def test_renamed_note_moves_to_its_group_after_save(window):
    page = window.maps_page
    page.select(MapRef(TEMPLATE, "EZdrummer 3"))
    page.answers["text"] = ["Mine"]
    page.duplicate()
    m = page.model
    m.set_name(38, "Cowbell: Hit")
    assert m.row_at(m.note_index(38, 0).row()).group == "snare"  # строка не уезжает при правке
    assert page.save()
    assert m.rows[m.note_index(38, 0).row()].group == "cowbell"


def test_note_table_sort_cycle_every_column(window, app):
    """Клик по заголовку: по возрастанию → по убыванию → снова группы; стрелка показывает состояние."""
    page = window.maps_page
    page.select(MapRef(TEMPLATE, "Superior Drummer 3"))
    m, header = page.model, page.notes.header
    assert m.grouped and m.sort is None and header.sort is None
    page.notes.table.setCurrentIndex(page.proxy.mapFromSource(m.note_index(38, COL_NAME)))

    def current():
        return m.note_at(page.proxy.mapToSource(page.notes.table.currentIndex()).row())

    names = page.work.names
    for col in (COL_NOTE,):  # колонки PITCH нет
        header.clicked.emit(col)
        notes = page.proxy.note_rows()
        assert m.sort == (col, False) and not m.grouped and notes == sorted(names)
        assert header.sort == (col, False)
        header.clicked.emit(col)
        assert m.sort == (col, True) and page.proxy.note_rows() == sorted(names, reverse=True)
        assert header.sort == (col, True) and current() == 38  # выбор сохранён
        header.clicked.emit(col)
        assert m.sort is None and m.grouped and header.sort is None  # третий клик — группы
    header.clicked.emit(COL_NAME)
    by_name = sorted(names, key=lambda n: (names[n].casefold(), n))
    assert m.sort == (COL_NAME, False) and page.proxy.note_rows() == by_name
    header.clicked.emit(COL_NAME)
    assert page.proxy.note_rows() == by_name[::-1]
    header.clicked.emit(COL_NOTE)  # другая колонка — сразу по возрастанию
    assert m.sort == (COL_NOTE, False)
    header.clicked.emit(COL_NOTE)
    header.clicked.emit(COL_NOTE)
    assert m.grouped and current() == 38
    # ноты без имени — в конце при любом направлении
    page.notes.named_only.setChecked(False)
    header.clicked.emit(COL_NAME)
    header.clicked.emit(COL_NAME)
    rows = page.proxy.note_rows()
    assert len(rows) == 128 and all(n not in names for n in rows[len(names):])




def test_map_list_screen_layout_and_keyboard(window, storage, app):
    """Заголовок 30, зазоры 6 (+2 под заголовком, +10 перед второй секцией), записи 46; ↑/↓/Home/End выбирают карты."""
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QKeyEvent

    from remap.ui.maps_list import layout_items
    storage.save_map(NoteMap("A", {36: "Kick"}))
    storage.save_map(NoteMap("B", {38: "Snare"}))
    page = window.maps_page
    page.reload_list()
    items, height = layout_items(page.list.sections, 218)
    tops = [(it.rect.top(), it.rect.height()) for it in items]
    n = len(page.list.sections[0].entries)
    assert tops[:3] == [(0, 30), (38, 46), (90, 46)]
    assert tops[n + 1] == (30 + 8 + n * 52 - 6 + 16, 30)
    assert height == tops[-1][0] + 46
    body = page.list.area.widget()
    page.select(MapRef(USER, "A"))
    for key, want in ((Qt.Key.Key_Down, MapRef(USER, "B")), (Qt.Key.Key_Home, page.list.refs()[0]),
                      (Qt.Key.Key_End, MapRef(USER, "B")), (Qt.Key.Key_Up, MapRef(USER, "A"))):
        app.sendEvent(body, QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier))
        assert page.current == want and page.list.current == want


def test_empty_my_maps_shows_message_entry(window):
    mine = window.maps_page.list.sections[1]
    assert [(e.name, e.ref) for e in mine.entries] == [("No maps yet", None)]


# --- экран нот ---

def test_named_only_remembered_in_ui_ini(window, storage, app):
    page = window.maps_page
    assert page.notes.named_only.isChecked()  # по умолчанию включён
    page.select(MapRef(TEMPLATE, "EZdrummer 3"))  # без карты флажок недоступен
    page.notes.named_only.click()
    assert not page.notes.named_only.isChecked() and not page.proxy.named_only
    w2 = MainWindow(storage)
    assert not w2.maps_page.notes.named_only.isChecked() and not w2.maps_page.proxy.named_only
    w2.close()
    # новая пустая карта снимает флажок сама — это не выбор пользователя, в ui.ini не пишется
    page.notes.named_only.click()
    page.answers["text"] = ["Fresh"]
    page.new_map()
    assert not page.notes.named_only.isChecked()
    w3 = MainWindow(storage)
    assert w3.maps_page.notes.named_only.isChecked()
    w3.close()


def test_group_collapses_and_unnamed_group_last(window):
    page = window.maps_page
    page.select(MapRef(TEMPLATE, "Superior Drummer 3"))
    page.notes.named_only.setChecked(False)
    view = page.notes.table
    heads = [page.proxy.source_row(r) for r in range(page.proxy.rowCount())]
    labels = [h.label for h in heads if h.is_header]
    assert labels[-1] == "Unnamed" and labels[0] == "Kick"
    unnamed = [h.note for h in heads if not h.is_header and h.group == heads[-1].group]
    assert unnamed and all(n not in page.work.names for n in unnamed)
    assert view.rowHeight(0) == 30 and view.rowHeight(1) == 28 and view.columnSpan(0, 0) == 2
    kick = sorted(n for n, name in page.work.names.items() if name.startswith("Kick"))
    view.group_clicked.emit(heads[0].group)  # свернуть Kick: заголовок остаётся, ноты скрыты
    assert heads[0].group in page.proxy.collapsed
    assert page.proxy.source_row(0).is_header and not set(kick) & set(page.proxy.note_rows())
    view.group_clicked.emit(heads[0].group)
    assert set(kick) <= set(page.proxy.note_rows())


def test_in_row_name_edit_enter_saves_esc_cancels(window, storage, app):
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtWidgets import QLineEdit
    storage.save_map(NoteMap("Kit", {36: "Kick", 38: "Snare"}))
    page = window.maps_page
    page.reload_list()
    page.select(MapRef(USER, "Kit"))
    window.resize(*theme.WINDOW_SIZE)
    window.show()
    app.processEvents()
    view, totals = page.notes.table, page.notes.totals
    assert totals.left == "2 NAMED NOTES" and totals.right == ""

    def start(note):
        idx = page.proxy.mapFromSource(page.model.note_index(note, COL_NOTE))  # щелчок по номеру — правка имени
        view.setCurrentIndex(idx)
        view.edit(idx)
        app.processEvents()
        editor = view.findChild(QLineEdit)
        assert editor is not None and editor.isVisible() and editor.text() == page.work.names[note]
        assert editor.height() == 22 and editor.width() >= 180
        assert totals.right.startswith("ENTER · SAVE NAME")
        return editor

    editor = start(38)
    editor.setText("Snare: Center")
    app.sendEvent(editor, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier))
    app.processEvents()
    assert page.work.names[38] == "Snare: Center" and page.dirty and totals.right == ""
    editor = start(36)
    editor.setText("Something else")
    app.sendEvent(editor, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
    app.processEvents()
    assert page.work.names[36] == "Kick" and totals.right == ""
    # у шаблона правки нет: справа — READ-ONLY TEMPLATE
    page.answers["save_changes"] = "discard"
    page.select(MapRef(TEMPLATE, "EZdrummer 3"))
    assert totals.right == "READ-ONLY TEMPLATE"


def test_totals_show_map_errors_in_error_colour(window, storage):
    storage.save_map(NoteMap("Bad", {35: "Kick", 36: "Kick", 38: "Snare"}, primary={35, 36}))
    page = window.maps_page
    page.reload_list()
    page.select(MapRef(USER, "Bad"))
    totals = page.notes.totals
    assert totals.error and totals.left == "1 ERROR IN THE MAP"
    assert "several Write to notes" in totals.toolTip()
    page.close_map()
    assert not totals.error and totals.left == "SELECT A MAP ON THE LEFT, OR CREATE ONE."


def test_note_and_badge_tooltips(window, storage, app):
    from PySide6.QtCore import QPoint
    from remap.ui import plates
    storage.save_map(NoteMap("Kit", {35: "Kick", 36: "Kick", 38: "Snare"}))
    page = window.maps_page
    page.reload_list()
    page.select(MapRef(USER, "Kit"))
    window.resize(*theme.WINDOW_SIZE)
    window.show()
    app.processEvents()
    view = page.notes.table
    note_cell = view.visualRect(page.proxy.mapFromSource(page.model.note_index(35, COL_NOTE)))
    assert view.tooltip_at(note_cell.center()) == "Note 35 · B0"
    name_cell = view.visualRect(page.proxy.mapFromSource(page.model.note_index(35, COL_NAME)))
    _, pill = plates.note_badge_rect(name_cell.toRectF(), "Kick", "+1")
    assert view.tooltip_at(pill.center().toPoint()) == "Also on note 36"
    assert view.tooltip_at(QPoint(name_cell.left() + 5, name_cell.center().y())) == ""  # имя не обрезано


def test_import_with_issues_can_be_discarded(window, storage, tmp_path):
    src = tmp_path / "broken.txt"
    src.write_text("# MIDI note/CC name map\n36 Kick\n300 Bad\n", encoding="utf-8")
    storage.save_map(NoteMap("Before", {38: "Snare"}))
    page = window.maps_page
    page.reload_list()
    page.select(MapRef(USER, "Before"))
    page.choose_open_file = lambda: str(src)
    page.answers["text"] = ["Imported"]
    page.answers["keep"] = False  # «Discard import»
    page.import_txt()
    assert page.answers["issues"]
    assert [e.id for e in storage.list_maps()[0]] == ["Before"]
    assert page.current == MapRef(USER, "Before") and MapRef(USER, "Imported") not in page.list.refs()
    assert page.status.text() == "Import discarded."
