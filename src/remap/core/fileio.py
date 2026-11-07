"""Атомарная запись файлов: при сбое прежний файл остаётся целым."""
from __future__ import annotations

import contextlib
import os
import tempfile
from pathlib import Path


def atomic_write_bytes(path: str | Path, data: bytes) -> None:
    """Пишет `data` во временный файл рядом с `path` (fsync), затем os.replace поверх.

    Временный файл — `.<stem>.<случайное>.tmp` в той же папке; при любой ошибке он удаляется,
    а существующий `path` не трогается. Папка должна существовать.
    """
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.stem}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
