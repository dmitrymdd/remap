"""Цвета, шрифты и таблица стилей Qt. Тема одна: тёмный металлический корпус и зелёные «экраны».

Токены — константы модуля, сгруппированные по областям; цвета — строки `#RRGGBB`, полупрозрачные — кортежи
`(r, g, b, alpha)` с `qss_rgba()` / `qcolor()` для QSS и рисования. Шрифты лежат в `assets/fonts` и
регистрируются `load_fonts()`.
"""

import logging
from importlib import resources
from pathlib import Path

from PySide6.QtGui import QColor, QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

log = logging.getLogger(__name__)

RGBA = tuple[int, int, int, float]

# --- Корпус ---
BODY_TOP, BODY_MID, BODY_BOTTOM = "#1E2023", "#191B1D", "#141618"  # вертикальный градиент: 0 %, BODY_MID_AT, 100 %
BODY_MID_AT = 0.45
# Виньетка: эллипс rx×ry (доли ширины/высоты) с центром (cx, cy); прозрачна до BODY_VIGNETTE_FROM, затем до alpha
BODY_VIGNETTE = {"rx": 1.30, "ry": 1.10, "cx": 0.5, "cy": 0.4, "from": 0.55, "alpha": 0.38}
# Верхний свет: эллипс 85 %×55 % с центром на верхней кромке; белый alpha → прозрачный к BODY_TOPLIGHT_TO
BODY_TOPLIGHT = {"rx": 0.85, "ry": 0.55, "cx": 0.5, "cy": 0.0, "to": 0.70, "alpha": 0.055}
# Линии по краю корпуса (inset-тени макета): верхняя светлая, рамка 1 px, нижняя тёмная
BODY_EDGE_LIGHT: RGBA = (255, 255, 255, 0.12)
BODY_EDGE_FRAME = "#0A0B0C"
BODY_EDGE_DARK: RGBA = (0, 0, 0, 0.6)
# Утопленный блок (под экраны)
RECESS_TOP, RECESS_BOTTOM, RECESS_RADIUS = "#070808", "#0D0E10", 12

# --- Клавиши: лицо — рамка 1 px, градиент, две inset-линии, внешняя тень; поверх — текстура ---
KEY_TOP, KEY_BOTTOM, KEY_BORDER, KEY_RADIUS = "#282B2F", "#1C1E21", "#08090A", 7
KEY_LABEL = "#C3C9CE"
KEY_LABEL_HOVER = "#E6EAED"  # наведение; в макете не задано
KEY_SWAP_ICON = "#F4F6F7"  # стрелки «⇄» не меняют цвет с состоянием клавиши
KEY_INSET_LIGHT: RGBA = (255, 255, 255, 0.11)  # inset 0 1px 0
KEY_INSET_DARK: RGBA = (0, 0, 0, 0.4)  # inset 0 -1px 0
KEY_SHADOW = {"dy": 2, "blur": 4, "alpha": 0.6}  # outer 0 2px 4px rgba(0,0,0,.6)
KEY_PRESSED_TOP, KEY_PRESSED_BOTTOM = "#131517", "#1A1C1F"  # нажата и включена — один вид
KEY_PRESSED_SHADOW = {"dy": 2, "blur": 4, "alpha": 0.8}  # inset 0 2px 4px rgba(0,0,0,.8)
KEY_PRESSED_EDGE: RGBA = (255, 255, 255, 0.06)  # outer 0 1px 0: светлая линия под нажатой
KEY_HOVER_TOP, KEY_HOVER_BOTTOM = "#30343A", "#22252A"  # наведение; в макете не задано
KEY_FOCUS_RING, KEY_FOCUS_GAP = "#8FC7A3", 1  # контур 1 px (как у кнопки логотипа), зазор от лица: поля клавиши малы
# Большая клавиша CONVERT: другой градиент и тени
KEY_GO_TOP, KEY_GO_BOTTOM, KEY_GO_RADIUS = "#2A2D31", "#1C1E21", 10
KEY_GO_INSET_LIGHT: RGBA = (255, 255, 255, 0.13)  # inset 0 1px 0
KEY_GO_INSET_DARK: RGBA = (0, 0, 0, 0.45)  # inset 0 -2px 0
KEY_GO_SHADOW = {"dy": 3, "blur": 6, "alpha": 0.65}  # outer 0 3px 6px rgba(0,0,0,.65)
# Размеры лица клавиш (с рамкой), px; None — по тексту и полям
KEY_TAB_SIZE, KEY_HELP_SIZE, KEY_SQUARE_SIZE = (118, 36), (36, 36), (38, 38)
KEY_SWAP_SIZE, KEY_MAP_SIZE, KEY_CLOSE_SIZE, KEY_GO_SIZE = (44, 38), (48, 38), (34, 34), (268, 68)
KEY_TUT_HEIGHT, KEY_TUT_PAD = 36, 16
# Подпись клавиш: Barlow Condensed, px / межбуквенный интервал в em / зазор значок–подпись / поле по бокам
KEY_TAB_FONT, KEY_TAB_SPACING, KEY_TAB_GAP, KEY_TAB_PAD = 13.5, 0.12, 8, 13
KEY_HELP_FONT = 18
KEY_TUT_FONT, KEY_TUT_SPACING = 14, 0.14
KEY_GO_FONT, KEY_GO_SPACING, KEY_GO_GAP = 20, 0.22, 14

