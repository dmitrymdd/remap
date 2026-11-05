"""Ряд экранов с перетаскиваемым зазором (`ui/split.py`) и формула секций полосы над ним (`ui/strip.py`)."""
import pytest
from PySide6.QtCore import QPoint, QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QWidget

from remap.ui import theme
from remap.ui.split import SplitRow
from remap.ui.strip import section_width

pytestmark = pytest.mark.ui

PAGE_W = theme.WINDOW_SIZE[0] - 2 * theme.PAGE_MARGIN  # 836: ширина ряда в окне макета
WIDE_W = 1600 - 2 * theme.PAGE_MARGIN
H = 400

# (side_first, side_min, main_min) — Profiles / Maps: колонка слева; Convert: OUTPUT справа
LEFT = (True, theme.POOL_W, theme.SCENE_W)
RIGHT = (False, theme.CONVERT_RIGHT_W, theme.CONVERT_INPUT_W)


def make_row(kind, settings=None, key="layout/test_side"):
    side_first, side_min, main_min = kind
    row = SplitRow(QWidget(), QWidget(), side_first=side_first, side_min=side_min, main_min=main_min,
                   settings=settings, key=key if settings is not None else None)
    row.show()  # скрытому виджету resizeEvent приходит только при показе
    return row


def spans(row):
    """(x, ширина) боковой колонки, ручки и главного экрана."""
    return tuple((w.x(), w.width()) for w in (row.side, row.handle, row.main))


@pytest.fixture
def settings(tmp_path):
    return QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat)


def drag(row, dx):
    """Протяжка ручки на dx px мышью (QTest)."""
    start = QPoint(row.handle.width() // 2, row.height() // 2)
    QTest.mousePress(row.handle, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    QTest.mouseMove(row.handle, start + QPoint(dx, 0))
    QTest.mouseRelease(row.handle, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start + QPoint(dx, 0))


def test_strip_sections_follow_mockup_blocks():
    """Секции полосы макета = блок экрана − 2 × 21; прорезь = зазор экранов + 2 × 21."""
    assert theme.STRIP_INSET == 21
    assert section_width(theme.POOL_W) == theme.STRIP_LEFT_W == 218
    assert section_width(theme.SCENE_W) == theme.STRIP_RIGHT_W == 522
    assert section_width(theme.CONVERT_INPUT_W) == theme.CONVERT_LEFT_W == 514
    assert section_width(theme.CONVERT_RIGHT_W) == theme.CONVERT_OUTPUT_W == 226
    assert theme.SCREEN_GAP + 2 * theme.STRIP_INSET == theme.STRIP_SEP_W == 54


@pytest.mark.parametrize("kind", [LEFT, RIGHT])
def test_mockup_width_is_the_minimum(app, kind):
    row = make_row(kind)
    assert row.minimumSizeHint().width() == PAGE_W
    row.resize(PAGE_W, H)
    assert row.side_width() == kind[1]
    assert row.main.width() == kind[2]
    assert row.handle.width() == theme.SCREEN_GAP and row.handle.height() == H


def test_side_left_geometry_at_900_and_1600(app):
    row = make_row(LEFT)
    row.resize(PAGE_W, H)
    assert spans(row) == ((0, 260), (260, 12), (272, 564))
    row.resize(WIDE_W, H)
    assert spans(row) == ((0, 260), (260, 12), (272, WIDE_W - 272))  # лишнее — главному экрану


def test_side_right_geometry_at_900_and_1600(app):
    row = make_row(RIGHT)
    row.resize(PAGE_W, H)
    assert spans(row) == ((568, 268), (556, 12), (0, 556))
    row.resize(WIDE_W, H)
    assert spans(row) == ((WIDE_W - 268, 268), (WIDE_W - 280, 12), (0, WIDE_W - 280))


def test_handle_shows_split_cursor_and_paints_nothing(app):
    row = make_row(LEFT)
    assert row.handle.cursor().shape() == Qt.CursorShape.SplitHCursor
    assert not row.handle.autoFillBackground()


@pytest.mark.parametrize(("kind", "dx", "expected"), [(LEFT, 100, 360), (LEFT, -100, 260),
                                                      (RIGHT, -100, 368), (RIGHT, 100, 268)])
def test_drag_moves_gap_within_limits(app, kind, dx, expected):
    """Ручка идёт за мышью: у колонки слева вправо — шире, у колонки справа — влево; меньше макета нельзя."""
    row = make_row(kind)
    row.resize(WIDE_W, H)
    drag(row, dx)
    assert row.side_width() == expected
    assert row.main.width() == WIDE_W - theme.SCREEN_GAP - expected


@pytest.mark.parametrize("kind", [LEFT, RIGHT])
def test_drag_stops_at_main_minimum(app, kind):
    row = make_row(kind)
    row.resize(WIDE_W, H)
    drag(row, 5000 if kind[0] else -5000)
    assert row.main.width() == kind[2]
    assert row.side_width() == WIDE_W - theme.SCREEN_GAP - kind[2]


def test_layout_changed_on_resize_and_drag(app):
    row = make_row(LEFT)
    seen = []
    row.layout_changed.connect(lambda: seen.append(row.side_width()))
    row.resize(WIDE_W, H)
    drag(row, 40)
    assert seen[-1] == 300 and len(seen) >= 2


def test_narrow_window_squeezes_but_keeps_saved_width(app):
    """Узкое окно ужимает колонку, но выбранная ширина хранится отдельно: окно снова шире — колонка прежняя."""
    row = make_row(LEFT)
    row.resize(WIDE_W, H)
    drag(row, 400)
    assert row.side_width() == row.saved == 660
    row.resize(1000, H)
    assert row.side_width() == 1000 - 12 - 564 and row.saved == 660
    row.resize(WIDE_W, H)
    assert row.side_width() == 660


def test_width_saved_on_release_and_restored_clamped(app, settings):
    row = make_row(RIGHT, settings)
    row.resize(WIDE_W, H)
    drag(row, -200)
    assert settings.value("layout/test_side", type=int) == 468
    again = make_row(RIGHT, settings)
    again.resize(PAGE_W, H)
    assert again.side_width() == 268 and again.saved == 468  # в узком окне — ужата, выбор не потерян
    again.resize(WIDE_W, H)
    assert again.side_width() == 468


def test_saved_width_below_minimum_is_ignored(app, settings):
    settings.setValue("layout/test_side", 100)
    row = make_row(LEFT, settings)
    row.resize(WIDE_W, H)
    assert row.side_width() == theme.POOL_W


def test_double_click_resets_to_layout_width(app, settings):
    row = make_row(LEFT, settings)
    row.resize(WIDE_W, H)
    drag(row, 300)
    assert row.side_width() == 560
    QTest.mouseDClick(row.handle, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                      QPoint(6, H // 2))
    assert row.side_width() == row.saved == theme.POOL_W
    assert settings.value("layout/test_side", type=int) == theme.POOL_W
