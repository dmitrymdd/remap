"""Экран OUTPUT вкладки Convert: геометрия по макету, карточки, выделение, перетаскивание, двойной клик, Ctrl+A."""
import shutil
import sys
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from remap.storage import Storage
from remap.ui.main_window import PAGE_CONVERT, MainWindow

pytestmark = pytest.mark.ui

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "midi" / "Groove 01.mid"
CTRL = Qt.KeyboardModifier.ControlModifier


@pytest.fixture
def window(app, tmp_path):
    w = MainWindow(Storage(tmp_path / "store"))
    w.resize(900, 800)
    w.show()
    w.show_page(PAGE_CONVERT)
    yield w
    w.close()
    w.deleteLater()


def converted(window, tmp_path, *names, bad=()):
    paths = []
    for name in names:
        shutil.copy(SAMPLE, tmp_path / name)
        paths.append(tmp_path / name)
    for name in bad:
        (tmp_path / name).write_bytes(b"not midi")
        paths.append(tmp_path / name)
    window.convert_page._accept_files(paths)
    window.convert_page.convert()
    QApplication.processEvents()
    return window.convert_page.output_screen


def test_screen_and_cards_follow_the_mockup(window, tmp_path):
    screen = converted(window, tmp_path, "a.mid", "b.mid")
    origin = screen.mapTo(window, QPoint(0, 0))
    assert QRect(origin, screen.size()) == QRect(600, 139, 268, 551)  # лицо блока 268×548 в (600, 140)
    first, second = screen.cards()
    pos = first.mapTo(window, QPoint(0, 0))
    assert (pos.x(), pos.y(), first.width(), first.height()) == (621, 199, 226, 54)
    assert second.mapTo(window, QPoint(0, 0)).y() - pos.y() == 62  # карточка 54 + зазор 8
    assert first.text_x() == 43  # значок 22 с полем 10 и зазор 10
    key = window.convert_page.convert_btn
    face = key.face_rect().translated(key.mapTo(window, QPoint(0, 0)).toPointF())
    assert (face.y(), face.height()) == (700, 68)  # лицо CONVERT — в 12 px под лицом OUTPUT
    assert screen.footer.text == "DRAG INTO YOUR DAW"


def test_planned_cards_and_failed_files(window, tmp_path):
    screen = converted(window, tmp_path, "a.mid", bad=("b.mid",))
    assert [(c.path.name, c.ready) for c in screen.cards()] == [("a_remapped.mid", True)]  # у ошибки карточки нет
    shutil.copy(SAMPLE, tmp_path / "c.mid")
    window.convert_page._accept_files([tmp_path / "c.mid"])  # добавление результаты не сбрасывает
    assert [(c.path.name, c.ready) for c in screen.cards()] == [("a_remapped.mid", True), ("c_remapped.mid", False)]


def test_folder_line_is_elided_in_the_middle(window, tmp_path):
    deep = tmp_path / "a_very_long_folder_name_for_the_card" / "and_another_long_one" / "Song"
    deep.mkdir(parents=True)
    screen = converted(window, deep, "a.mid")
    (card,) = screen.cards()
    shown = card.folder_label()
    assert "…" in shown and shown.endswith("Song") and shown[:2] == str(deep)[:2]  # видны диск и сама папка


def test_drag_takes_selected_or_only_the_card(window, tmp_path, monkeypatch):
    screen = converted(window, tmp_path, "a.mid", "b.mid", "c.mid")
    a, b, c = screen.cards()
    def names(card):
        return [p.name for p in screen.ready_targets(card)]

    assert names(b) == ["b_remapped.mid"]  # ничего не выделено — только она
    screen.card_pressed(a.path, Qt.KeyboardModifier.NoModifier)
    screen.card_pressed(c.path, CTRL)
    assert names(a) == ["a_remapped.mid", "c_remapped.mid"] and names(b) == ["b_remapped.mid"]
    dragged = []
    monkeypatch.setattr(screen, "drag_from", lambda card: dragged.append(names(card)))
    QTest.mousePress(c, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(20, 20))
    QTest.mouseMove(c, QPoint(60, 40))
    QTest.mouseRelease(c, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(60, 40))
    assert dragged == [["a_remapped.mid", "c_remapped.mid"]]  # нажатие на выделенную не сбросило выделение
    QTest.mouseClick(c, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(20, 20))
    assert [p.name for p in screen.selection.selected] == ["c_remapped.mid"]  # клик без перетаскивания — только она


def test_ctrl_a_goes_to_the_last_clicked_screen_and_delete_stays_on_input(window, tmp_path):
    screen = converted(window, tmp_path, "a.mid", "b.mid")
    page = window.convert_page
    QTest.keyClick(window, Qt.Key.Key_A, CTRL)  # по умолчанию — INPUT
    assert len(page.input.selection) == 2 and len(screen.selection) == 0
    page.input.clear_selection()
    QTest.mouseClick(screen.cards()[0], Qt.MouseButton.LeftButton)
    QTest.keyClick(window, Qt.Key.Key_A, CTRL)
    assert len(screen.selection) == 2 and len(page.input.selection) == 0
    QTest.keyClick(window, Qt.Key.Key_Delete)  # Delete убирает только строки INPUT — там ничего не выделено
    assert len(page.sources) == 2