# --- Винты и шелкография ---
SCREW_LIGHT, SCREW_MID, SCREW_DARK, SCREW_RIM = "#8A9096", "#3A3E43", "#16181A", "#08090A"
SCREW_HIGHLIGHT: RGBA = (255, 255, 255, 0.08)  # мягкий блик под ободом
SCREW_SLOT = "#0A0B0C"
SCREW_SLOT_LIGHT: RGBA = (255, 255, 255, 0.12)  # светлая копия шлица, сдвинутая на (+0.6, +0.6)
SILK_TEXT = "#9AA1A8"
SILK_FAINT = "#6B7278"  # приглушённая шелкография (недоступное, подсказки); в макете не задано
KEY_LABEL_DISABLED = SILK_FAINT  # недоступная клавиша; в макете не задано

# --- Экран (зелёное стекло) ---
SCREEN_GLASS_INNER, SCREEN_GLASS_MID, SCREEN_GLASS_OUTER = "#132A1F", "#0D1C15", "#0A1711"  # радиальный
SCREEN_BORDER, SCREEN_RADIUS = "#21412F", 7
SCREEN_GRID: RGBA = (127, 181, 150, 0.13)  # крест сетки (#7FB596), шаг SCREEN_GRID_STEP
SCREEN_GRID_STEP = 32
SCREEN_GLOW = {"rx": 1.2, "ry": 0.70, "cx": 0.5, "cy": 0.0}  # radial-gradient(ellipse 120% 70% at 50% 0%); About — ry 0.80
SCREEN_GLOW_MID_AT = 0.6  # стоп SCREEN_GLASS_MID
SCREEN_SHADOW = {"dy": 0, "blur": 18, "alpha": 0.55}  # inset 0 0 18px rgba(0,0,0,.55)
SCREEN_PAD = 14  # поля содержимого экрана (в гутер справа ложится полоса прокрутки)
# Полоса прокрутки на экране: 3 px, в 5 px от внутреннего правого края; ниже — наведение (в макете не задано)
SCROLL_WIDTH, SCROLL_RIGHT, SCROLL_RADIUS, SCROLL_HIT, SCROLL_MIN_HANDLE = 3, 5, 2, 3, 20
SCROLL_TRACK: RGBA = (110, 190, 140, 0.1)
SCROLL_HANDLE, SCROLL_HANDLE_HOVER = "#3A6B4F", "#4C8A66"
CHIP_BORDER, CHIP_RADIUS = "#477A5C", 5
CHIP_BG: RGBA = (110, 190, 140, 0.07)
SCREEN_TEXT, SCREEN_TEXT_2, SCREEN_TEXT_3 = "#E6F2EA", "#8FC7A3", "#74A487"
SCREEN_DIVIDER = "#21412F"
SCREEN_BTN_BORDER, SCREEN_BTN_TEXT = "#2A4C38", "#CBE3D3"  # вторичная кнопка на экране

# --- Акцент, выбор, кабель ---
ACCENT = "#62D69A"
ACCENT_HOVER = "#86E3B3"  # наведение; в макете не задано
SELECTED = "#FFFFFF"
CABLE, CABLE_WIDTH, CABLE_SELECTED_WIDTH = "#82BC98", 1.5, 1.6
CABLE_PORT_RADIUS, CABLE_TANGENT = 2.6, 60  # точка кабеля; плечо Безье: горизонтальные касательные концов

# --- Статусы: светодиод, текст, рамка, фон ---
OK_LED, OK_TEXT = "#62D69A", "#8FC7A3"
WARN_LED, WARN_TEXT, WARN_BORDER, WARN_BG = "#E3D36B", "#E6DA8E", "#6F7748", (227, 211, 107, 0.06)
ERR_LED, ERR_TEXT, ERR_BORDER, ERR_BG = "#F0646E", "#F2939A", "#7C4248", (240, 100, 110, 0.07)
OK_BG: RGBA = (110, 190, 140, 0.07)
LED_SIZE, LED_GLOW_BLUR = 6, 6  # светодиод 6 px: кольцо 0 0 0 1px rgba(0,0,0,.5) и свечение 0 0 6px своим цветом
LED_RING: RGBA = (0, 0, 0, 0.5)
LED_OFF = "#24412F"  # погашен (до конвертации); в макете не задано

