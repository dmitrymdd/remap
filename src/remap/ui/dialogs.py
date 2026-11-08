"""Системные диалоги вкладок Maps и Profiles (QInputDialog / QMessageBox).

Страницы держат свои методы с теми же именами и зовут эти функции: тесты подменяют методы страниц.
"""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QInputDialog, QLineEdit, QMessageBox, QWidget

from ..storage import id_taken


def ask_text(parent: QWidget, title: str, label: str, default: str) -> str | None:
    """Строка текста; None — отмена."""
    text, ok = QInputDialog.getText(parent, title, label, QLineEdit.EchoMode.Normal, default)
    return text if ok else None


def confirm(parent: QWidget, title: str, text: str, details: str = "") -> bool:
    """Yes / Cancel (по умолчанию Cancel); True — Yes."""
    box = QMessageBox(QMessageBox.Icon.Question, title, text,
                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, parent)
    if details:
        box.setInformativeText(details)
    box.setDefaultButton(QMessageBox.StandardButton.Cancel)
    return box.exec() == QMessageBox.StandardButton.Yes


def ask_save_changes(parent: QWidget, text: str) -> str:
    """«Unsaved changes»: Save (по умолчанию) / Discard / Cancel -> "save" / "discard" / "cancel"."""
    answer = QMessageBox.question(
        parent, "Unsaved changes", text,
        QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
        QMessageBox.StandardButton.Save)
    return {QMessageBox.StandardButton.Save: "save",
            QMessageBox.StandardButton.Discard: "discard"}.get(answer, "cancel")


def show_error(parent: QWidget, text: str) -> None:
    """Предупреждение с заголовком «REMAP»."""
    QMessageBox.warning(parent, "REMAP", text)


def ask_unique_name(ask_text: Callable[[str, str, str], str | None], show_error: Callable[[str], None],
                    kind: str, title: str, default: str, ids: list[str],
                    exclude_id: str | None = None) -> str | None:
    """Имя карты или профиля (kind — «Map» / «Profile»); ID (имя файла) не должен совпадать с одним из ids.
    None — отмена. Вопрос и ошибки — через методы страницы (тесты их подменяют)."""
    while True:
        text = ask_text(title, f"{kind} name:", default)
        if text is None:
            return None
        text = text.strip()
        if not text:
            show_error("The name cannot be empty.")
            continue
        if id_taken(text, ids, exclude_id):
            show_error(f'A {kind.lower()} named "{text}" already exists. Choose another name.')
            default = text
            continue
        return text
