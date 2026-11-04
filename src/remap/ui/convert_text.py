"""Тексты экрана Convert без Qt: отбор MIDI-файлов, строка результата файла, полный отчёт, итог пакета."""
from __future__ import annotations

from pathlib import Path

from ..core import ConversionReport, FileResult

MIDI_EXTS = {".mid", ".midi"}


def is_midi(path: str | Path | None) -> bool:
    return bool(path) and Path(path).suffix.lower() in MIDI_EXTS and Path(path).is_file()


def expand_midi_paths(paths: list[Path]) -> list[Path]:
    """Файлы .mid/.midi из списка; папка заменяется своими .mid/.midi верхнего уровня (без рекурсии), по имени."""
    files: list[Path] = []
    for p in paths:
        if p.is_dir():
            try:
                files.extend(sorted((c for c in p.iterdir() if is_midi(c)), key=lambda c: c.name.casefold()))
            except OSError:
                continue
        elif is_midi(p):
            files.append(p)
    return files


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def _counts(hits: int, notes: int) -> str:
    return f"{_plural(hits, 'hit')} ({_plural(notes, 'note')})"


def format_report(report: ConversionReport) -> str:
    """Полный текст отчёта. hits — note_on, notes — различные номера нот; категории: moved (номер изменился),
    unchanged (тот же номер — по правилу или без правила), deleted."""
    t = report.totals()
    lines = [f"Total: {_counts(t.hits, t.notes)}",
             f"  Moved: {_counts(t.moved.hits, t.moved.notes)}",
             f"  Unchanged: {_counts(t.unchanged.hits, t.unchanged.notes)}",
             f"  Deleted: {_counts(t.deleted.hits, t.deleted.notes)}"]
    if report.unresolved_kept:
        lines.append("  no rule in the profile, unchanged: " + ", ".join(map(str, report.unresolved_kept)))
    lines.append(f"Merged duplicates (many-to-one, same tick): {_plural(report.merged, 'hit')}, "
                 f"{report.merged_note_offs} note_off")
    lines.append(f"Overlaps of one target note on different ticks: {report.overlaps}")
    if report.orphan_note_offs:
        lines.append(f"note_off without note_on (kept): {report.orphan_note_offs}")
    if report.warnings:
        lines.append("")
        lines.append("Warnings:")
        lines.extend(f"  ⚠ {w}" for w in report.warnings)
    if report.notes:
        lines.append("")
        lines.append("Per note (source → result, hits):")
        for r in report.notes.values():
            target = "deleted" if r.action == "delete" else f"→ {r.dst}"
            origin = "" if r.origin == "profile" else f"  [{r.origin}]"
            lines.append(f"  {r.src:>3} {target:<8} ×{r.count}{origin}")
    return "\n".join(lines)


def report_summary(report: ConversionReport) -> str:
    """Итог одной строкой в той же терминологии, что и format_report; предупреждения — только если есть."""
    t = report.totals()
    w = len(report.warnings)
    text = f"{_plural(t.hits, 'hit')} · {t.moved.hits} moved · {t.unchanged.hits} unchanged · {t.deleted.hits} deleted"
    return text + (f" · {_plural(w, 'warning')}" if w else "")


def result_line(res: FileResult) -> str:
    """Строка результата под именем файла: «✓ 52 hits · …» или «✗ <первая строка ошибки>»."""
    if res.ok:
        return f"✓ {report_summary(res.report)}"
    error = (res.error or "").strip()
    return f"✗ {error.splitlines()[0] if error else 'Failed'}"


def result_details(res: FileResult, head: str = "") -> str:
    """Полный текст для окна Details: отчёт (с заголовком «Profile: …») или ошибка + технические детали."""
    if res.ok:
        return head + format_report(res.report)
    text = (res.error or "Failed").strip()
    return f"{text}\n\nTechnical details:\n{res.details}" if res.details else text


def batch_summary(ok: int, failed: int) -> str:
    """«3 files converted, 1 failed»."""
    text = f"{_plural(ok, 'file')} converted"
    return text + (f", {failed} failed" if failed else "")