# --- Поля ввода: «рамка» (зелёное поле, вставленное в металл, с чёрным ободом) и плоское на экране ---
FIELD_TOP, FIELD_BOTTOM, FIELD_BORDER, FIELD_RADIUS = "#11251B", "#0D1C15", "#2A4C38", 6
FIELD_HEIGHT, FIELD_PAD_X, FIELD_GAP = 38, 10, 8  # высота лица, поля по бокам, зазор текст–стрелка
FIELD_RIM, FIELD_RIM_W = "#07080A", 3  # сплошной обод вокруг лица (box-shadow 0 0 0 3px)
FIELD_RIM_LIGHT: RGBA = (255, 255, 255, 0.09)  # светлая линия под ободом (0 1px 0 3px)
FIELD_INSET = {"dy": 1, "blur": 3, "alpha": 0.7}  # inset 0 1px 3px rgba(0,0,0,.7)
FIELD_CAPTION, FIELD_TEXT, FIELD_PLACEHOLDER = "#7DB394", SCREEN_TEXT, SCREEN_TEXT_3
FIELD_HOVER_BORDER = "#477A5C"  # наведение; в макете не задано
FIELD_FOCUS_BORDER = ACCENT  # фокус и открытый список; в макете не задано
FIELD_FOCUS_GLOW: RGBA = (98, 214, 154, 0.25)  # inset 0 0 0 1px
FIELD_DISABLED_OPACITY = 0.45
# Подписи двухстрочного поля и значения: px, вес, интервал (в em); зазор между строками 1 px
FIELD_CAPTION_FONT, FIELD_CAPTION_SPACING = 8.5, 0.16
FIELD_VALUE_FONT = 12  # одна строка; у двухстрочного поля — FIELD_VALUE2_FONT / вес Medium
FIELD_VALUE2_FONT = 12.5
# Плоское поле на экране (поиск на Maps)
FIELD_SCREEN_BG: RGBA = (0, 0, 0, 0.28)
FIELD_SCREEN_HEIGHT = 34
FIELD_SCREEN_INSET = {"dy": 1, "blur": 3, "alpha": 0.6}
# Флажок на экране: 15 px, рамка, подпись Martian 10/600/.1em
CHECK_SIZE, CHECK_RADIUS, CHECK_GAP, CHECK_PAD = 15, 3, 8, 2  # CHECK_PAD — запас вокруг квадрата под кольцо фокуса
CHECK_BORDER, CHECK_HOVER_BORDER = "#477A5C", "#8FC7A3"
CHECK_TEXT = SCREEN_BTN_TEXT
CHECK_FONT, CHECK_SPACING = 10, 0.1
# Список комбо: стеклянный, строки 28 px, не больше POPUP_MAX_ROWS строк (дальше — полоса прокрутки)
POPUP_ROW, POPUP_PAD, POPUP_PAD_X, POPUP_MAX_ROWS = 28, 4, 6, 10  # текст строки встаёт на 11 px, как в поле
POPUP_TEXT = "#E0EDE5"
POPUP_HOVER_BG: RGBA = (110, 190, 140, 0.12)
POPUP_HOVER_BORDER = "#5E9B7A"
# Скруглённый прозрачный список (рамка и фон контейнера Qt снимаются). False — запасной квадратный и непрозрачный
POPUP_ROUNDED = True

# --- Плашки: строки пула и сцены, заголовки групп, бейдж «+N», строки нот и карт (ui/plates.py) ---
PLATE_RADIUS, PLATE_PAD_X, PLATE_GAP, PLATE_NUM_W = 5, 10, 10, 28  # номер — столбец 28 px, по правому краю
# содержимое заголовка группы Profiles (значок, метка, число) — с полем плашки: рамка наведения/drop не задевает значок;
# в макете поле 2 px (пул) и 0 (сцена), но рамки наведения там нет
HEADER_INSET = PLATE_PAD_X
PLATE_NUM, PLATE_NAME = SCREEN_TEXT_2, POPUP_TEXT  # обычная плашка: фон CHIP_BG, рамка CHIP_BORDER
PLATE_NUM_FONT, PLATE_NAME_FONT = 11.5, 12
PLATE_SELECTED_BG: RGBA = (255, 255, 255, 0.09)  # выбрана: рамка, номер и имя белые
PLATE_DELETED_BORDER, PLATE_DELETED_NUM, PLATE_DELETED_NAME = "#21412F", "#587D67", "#688C76"  # зачёркнутая в пуле
PLATE_HOVER_BG, PLATE_HOVER_BORDER = POPUP_HOVER_BG, POPUP_HOVER_BORDER  # наведение; в макете не задано
PLATE_SUGGESTED_OPACITY = 0.7  # подсказка: обычная плашка с пунктирной рамкой
HEADER_FONT, HEADER_SPACING, HEADER_COUNT_FONT = 11, 0.12, 10.5  # заголовок группы: метка акцентом, число приглушено
BADGE_HEIGHT, BADGE_RADIUS, BADGE_FONT, BADGE_PAD = 17, 3, 10, 5  # «+N»
NOTE_ROW_H, NOTE_NUM_COL, NOTE_NUM_PAD = 28, 64, 18  # строка ноты Maps: столбец номера 64 px, правый отступ 18
NOTE_ROW_LINE: RGBA = (110, 190, 140, 0.08)  # линия под строкой
NOTE_EDIT_BG: RGBA = (255, 255, 255, 0.07)  # строка в правке: заливка и белая рамка 1 px внутри
NOTE_EDIT_FIELD, NOTE_EDIT_RADIUS = "#07120C", 3  # поле имени в правке (рамка — CHIP_BORDER)
NOTE_EDIT_H, NOTE_EDIT_MIN_W = 22, 180  # поле имени: высота и наименьшая ширина
NOTE_GROUP_H = 30  # заголовок группы в таблице нот (линия снизу, метка от левого края +4)
NOTE_GROUP_INSET = 4
NOTES_TOOLS_GAP = 14  # поиск — «NAMED ONLY»
NOTES_HEAD_TOP, NOTES_HEAD_H = 10, 28  # строка NOTE / NAME: отступ сверху и высота (+1 px линии снизу)
NOTES_HEAD_FONT, NOTES_HEAD_SPACING = 10, 0.14  # Martian 10/600, цвет FIELD_CAPTION
NOTES_TOTALS_H, NOTES_TOTALS_FONT, NOTES_TOTALS_SPACING = 26, 10, 0.08  # строка итогов (+1 px линии сверху)
NOTES_TRACK_TOP, NOTES_TRACK_BOTTOM = 86, 60  # дорожка полосы прокрутки от внутренних краёв экрана (макет: 86 и 470 px)
MAP_ENTRY_H, MAP_NAME_FONT, MAP_SUB_FONT, MAP_ENTRY_GAP = 46, 12, 9.5, 2  # запись в списке карт: имя 12/500 и строка источника
MAP_SUB_SELECTED = "#D8E6DD"  # подпись выбранной записи (обычная — SCREEN_TEXT_3)

