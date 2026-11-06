"""Общие фикстуры тестов. Qt — offscreen (окна не показываются); PySide6 импортируется только в фикстуре app,
чтобы тесты ядра шли и без него."""
import os

import pytest

from remap.storage import Storage

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("REMAP_NO_TUTORIAL", "1")  # обучение при первом заходе на Profiles закрыло бы страницу в тестах


@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app
    # платформа offscreen падает (segfault) при выходе, если в буфере обмена остались данные
    # (test_load_convert_and_copy кладёт туда файл); обычная платформа windows — нет
    app.clipboard().clear()


@pytest.fixture
def storage(tmp_path):
    return Storage(tmp_path / "store")


@pytest.fixture(autouse=True)
def _delete_closed_windows():
    """После теста закрывает и удаляет окна верхнего уровня: без цикла событий deleteLater() не срабатывает,
    окна копятся, и каждый следующий тест UI идёт медленнее. Qt не импортируется, если тест его не загрузил."""
    yield
    import sys
    if "PySide6.QtWidgets" not in sys.modules:
        return
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication
    if QApplication.instance() is None:
        return
    for widget in QApplication.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QCoreApplication.processEvents()
