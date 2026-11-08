"""Системные диалоги вкладок Maps и Profiles (QInputDialog / QMessageBox).

Страницы держат свои методы с теми же именами и зовут эти функции: тесты подменяют методы страниц.
"""
from __future__ import annotations

from PySide6.QtWidgets import QInputDialog, QLineEdit, QMessageBox, QWidget


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