# --- Подсказка: у Qt она квадратная, с системной тенью (скругление и тень макета в QSS недоступны) ---
TOOLTIP_BG, TOOLTIP_BORDER, TOOLTIP_TEXT = "#0B0C0E", "#3A3F44", "#D5DADF"
TOOLTIP_PX = 10
# Поля задаём в QSS половинными: Qt считает padding и рамку дважды (рамка виджета + `margin` метки QTipLabel =
# 1 + padding + рамка) и ещё 1 px своего отступа, так что от края до текста выходит 2·(padding + 1) + 2 — по вертикали
# 10, по горизонтали 12 px (в макете плашка: рамка 1 + поле 8 / 10 = 9 / 11).
TOOLTIP_PAD_Y, TOOLTIP_PAD_X = 3, 4
TOOLTIP_MAX_WIDTH = 290  # QSS не умеет ограничивать ширину подсказки: переносы — на стороне текста (`tips.tip()`)
TOOLTIP_TEXT_WIDTH = TOOLTIP_MAX_WIDTH - 2 * (2 * (TOOLTIP_PAD_X + 1) + 2)  # 266: колонка текста
TOOLTIP_LINE_HEIGHT = 150  # %

# --- Шрифты ---
MONO_FILE = "MartianMono.ttf"
LABEL_FILES = ("BarlowCondensed-Medium.ttf", "BarlowCondensed-SemiBold.ttf")
MONO_FAMILY = "Martian Mono"  # реальные имена выставляет load_fonts()
LABEL_FAMILY = "Barlow Condensed"
# Ось wdth Martian Mono (75–112.5). В макете корень — `font-stretch: 75%`, но UA-стиль `<button>`/`<input>` сбрасывает
# её в 100 %: текст внутри кнопок и полей ввода шире, текст в span/div — уже (таблица — в отчёте шага 3b)
WDTH_TEXT = 75.0
WDTH_BUTTON = 100.0
LABEL_SPACING = 0.13  # межбуквенный интервал подписей по умолчанию, в em
APP_FONT_PX = 12  # шрифт приложения по умолчанию: Martian Mono 12 px, wdth 75
PX_TO_PT = 0.75  # 96 dpi: размер в px × 0.75 = размер в pt (дробные px, например 13.5, — только так)

# --- Металл: две текстуры поверх любой металлической поверхности (файлы в assets/textures) ---
METAL_BRUSHED_FILE, METAL_BRUSHED_TILE, METAL_BRUSHED_OPACITY = "metal009_brushed_tile.png", 512, 0.02  # шлифовка
METAL_SCRATCH_FILE, METAL_SCRATCH_TILE, METAL_SCRATCH_OPACITY = "metal031_scratch_tile.png", 1024, 0.025  # царапины
# плитка — логический размер в пикселях (картинка 1024² при 512 = DPR 2, 2048² при 1024 = DPR 2)

# --- Утопленный блок: тень внутри и три внешние линии ---
RECESS_SHADOW_DY, RECESS_SHADOW_BLUR, RECESS_SHADOW_ALPHA = 2, 4, 0.95  # inset 0 2px 4px rgba(0,0,0,.95)
RECESS_EDGE_DARK: RGBA = (0, 0, 0, 0.55)  # 0 -1px 0: тёмная линия над блоком
RECESS_EDGE_LIGHT: RGBA = (255, 255, 255, 0.11)  # 0 1px 0: светлая под блоком
RECESS_EDGE_FAINT: RGBA = (255, 255, 255, 0.03)  # 0 2px 0: вторая, едва заметная
RECESS_EDGE_TOP, RECESS_EDGE_BOTTOM = 1, 2  # px, которые виджет блока резервирует над и под рамкой блока
RECESS_PAD = 6  # поля содержимого блока по умолчанию

