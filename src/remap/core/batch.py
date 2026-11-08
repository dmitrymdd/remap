"""Пакетная конвертация нескольких файлов одним профилем (без Qt и без UI)."""
from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from .convert import ConversionReport, convert
from .errors import describe_error, path_key, technical_details
from .profile import FORWARD, RemapProfile

SUFFIX = "_remapped"


def output_path_for(src: Path, output_dir: Path | None = None) -> Path:
    """Куда пишется результат: рядом с исходником или в output_dir, имя — «<имя>_remapped.mid»."""
    return (output_dir if output_dir is not None else src.parent) / (src.stem + SUFFIX + ".mid")


@dataclass
class FileResult:
    src: Path
    dst: Path
    report: ConversionReport | None = None
    error: str | None = None    # понятный текст (describe_error)
    details: str | None = None  # технические детали: тип исключения и его текст

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass
class BatchResult:
    files: list[FileResult] = field(default_factory=list)

    @property
    def succeeded(self) -> list[FileResult]:
        return [f for f in self.files if f.ok]

    @property
    def failed(self) -> list[FileResult]:
        return [f for f in self.files if not f.ok]

    @property
    def outputs(self) -> list[Path]:
        return [f.dst for f in self.succeeded]


@dataclass(frozen=True)
class OutputConflict:
    """Результат `src` не будет записан: имя `dst` уже занял результат исходника `other` (выше в пачке) или `dst` —
    это другой исходник пачки `other` (`overwrites_source`)."""
    src: Path
    dst: Path
    other: Path
    overwrites_source: bool = False

    @property
    def message(self) -> str:
        if self.overwrites_source:
            return f"Output would overwrite another source file: {self.dst.name}"
        return f"Output name collides with the result of {self.other.name}: {self.dst.name}"


def output_conflicts(sources: Iterable[Path], output_dir: Path | None = None) -> list[OutputConflict | None]:
    """Конфликты имён внутри пачки, по порядку `sources` (None — конфликта нет). Пути сравниваются `path_key()`
    (на Windows без различия регистра). Имя занимает первый файл; файл с конфликтом имя не занимает."""
    sources = list(sources)
    source_by_key = {}
    for s in sources:
        source_by_key.setdefault(path_key(s), s)
    claimed: dict[str, Path] = {}
    out: list[OutputConflict | None] = []
    for src in sources:
        dst = output_path_for(src, output_dir)
        key = path_key(dst)
        if key in claimed:
            out.append(OutputConflict(src, dst, claimed[key]))
        elif key in source_by_key:
            out.append(OutputConflict(src, dst, source_by_key[key], overwrites_source=True))
        else:
            claimed[key] = src
            out.append(None)
    return out


def convert_batch(sources: Iterable[Path], profile: RemapProfile, direction: str = FORWARD,
                  output_dir: Path | None = None,
                  convert_fn: Callable[..., ConversionReport] = convert) -> BatchResult:
    """Конвертирует файлы по порядку; ошибка одного файла не останавливает остальные.

    Существующий файл результата перезаписывается (как при одном файле). Исключение — конфликты внутри самой
    пачки: два результата с одним именем (файлы из разных папок при общей output_dir) или результат, совпадающий
    с другим исходником пачки, — такой файл не пишется и попадает в отчёт ошибкой (первый занявший имя пишется);
    правило — `output_conflicts()`, по нему же Convert показывает конфликты до конвертации.
    """
    sources = list(sources)
    conflicts = output_conflicts(sources, output_dir)
    result = BatchResult()
    folder_error = None
    if output_dir is not None:
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            folder_error = f"Cannot create the output folder: {e}"
    for src, conflict in zip(sources, conflicts, strict=True):
        dst = output_path_for(src, output_dir)
        error = folder_error or (conflict.message if conflict is not None else None)
        if error is not None:
            result.files.append(FileResult(src, dst, error=error))
            continue
        try:
            report = convert_fn(src, dst, profile, direction=direction)
        except Exception as exc:  # noqa: BLE001 — любая ошибка файла (битый MIDI, доступ): в отчёт, пачка дальше
            result.files.append(FileResult(src, dst, error=describe_error(exc, src, dst),
                                           details=technical_details(exc)))
        else:
            result.files.append(FileResult(src, dst, report))
    return result
