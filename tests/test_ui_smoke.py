"""Смоук-тесты главного окна PySide6 (без pytest-qt, платформа Qt offscreen)."""
import shutil
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytestmark = pytest.mark.ui

from PySide6.QtCore import QMimeData, Qt, QUrl
from PySide6.QtWidgets import QApplication

from remap.core import RemapProfile, Rule, convert, legacy_profile
from remap.storage import Storage
from remap.ui.convert_page import midi_paths_from_mime
from remap.ui.convert_text import batch_summary, format_report, report_summary
from remap.ui.main_window import MainWindow

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "midi" / "Groove 01.mid"


@pytest.fixture
def window(app, tmp_path):
    w = MainWindow(Storage(tmp_path / "store"))
    yield w
    w.close()
    w.deleteLater()


def test_window_constructs_with_seeded_legacy_profile(window):
    assert window.windowTitle() == "REMAP"
    assert window.convert_page.profile_combo.count() == 1
    assert window.convert_page.profile_combo.currentText() == legacy_profile().name
    assert window.convert_page.selected_profile().rules == legacy_profile().rules


def test_profiles_from_storage_listed(app, tmp_path):
    storage = Storage(tmp_path / "store")
    storage.save_profile(RemapProfile(name="Мой профиль", rules={36: Rule.map_to(35)}))
    (storage.profiles_dir / "broken.json").write_text("{", encoding="utf-8")
    w = MainWindow(storage)  # папка профилей уже есть — legacy не засевается
    assert [w.convert_page.profile_combo.itemText(i) for i in range(w.convert_page.profile_combo.count())] == ["Мой профиль"]
    assert "broken.json" in w.convert_page.status.text()
    assert w.convert_page.selected_profile().rules == {36: Rule.map_to(35)}
    w.close()


def test_load_convert_and_copy(window, tmp_path, app):
    src = tmp_path / "groove.mid"
    shutil.copy(SAMPLE, src)
    window.convert_page.load(src)
    assert window.convert_page.source == src.resolve()
    window.convert_page.convert()
    out = tmp_path / "groove_remapped.mid"
    assert out.is_file() and window.convert_page.output == out.resolve()
    # секции REPORT нет: итог — под именем файла, полный отчёт — в окне Details
    for gone in ("report_view", "report_summary", "details_btn", "batch_area", "batch_box"):
        assert not hasattr(window, gone)
    (row,) = rows(window)
    assert row.state in ("ok", "warn") and " hits · " in row.line and not row.line.startswith("✓")
    dlg = window.convert_page.details_dialog(src.resolve())
    assert "Moved:" in dlg.view.toPlainText() and dlg.view.isReadOnly()
    dlg.deleteLater()

    window.convert_page.copy_output()
    urls = app.clipboard().mimeData().urls()
    assert [Path(u.toLocalFile()) for u in urls] == [out.resolve()]


def test_convert_without_file_does_not_crash(window):
    window.convert_page.convert()
    assert window.convert_page.output is None
    assert window.convert_page.status.property("state") == "error"


def test_midi_paths_from_mime(tmp_path):
    mid, txt = tmp_path / "a.MID", tmp_path / "b.txt"
    mid.write_bytes(b"")
    txt.write_text("x")
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(txt)), QUrl.fromLocalFile(str(mid))])
    assert midi_paths_from_mime(mime) == [mid]
    text_only = QMimeData()
    text_only.setText(f'"{mid}"')
    assert midi_paths_from_mime(text_only) == [mid]


def test_format_report_and_summary_use_one_vocabulary(tmp_path):
    """hits — note_on, notes — номера; категории moved / unchanged / deleted одинаковы в итоге и в Details."""
    profile = RemapProfile(name="p", rules={36: Rule.map_to(35), 38: Rule.delete(), 42: Rule.map_to(42)})
    report = convert(SAMPLE, tmp_path / "out.mid", profile)
    t = report.totals()
    text = format_report(report)
    for part in ("Total:", "Moved:", "Unchanged:", "Deleted:", "Merged duplicates", "Overlaps", "Notes:"):
        assert part in text
    assert "Remapped" not in text and "Kept as is" not in text
    assert f"Moved: {t.moved.hits} hits ({t.moved.notes} note" in text
    assert f"Unchanged: {t.unchanged.hits} hits ({t.unchanged.notes} notes)" in text
    assert f"Deleted: {t.deleted.hits} hit" in text
    w = len(report.warnings)
    parts = [f"{t.hits} hits"] + [f"{n} {word}" for n, word in (
        (t.moved.hits, "moved"), (t.unchanged.hits, "unchanged"), (t.deleted.hits, "deleted")) if n]
    parts += [f"{w} warning" + ("" if w == 1 else "s")] if w else []  # нули (кроме hits) не пишутся
    assert report_summary(report) == " · ".join(parts)
    assert t.moved.hits + t.unchanged.hits + t.deleted.hits == t.hits
    assert "notes converted" not in report_summary(report)  # «notes» — не про hits