# --- Панель внутри блока («верхняя полоса»): градиент, радиус 7, светлая линия сверху ---
PANEL_TOP, PANEL_BOTTOM, PANEL_RADIUS = "#1C1E21", "#17191B", 7
PANEL_EDGE_LIGHT: RGBA = (255, 255, 255, 0.06)

# --- Раскладка окна (макет 900×800): шапка, полоса профиля, экраны, нижняя полоса ---
WINDOW_SIZE = (900, 800)
HEADER_H, HEADER_PAD_X, HEADER_GAP = 64, 40, 14  # шапка: высота, поля, зазор между логотипом, разделителем и надписью
LOGO_SIZE = (144, 22)  # место под логотип (сам логотип позже)
BRAND_DIVIDER_H, BRAND_DIVIDER, BRAND_DIVIDER_SHADOW = 28, "#34383C", (0, 0, 0, 0.5)
BRAND_FONT, BRAND_SPACING, BRAND_LINE = 11.5, 0.14, 1.2  # шелкография «DRUM MIDI / NOTE REMAPPER»
PAGE_MARGIN = 32  # поля страницы слева и справа
STRIP_W, STRIP_H = 836, 64  # полоса профиля: размер лица утопленного блока
STRIP_GAP = 9  # от нижнего края виджета полосы до верхнего края виджета экранов (лица: 12 px)
POOL_W, SCENE_W, SCREEN_GAP = 260, 564, 12  # блоки экранов и зазор между ними
COL_FROM, COL_GAP, COL_TO = 200, 122, 200  # колонки сцены
BAND_H = 30  # нижняя полоса под экранами (между винтами)
BAND_ITEM_H, BAND_ITEM_TOP = 22, 1  # панель подсказок и статус: на линии центров нижних винтов
STRIP_PAD_X = 15  # поля панели в полосе
STRIP_LEFT_W, STRIP_SEP_W, STRIP_RIGHT_W = 218, 54, 522
STRIP_GAP_KEYS = 8
# полоса Convert (лица): профиль | прорезь | SOURCE ⇄ TARGET в левой части 514 | прорезь 54 | OUTPUT
CONVERT_LEFT_W, CONVERT_PROFILE_W, CONVERT_MAP_W, CONVERT_OUTPUT_W = 514, 148, 146, 226
CONVERT_PROFILE_FONT = 13  # однострочное комбо профиля, вес Medium (у Profiles — 12/400)
CONVERT_INPUT_W, CONVERT_RIGHT_W = 556, 268  # блок INPUT и правая колонка (OUTPUT, CONVERT); зазор — SCREEN_GAP
INPUT_HEAD_H, INPUT_HEAD_BELOW = 30, 6  # заголовок экрана: высота с линией, padding-bottom
INPUT_GAP, DROP_TOP_EXTRA = 8, 4  # gap колонки экрана; у зоны drop ещё margin-top 4
INPUT_COUNT_FONT = 10.5  # «3 FILES»
FILE_ROW_H, FILE_ROW_PAD_L, FILE_ROW_PAD_R, FILE_ROW_LINE_GAP = 60, 12, 10, 6
FILE_ROW_GAP_X = 10  # зазор между значком, именем и кнопкой; во второй строке — между LED, текстом и DETAILS
FILE_ROW_INDENT = 24  # вторая строка: padding-left (LED — на 14 px левее, margin-right −2)
FILE_NAME_FONT, FILE_RESULT_FONT = 12.5, 10.5
FILE_REMOVE_SIZE, FILE_REMOVE_RADIUS = 22, 4
FILE_DETAILS_H, FILE_DETAILS_PAD, FILE_DETAILS_RADIUS = 20, 7, 3
FILE_BTN_FONT, FILE_BTN_SPACING = 9, 0.04
DROP_BORDER, DROP_RADIUS, DROP_GAP = "#3A6B4F", 6, 10
DROP_BG: RGBA = (0, 0, 0, 0.16)
DROP_DASH = (3, 3)  # штрих и пробел рамки dashed 1 px
DROP_TITLE_FONT, DROP_TITLE_SPACING, DROP_SUB_FONT = 11, 0.08, 10
DROP_MIN_H = 120  # меньше зона drop не сжимается, дальше список прокручивается; в макете не задано
TOTALS_H, TOTALS_FONT, TOTALS_SPACING, TOTALS_GAP = 26, 10, 0.06, 14
OUT_CARD_H, OUT_CARD_PAD, OUT_CARD_GAP_X, OUT_CARD_LINE_GAP = 54, 10, 10, 3  # карточка результата
OUT_NAME_FONT, OUT_FOLDER_FONT = 12, 9.5
OUT_PLANNED_OPACITY = 0.45  # будущий результат (до конвертации) — приглушён; в макете не задано
CONVERT_GO_SLOT_H, CONVERT_GO_GAP = 68, 12  # место под CONVERT под экраном OUTPUT (лица: 688 → 700)
STRIP_SEP: RGBA = (255, 255, 255, 0.06)
STRIP_SEP_DARK = "#0A0B0C"
# колонки: плашка, шаг строк, заголовок группы, зазоры под и над заголовком (cable_layout.RowMetrics)
POOL_ROWS = (28, 32, 29, 4, 4)
SCENE_ROWS = (30, 36, 30, 12, 10)
POOL_HEAD_H = 30  # заголовок пула: высота до линии (с отступом 6 под текстом)
POOL_HEAD_FONT, POOL_HEAD_SPACING = 11, 0.08
MATCH_FONT, MATCH_SPACING, MATCH_H, MATCH_PAD = 9, 0.04, 24, 8
MATCH_BG: RGBA = (110, 190, 140, 0.06)
MATCH_RADIUS = 4