def test_convert_key_follows_the_mockup_and_needs_profile_and_files(window, tmp_path):
    page = window.convert_page
    key = page.convert_btn
    face = key.face_rect().translated(key.mapTo(window, QPoint(0, 0)).toPointF())
    assert face.toRect() == QRect(600, 700, 268, 68) and key.lit and key.text() == "Convert"
    assert key.icon_name == "go-arrow" and not key.isEnabled() and "Add .mid files" in key.toolTip()
    shutil.copy(SAMPLE, tmp_path / "a.mid")
    page._accept_files([tmp_path / "a.mid"])
    assert key.isEnabled() and "Convert (Enter)" in key.toolTip()
    window.activateWindow()  # горячие клавиши окна — у активного окна
    QApplication.processEvents()
    QTest.keyClick(window, Qt.Key.Key_Return)  # Enter = CONVERT
    assert page.output_screen.cards()[0].ready


def test_profile_without_target_map_gives_ok_rows(window, tmp_path):
    """Встроенный профиль без карт: «нет целевой карты» — про профиль (Details и подсказка TARGET), строки — ok."""
    page = window.convert_page
    converted(window, tmp_path, "a.mid", "b.mid")
    assert [r.state for r in page.input.rows()] == ["ok", "ok"]
    assert page.input.totals.text == "2 CONVERTED"
    res = page.results[(tmp_path / "a.mid").resolve()]
    assert res.report.warnings == [] and "no target map" in res.report.profile_notes[0]
    assert "Notes:" in page.details_dialog(res.src).view.toPlainText()
    assert "target notes are not checked" in page.target_field.toolTip()


def test_results_reset_only_on_profile_direction_or_folder_change(window, tmp_path):
    page = window.convert_page
    converted(window, tmp_path, "a.mid")
    shutil.copy(SAMPLE, tmp_path / "b.mid")
    page._accept_files([tmp_path / "b.mid"])
    assert len(page.results) == 1  # добавление — не сброс
    page.toggle_direction()
    assert page.results == {}  # направление сменилось
    page.toggle_direction()
    page.convert()
    page.set_output_dir(tmp_path / "out")
    assert page.results == {}  # папка сменилась
    page.set_output_dir(None)
    page.convert()
    page.reload_profiles()  # тот же профиль (сохранили другой профиль на Profiles) — результаты остаются
    assert len(page.results) == 2


def test_results_reset_when_current_profile_is_resaved_with_other_rules(window, tmp_path):
    page = window.convert_page
    converted(window, tmp_path, "a.mid")
    profile_id = page.profile_combo.currentData()
    profile = window.storage.load_profile(profile_id)
    page.reload_profiles()  # пересохранили без изменений — результаты остаются
    assert len(page.results) == 1
    profile.rules.pop(next(iter(profile.rules)))
    window.storage.save_profile(profile, profile_id=profile_id, overwrite=True)
    page.reload_profiles()  # так Profiles сообщает о сохранении (profiles_changed)
    assert page.profile_combo.currentData() == profile_id
    assert page.results == {}  # тот же профиль с другими правилами — как смена профиля


def _same_named(tmp_path, *names):
    paths = []
    for folder, name in zip(("one", "two", "three"), names, strict=False):
        (tmp_path / folder).mkdir()
        shutil.copy(SAMPLE, tmp_path / folder / name)
        paths.append((tmp_path / folder / name).resolve())
    return paths


def test_same_named_sources_with_one_output_folder(window, tmp_path):
    """Два «a.mid» из разных папок и общая папка результатов: до конвертации — как сделает CONVERT. У первого —
    будущая карточка, у второго карточки нет, его строка — предупреждение с подсказкой, чей результат занял имя;
    после CONVERT пишется только первый, второй — ошибкой, файл первого не перезаписан."""
    first, second = _same_named(tmp_path, "a.mid", "a.mid")
    page = window.convert_page
    page.set_output_dir(tmp_path / "out")
    page._accept_files([first, second])
    screen = page.output_screen
    card, = screen.cards()
    assert card.path == tmp_path / "out" / "a_remapped.mid" and not card.ready
    ok_row, clash_row = page.input._rows
    assert (ok_row.state, ok_row.line) == ("ready", "Ready")
    assert clash_row.state == "warn" and clash_row.line == "Output name taken · will be skipped"
    tip_html = clash_row.tooltip_at(clash_row.line_rect().center())
    assert "Will not be converted" in tip_html and str(first) in tip_html
    page.convert()
    QApplication.processEvents()
    assert [(c.path.name, c.ready) for c in screen.cards()] == [("a_remapped.mid", True)]
    ok, clash = (page.results[s] for s in (first, second))
    assert ok.ok and not clash.ok and "collides" in clash.error
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == ["a_remapped.mid"]


def test_name_conflict_clears_when_its_cause_goes(window, tmp_path):
    """Конфликт уходит вместе с причиной: убрали первый файл — второй снова «Ready» со своей карточкой; рядом с
    исходниками имена не сталкиваются. Регистр имени на Windows не важен (A.MID и a.mid — одно имя)."""
    first, second = _same_named(tmp_path, "a.mid", "A.MID" if sys.platform == "win32" else "a.mid")
    page = window.convert_page
    page.set_output_dir(tmp_path / "out")
    page._accept_files([first, second])
    assert [r.state for r in page.input._rows] == ["ready", "warn"] and len(page.output_screen.cards()) == 1
    page.set_output_dir(None)
    assert [r.state for r in page.input._rows] == ["ready", "ready"]
    assert {c.path.parent for c in page.output_screen.cards()} == {first.parent, second.parent}
    page.set_output_dir(tmp_path / "out")
    page.remove_sources([first])
    row, = page.input._rows
    assert (row.state, row.line) == ("ready", "Ready")
    card, = page.output_screen.cards()
    assert card.path.parent == tmp_path / "out" and not card.ready