def test_batch_summary_wording():
    assert batch_summary(3, 1) == "3 files converted, 1 failed"
    assert batch_summary(1, 0) == "1 file converted"
    assert batch_summary(0, 2) == "0 files converted, 2 failed"


def test_window_default_size_fits_screen(window):
    area = window.screen().availableGeometry()
    assert window.width() == max(min(1280, int(area.width() * 0.9)), window.minimumWidth())
    assert window.height() == max(min(800, int(area.height() * 0.9)), window.minimumHeight())
    assert (window.minimumWidth(), window.minimumHeight()) == (900, 580)


# --- пакетная конвертация на вкладке Convert ---

def _files(tmp_path, *names):
    out = []
    for name in names:
        f = tmp_path / name
        shutil.copy(SAMPLE, f)
        out.append(f)
    return out


def test_midi_paths_from_mime_expands_folder_without_recursion(tmp_path):
    folder = tmp_path / "set"
    (folder / "deep").mkdir(parents=True)
    for name in ("b.mid", "A.MIDI", "notes.txt"):
        (folder / name).write_bytes(b"")
    (folder / "deep" / "c.mid").write_bytes(b"")
    single = tmp_path / "x.mid"
    single.write_bytes(b"")
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(single)), QUrl.fromLocalFile(str(folder))])
    assert midi_paths_from_mime(mime) == [single, folder / "A.MIDI", folder / "b.mid"]


def rows(window):
    return window.convert_page.input.rows()


def test_several_files_list_remove_and_clear(window, tmp_path):
    screen = window.convert_page.input
    assert screen.header.count == "" and not screen.clear_btn.isEnabled() and rows(window) == []
    a, b, c = _files(tmp_path, "a.mid", "b.mid", "c.mid")
    window.convert_page._accept_files([a, b, c, a])  # повтор не добавляется
    assert window.convert_page.sources == [a.resolve(), b.resolve(), c.resolve()]
    assert [r.path.name for r in rows(window)] == ["a.mid", "b.mid", "c.mid"] and screen.header.count == "3 FILES"
    assert [(c.path.name, c.ready) for c in cards(window)] == [
        ("a_remapped.mid", False), ("b_remapped.mid", False), ("c_remapped.mid", False)]
    assert cards(window)[0].path.parent == a.resolve().parent  # будущие — рядом с исходниками
    window.convert_page.remove_source(b.resolve())
    assert window.convert_page.sources == [a.resolve(), c.resolve()] and screen.header.count == "2 FILES"
    window.convert_page.remove_source(a.resolve())
    assert [r.path.name for r in rows(window)] == ["c.mid"] and screen.header.count == "1 FILE"
    window.convert_page._accept_files([a, b])
    screen.clear_btn.click()
    assert window.convert_page.sources == [] and rows(window) == []


def test_drop_dialog_and_paste_add_to_the_list(window, tmp_path, app, monkeypatch):
    from PySide6.QtCore import QMimeData, QUrl
    from PySide6.QtWidgets import QFileDialog
    a, b, c = _files(tmp_path, "a.mid", "b.mid", "c.mid")
    window.convert_page._accept_files([a])
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *args: ([str(b), str(a)], ""))
    window.convert_page.choose_file()  # диалог — добавляет, повтор a не дублируется
    assert window.convert_page.sources == [a.resolve(), b.resolve()]
    assert window.convert_page.status.text().startswith("Added 1 file · 2 in the list")
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(c))])
    app.clipboard().setMimeData(mime)
    window.convert_page.paste_file()  # Ctrl+V — тоже добавляет
    assert window.convert_page.sources == [a.resolve(), b.resolve(), c.resolve()]
    window.convert_page._accept_files([c])
    assert window.convert_page.status.text() == "Already in the list." and len(window.convert_page.sources) == 3
    window.convert_page.input.clear_btn.click()  # «Clear all» — заново
    assert window.convert_page.sources == []
    window.convert_page._accept_files([b])
    assert window.convert_page.sources == [b.resolve()]
    window.convert_page.load(a)  # load() заменяет
    assert window.convert_page.sources == [a.resolve()]


def cards(window):
    return window.convert_page.output_screen.cards()