# --- Обучение (Profiles.dc.html): затемнение с вырезами, кольцо вокруг выреза, плашка шага ---
HELP_GAP = 16  # от лица «?» до лица первой вкладки
TUT_DIM: RGBA = (3, 4, 5, 0.7)  # #030405, fill-opacity .7; вырез — скруглённый прямоугольник без затемнения
TUT_RING_OUT, TUT_RING_WIDTH = 2, 1.5  # кольцо на 2 px шире выреза (радиус + 2), рамка 1.5 px акцентом внутрь
TUT_RING_SPREAD: RGBA = (98, 214, 154, 0.18)  # 0 0 0 4px — полоса 4 px вокруг кольца
TUT_RING_SPREAD_W = 4
TUT_RING_GLOW = {"dy": 0, "blur": 18, "alpha": 0.35, "rgb": (98, 214, 154)}  # 0 0 18px rgba(98,214,154,.35)
TUT_PLATE_W, TUT_PLATE_RADIUS = 320, 12  # ширина с рамкой (box-sizing: border-box)
TUT_PLATE_PAD_X, TUT_PLATE_PAD_TOP, TUT_PLATE_PAD_BOTTOM = 18, 16, 18  # padding 16px 18px 18px
TUT_PLATE_GAP, TUT_PLATE_ROW_TOP, TUT_PLATE_KEY_GAP = 10, 4, 8  # между строками; над клавишами; между клавишами
TUT_PLATE_STOPS = ((0.0, "#24272B"), (0.55, "#1B1D20"), (1.0, "#17191B"))
TUT_PLATE_INSET_LIGHT: RGBA = (255, 255, 255, 0.14)  # inset 0 1px 0
TUT_PLATE_INSET_DARK: RGBA = (0, 0, 0, 0.6)  # inset 0 -1px 0
TUT_PLATE_SHADOW = {"dy": 18, "blur": 44, "alpha": 0.75}  # 0 18px 44px rgba(0,0,0,.75)
TUT_PLATE_MARGIN = 8  # плашка не ближе к краю окна; в макете не задано
TUT_PLATE_FLIP_GAP = 24  # плашка не помещается под вырезом — над ним с тем же зазором (под вырезом в макете 24)
TUT_COUNTER_FONT, TUT_COUNTER_SPACING = 13, 0.18  # «STEP 4 / 8», цвет SILK_TEXT
TUT_TITLE_FONT, TUT_TITLE_SPACING, TUT_TITLE = 22, 0.08, "#EDF0F2"
TUT_TEXT_FONT, TUT_TEXT_LINE, TUT_TEXT = 16, 1.35, KEY_LABEL  # Barlow 500, line-height 1.35
TUT_SKIP_FONT, TUT_SKIP_SPACING, TUT_SKIP = 13, 0.14, "#8C949B"
TUT_SKIP_UNDERLINE = 3  # text-underline-offset: 3px от базовой линии, толщина 1 px
TUT_DOT, TUT_DOT_GAP = 6, 5  # квадратные точки шагов
TUT_DOT_PAST, TUT_DOT_FUTURE = "#6B7379", "#0B0C0D"  # текущая — ACCENT
TUT_DOT_FUTURE_SHADOW = {"dy": 1, "blur": 1, "alpha": 0.8}  # inset 0 1px 1px rgba(0,0,0,.8)
TUT_DOT_GLOW = {"dy": 0, "blur": 4, "alpha": 1.0, "rgb": (98, 214, 154)}  # текущая: 0 0 4px ACCENT

# --- Винты корпуса: квадрат 14 px, левый верхний угол в 11 px от углов окна ---
SCREW_SIZE, SCREW_INSET = 14, 11

# --- Ресурсы ---
ASSETS = resources.files("remap") / "assets"
LOGO_PNG = Path(str(ASSETS / "logo.png"))  # 2170×725 RGBA, используется позже; может отсутствовать


# Временный слой: старые ключи → новая палитра, чтобы страницы работали до перестройки. Убирается в шагах 3–5.
# Направления цветом не различаем: обратное (←) рисуется как прямое.
LEGACY = {
    "bg": RECESS_BOTTOM,
    "surface": KEY_TOP,
    "border": TOOLTIP_BORDER,
    "text": SCREEN_TEXT,
    "text_muted": SILK_TEXT,
    "text_faint": SILK_FAINT,
    "accent": ACCENT,
    "accent_hover": ACCENT_HOVER,
    "on_accent": SCREEN_GLASS_OUTER,
    "selection": SCREEN_BORDER,
    "accent_muted": CHIP_BORDER,
}
TOKENS = LEGACY


def qss_rgba(c: RGBA) -> str:
    r, g, b, a = c
    return f"rgba({r}, {g}, {b}, {round(a * 100)}%)"


def qcolor(c: str | RGBA, alpha: float | None = None) -> QColor:
    """QColor из `#RRGGBB` или `(r, g, b, alpha)`; `alpha` (0–1) заменяет прозрачность."""
    if isinstance(c, str):
        out = QColor(c)
    else:
        r, g, b, a = c
        out = QColor(r, g, b)
        out.setAlphaF(a)
    if alpha is not None:
        out.setAlphaF(alpha)
    return out


_FONT_IDS: dict[str, int] = {}  # файл шрифта -> id в QFontDatabase (каждый файл регистрируется один раз)
# Растёт, когда регистрируется новый файл шрифта. Часть ключей кэшей текста и плашек: до `load_fonts()` под тем же именем
# семейства Qt подставляет запасной шрифт, и метрики и растры, посчитанные с ним, после загрузки уже неверны.
FONT_GENERATION = 0


def load_fonts() -> dict[str, str]:
    """Регистрирует шрифты из assets/fonts; возвращает {"mono": семейство, "label": семейство}.
    Нет файла — предупреждение в лог, остаётся запасное имя семейства (шрифт подменит система)."""
    global MONO_FAMILY, LABEL_FAMILY, FONT_GENERATION
    fonts = ASSETS / "fonts"
    found: dict[str, str] = {}
    for kind, files in (("mono", (MONO_FILE,)), ("label", LABEL_FILES)):
        for name in files:
            path = Path(str(fonts / name))
            fid = _FONT_IDS.get(str(path), -1)
            if fid < 0 and path.is_file():
                fid = QFontDatabase.addApplicationFont(str(path))
                if fid >= 0:
                    _FONT_IDS[str(path)] = fid
                    FONT_GENERATION += 1
            families = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
            if not families:
                log.warning("font not loaded: %s", path)
                continue
            found[kind] = families[0]
    MONO_FAMILY = found.get("mono", MONO_FAMILY)
    LABEL_FAMILY = found.get("label", LABEL_FAMILY)
    return {"mono": MONO_FAMILY, "label": LABEL_FAMILY}


def _sized(font: QFont, px: float, weight: QFont.Weight) -> QFont:
    """Размер в px (допустимы дробные: 13.5, 12.5, 8.5) через pt: `setPixelSize` принимает только целые. Без хинтинга
    и со сглаживанием — ближе к тексту браузера, по которому нарисован макет."""
    font.setPointSizeF(px * PX_TO_PT)
    font.setWeight(weight)
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    return font


def mono_font(px: float, weight: QFont.Weight = QFont.Weight.Normal, wdth: float = WDTH_TEXT) -> QFont:
    """Martian Mono; ширина — ось wdth (`WDTH_TEXT` 75 по умолчанию, `WDTH_BUTTON` 100 для текста кнопок и полей)."""
    f = _sized(QFont(MONO_FAMILY), px, weight)
    f.setVariableAxis(QFont.Tag("wdth"), wdth)
    return f


def label_font(px: float, weight: QFont.Weight = QFont.Weight.DemiBold, spacing: float = LABEL_SPACING) -> QFont:
    """Barlow Condensed, заглавные, разрядка `spacing` em (по умолчанию 0.13)."""
    f = _sized(QFont(LABEL_FAMILY), px, weight)
    f.setCapitalization(QFont.Capitalization.AllUppercase)
    f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, px * spacing)
    return f


def install_app_font() -> QFont:
    """Шрифт приложения по умолчанию — Martian Mono 12 px (wdth 75), как корень макета. Вызывается после
    `load_fonts()` и до стилей; в QSS шрифт `QWidget` не задаётся, иначе он перекроет этот."""
    font = mono_font(APP_FONT_PX)
    QApplication.setFont(font)
    return font