def test_copy_takes_selected_cards_or_all(window, tmp_path, app):
    output = window.convert_page.output_screen
    copy = output.copy_btn
    assert not copy.isEnabled() and "Copy all files (Ctrl+C)" in copy.toolTip()
    a, b, c = _files(tmp_path, "a.mid", "b.mid", "c.mid")
    window.convert_page._accept_files([a, b, c])
    assert not copy.isEnabled()  # будущие результаты не копируются
    window.convert_page.convert()
    assert copy.isEnabled() and len(window.convert_page.outputs) == 3
    copy.click()  # ничего не выделено — все
    assert [Path(u.toLocalFile()).name for u in app.clipboard().mimeData().urls()] == [
        "a_remapped.mid", "b_remapped.mid", "c_remapped.mid"]
    output.card_pressed(cards(window)[1].path, Qt.KeyboardModifier.NoModifier)
    assert "Copy the selected files (Ctrl+C)" in copy.toolTip()
    window.convert_page.copy_output()  # Ctrl+C — то же, что COPY: выделенные
    assert [Path(u.toLocalFile()).name for u in app.clipboard().mimeData().urls()] == ["b_remapped.mid"]


def test_failed_file_shows_first_error_line_under_its_name(window, tmp_path):
    from remap.core import FileResult
    from remap.ui.convert_text import result_details, result_line
    res = FileResult(tmp_path / "x.mid", tmp_path / "x_remapped.mid", error="Bad header\nat byte 14\nchunk MThd")
    assert result_line(res) == "Bad header" and result_details(res) == res.error
    a, b = _files(tmp_path, "a.mid", "b.mid")
    window.convert_page._accept_files([a, b])
    window.convert_page.results = {a.resolve(): res}
    window.convert_page.input.set_files(window.convert_page.sources, window.convert_page.results)
    first, second = rows(window)
    assert first.line == "Bad header" and first.state == "error" and first.details_rect() is not None
    tooltip = first.tooltip_at(first.line_rect().center())
    assert "Not converted" in tooltip and "at byte 14" in tooltip  # смысл ошибки — в подсказке строки и LED
    assert "Not converted" in first.tooltip_at(first.led_rect().center())
    assert second.line == "Ready" and second.state == "ready" and second.details_rect() is None


def test_single_file_row_before_conversion(window, tmp_path):
    (a,) = _files(tmp_path, "a.mid")
    window.convert_page.load(a)
    (row,) = rows(window)
    assert row.path.name == "a.mid" and row.line == "Ready" and row.state == "ready"
    assert str(a.resolve()) in row.tooltip_at(row.rect().center())  # полный путь — в подсказке строки
    assert window.convert_page.input.totals.isHidden()  # до конвертации итогов нет
    assert [(c.path.name, c.ready) for c in cards(window)] == [("a_remapped.mid", False)]


def test_convert_several_files_with_one_failure(window, tmp_path):
    a, c = _files(tmp_path, "a.mid", "c.mid")
    bad = tmp_path / "b.mid"
    bad.write_bytes(b"not midi")
    window.convert_page._accept_files([a, bad, c])
    window.convert_page.convert()
    assert [p.name for p in window.convert_page.outputs] == ["a_remapped.mid", "c_remapped.mid"]
    assert window.convert_page.status.text() == "2 files converted, 1 failed" and window.convert_page.status.property("state") == "error"
    shown = rows(window)
    assert [r.path.name for r in shown] == ["a.mid", "b.mid", "c.mid"]
    assert " hits · " in shown[0].line and shown[0].state != "error"
    assert shown[1].line == "Not a MIDI file" and shown[1].state == "error"
    assert all(r.details_rect() is not None for r in shown)  # у каждой строки — DETAILS
    totals = window.convert_page.input.totals
    assert not totals.isHidden() and totals.text.startswith("2 CONVERTED") and totals.text.endswith("1 FAILED")
    assert not (tmp_path / "b_remapped.mid").exists()
    dlg = window.convert_page.details_dialog(a.resolve())
    assert dlg.view.toPlainText().startswith("Profile:") and "Moved:" in dlg.view.toPlainText()
    dlg.copy()
    assert QApplication.clipboard().text() == dlg.view.toPlainText()  # Copy — весь текст
    assert window.convert_page.details_dialog(bad.resolve()).view.toPlainText() == NOT_MIDI_DETAILS
    assert [(c.path.name, c.ready) for c in cards(window)] == [("a_remapped.mid", True), ("c_remapped.mid", True)]
    window.convert_page.remove_source(c.resolve())  # убрали файл — пропали только его результат и карточка
    assert list(window.convert_page.results) == [a.resolve(), bad.resolve()] and window.convert_page.outputs == [tmp_path / "a_remapped.mid"]
    assert [r.state for r in rows(window)][1] == "error" and [c.path.name for c in cards(window)] == ["a_remapped.mid"]
    # добавление файлов результаты не сбрасывает: у нового — «Ready», у прежних — их итог
    window.convert_page._accept_files([_files(tmp_path, "d.mid")[0]])
    assert set(window.convert_page.results) == {a.resolve(), bad.resolve()}
    assert [r.state for r in rows(window)][-1] == "ready" and rows(window)[0].line != "Ready"
    assert not window.convert_page.input.totals.isHidden()