def stylesheet(t: dict[str, str] = TOKENS) -> str:
    mono, label = f'"{MONO_FAMILY}"', f'"{LABEL_FAMILY}"'
    body = (f"qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {BODY_TOP}, stop:{BODY_MID_AT} {BODY_MID}, "
            f"stop:1 {BODY_BOTTOM})")
    key = f"qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {KEY_TOP}, stop:1 {KEY_BOTTOM})"
    key_hover = f"qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {KEY_HOVER_TOP}, stop:1 {KEY_HOVER_BOTTOM})"
    key_down = f"qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {KEY_PRESSED_TOP}, stop:1 {KEY_PRESSED_BOTTOM})"
    return f"""
    QWidget {{ background: transparent; color: {t['text']}; }}  /* шрифт — приложения (install_app_font) */
    QMainWindow {{ background: {BODY_BOTTOM}; }}  /* металл центрального виджета рисует ui/metal.py */
    QDialog {{ background: {body}; }}
    QToolTip {{ background: {TOOLTIP_BG}; color: {TOOLTIP_TEXT}; border: 1px solid {TOOLTIP_BORDER};
                padding: {TOOLTIP_PAD_Y}px {TOOLTIP_PAD_X}px; font-family: {mono}; font-size: {TOOLTIP_PX}px; }}
    QLabel#muted {{ color: {t['text_muted']}; }}
    QPushButton {{ background: {key}; color: {KEY_LABEL}; border: 1px solid {KEY_BORDER};
                   border-radius: {KEY_RADIUS}px; padding: 7px 14px; }}
    QPushButton:hover {{ background: {key_hover}; }}
    QPushButton:pressed {{ background: {key_down}; }}
    QPushButton:disabled {{ color: {t['text_faint']}; }}
    QPushButton#primary {{ background: {t['accent']}; color: {t['on_accent']}; border: none; font-weight: 600; }}
    QPushButton#primary:hover {{ background: {t['accent_hover']}; }}
    QPushButton#primary:disabled {{ background: {key}; color: {t['text_faint']};
                                    border: 1px solid {KEY_BORDER}; font-weight: 400; }}
    QComboBox {{ background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 6px;
                 padding: 5px 24px 5px 10px; }}
    /* без font-size: шрифт в px из QSS при открытии списка даёт «QFont::setPointSize: Point size <= 0»; текст
       комбо рисует ui/combo.py */
    QComboBox:hover {{ border-color: {t['accent']}; }}
    /* стрелку рисует ui/combo.py (ComboBox): у ::drop-down своей рамки нет — иначе справа двойная граница */
    QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: center right; width: 20px;
                            border: none; background: transparent; }}
    QComboBox::down-arrow {{ image: none; width: 0; height: 0; }}
    QComboBox QAbstractItemView {{ background: {t['surface']}; border: 1px solid {t['border']};
                                   selection-background-color: {t['accent']};
                                   selection-color: {t['on_accent']}; }}
    QPlainTextEdit {{ background: {t['bg']}; border: 1px solid {t['border']}; border-radius: 8px;
                      padding: 6px; font-family: {mono}; font-size: 12px; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {t['border']}; border-radius: 3px; min-height: 24px; }}
    QScrollBar::handle:vertical:hover {{ background: {t['text_faint']}; }}
    QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{
        background: none; height: 0; }}
    QLabel#status {{ color: {t['text_muted']}; }}
    QLabel#status[state="ok"] {{ color: {OK_TEXT}; }}
    QLabel#status[state="error"] {{ color: {ERR_TEXT}; }}

    QTableWidget {{ background: {t['bg']}; border: 1px solid {t['border']}; border-radius: 8px;
                               outline: none; font-family: {mono}; font-size: 12px; }}
    QTableWidget {{ gridline-color: {t['border']}; selection-background-color: {t['selection']};
                  selection-color: {t['text']}; }}
    QHeaderView::section {{ background: {t['bg']}; color: {t['text_muted']}; border: none;
                            border-bottom: 1px solid {t['border']}; padding: 4px 6px; font-family: {label};
                            font-size: 10pt; font-weight: 600; }}
    QTableWidget QLineEdit {{ border-radius: 0; padding: 0 4px; }}
    QLineEdit {{ background: {t['bg']}; border: 1px solid {t['border']}; border-radius: 6px;
                 padding: 5px 8px; font-family: {mono}; font-size: 12px; selection-background-color: {t['accent']};
                 selection-color: {t['on_accent']}; }}
    QLineEdit:focus {{ border-color: {t['accent']}; }}
    QMenu {{ background: {t['surface']}; border: 1px solid {t['border']}; padding: 4px; }}
    QMenu::item {{ padding: 6px 18px; border-radius: 4px; }}
    QMenu::item:selected {{ background: {t['accent']}; color: {t['on_accent']}; }}
    QCheckBox::indicator, QTableWidget::indicator {{ width: 14px; height: 14px; border: 1px solid {t['text_faint']};
                                                   border-radius: 3px; background: {t['bg']}; }}
    QCheckBox::indicator:checked, QTableWidget::indicator:checked {{ background: {t['accent']};
                                                                   border-color: {t['accent']}; }}
    QCheckBox::indicator:hover, QTableWidget::indicator:hover {{ border-color: {t['accent']}; }}
    QCheckBox::indicator:disabled, QTableWidget::indicator:disabled {{ border-color: {t['border']};
                                                                     background: {t['surface']}; }}
    QCheckBox::indicator:checked:disabled, QTableWidget::indicator:checked:disabled {{
        background: {t['accent_muted']}; border-color: {t['accent_muted']}; }}
    QFrame#suggestBar {{ background: {t['surface']}; border: 1px dashed {t['accent_muted']}; border-radius: 6px; }}
    QFrame#suggestBar QLabel {{ background: transparent; color: {t['text_muted']}; }}
    QPushButton#link {{ background: transparent; border: none; padding: 3px 6px; color: {t['accent']};
                        font-weight: 600; }}
    QPushButton#link:hover {{ color: {t['accent_hover']}; }}
    QPushButton#link:disabled {{ color: {t['text_faint']}; }}
    """


def repolish(w, prop: str, value: str) -> None:
    """Сменить динамическое свойство виджета и применить стили, зависящие от него."""
    w.setProperty(prop, value)
    w.style().unpolish(w)
    w.style().polish(w)