def test_convert_several_files_to_output_folder_and_reset(window, tmp_path):
    d1, d2 = tmp_path / "one", tmp_path / "two"
    d1.mkdir()
    d2.mkdir()
    a, b = _files(d1, "groove.mid")[0], _files(d2, "groove.mid")[0]
    other = _files(tmp_path, "solo.mid")[0]
    out = tmp_path / "results"
    window.convert_page.ask_output_folder = lambda start: str(out)
    convert = window.convert_page
    assert [a.text() for a in convert.output_menu.actions()] == ["Next to source files", "Choose folder…"]
    assert convert.output_btn.text() == "Next to source files" and convert.output_next_action.isChecked()
    convert.output_choose_action.trigger()
    assert window.convert_page.output_dir == out and convert.output_btn.text() == str(out)
    assert not convert.output_next_action.isChecked() and str(out) in convert.output_btn.toolTip()
    window.convert_page._accept_files([a, b, other])
    assert {c.path.parent for c in cards(window)} == {out}
    window.convert_page.convert()
    # одинаковые имена в общей папке — ошибка, а не молчаливая перезапись
    assert window.convert_page.status.text() == "2 files converted, 1 failed"
    assert "collides" in rows(window)[1].line
    assert sorted(p.name for p in out.iterdir()) == ["groove_remapped.mid", "solo_remapped.mid"]
    assert not (d1 / "groove_remapped.mid").exists()
    convert.output_next_action.trigger()
    assert window.convert_page.output_dir is None and convert.output_next_action.isChecked() and window.convert_page.outputs == []
    assert convert.output_btn.text() == "Next to source files"
    window.convert_page.convert()
    assert (d1 / "groove_remapped.mid").is_file() and (d2 / "groove_remapped.mid").is_file()
    assert window.convert_page.status.text() == "3 files converted"


def test_output_folder_applies_to_single_file(window, tmp_path):
    (a,) = _files(tmp_path, "a.mid")
    out = tmp_path / "res"
    window.convert_page.set_output_dir(out)
    window.convert_page.load(a)
    assert cards(window)[0].path == out / "a_remapped.mid"
    window.convert_page.convert()
    assert (out / "a_remapped.mid").is_file() and not (tmp_path / "a_remapped.mid").exists()
    assert window.convert_page.status.text() == "Converted: a_remapped.mid"


NOT_MIDI_DETAILS = "Not a MIDI file\n\nTechnical details:\nOSError: MThd not found. Probably not a MIDI file"


def test_single_file_failure_shows_in_its_row(window, tmp_path):
    bad = tmp_path / "bad.mid"
    bad.write_bytes(b"not midi")
    window.convert_page.load(bad)
    shown = []
    window.convert_page.show_error = shown.append
    window.convert_page.convert()
    assert shown == [] and window.convert_page.outputs == []  # как у пакета: без окна ошибки
    assert window.convert_page.status.text() == "Conversion failed." and window.convert_page.status.property("state") == "error"
    (row,) = rows(window)
    assert row.line == "Not a MIDI file" and row.state == "error" and row.details_rect() is not None
    assert window.convert_page.details_dialog(bad.resolve()).view.toPlainText() == NOT_MIDI_DETAILS


def test_truncated_file_row_shows_plain_message_details_show_exception(window, tmp_path):
    (src,) = _files(tmp_path, "cut.mid")
    src.write_bytes(src.read_bytes()[:40])
    window.convert_page.load(src)
    window.convert_page.convert()
    assert rows(window)[0].line == "The file is damaged or truncated"  # не «EOFError»
    assert window.convert_page.details_dialog(src.resolve()).view.toPlainText() == (
        "The file is damaged or truncated\n\nTechnical details:\nEOFError")


def test_copy_several_outputs_as_file_urls(window, tmp_path, app):
    a, b = _files(tmp_path, "a.mid", "b.mid")
    window.convert_page._accept_files([a, b])
    window.convert_page.convert()
    window.convert_page.copy_output()
    urls = app.clipboard().mimeData().urls()
    assert [Path(u.toLocalFile()) for u in urls] == [tmp_path / "a_remapped.mid", tmp_path / "b_remapped.mid"]
    assert window.convert_page.status.text().startswith("2 output files copied")


def test_report_summary_hides_zero_parts_except_hits():
    from remap.core.convert import ConversionReport, NoteResult
    empty = ConversionReport()
    assert report_summary(empty) == "0 hits"
    moved = ConversionReport(notes={36: NoteResult(src=36, count=52, action="map", dst=35, origin="profile")})
    assert report_summary(moved) == "52 hits · 52 moved"
