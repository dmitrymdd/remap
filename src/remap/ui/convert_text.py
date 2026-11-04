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
    """Итог одной строкой в той же терминологии, что и format_report: hits всегда, остальные части — только ненулевые
    (как в строке итогов экрана)."""
    t = report.totals()
    parts = [_plural(t.hits, "hit")]
    parts += [f"{n} {word}" for n, word in ((t.moved.hits, "moved"), (t.unchanged.hits, "unchanged"),
                                            (t.deleted.hits, "deleted")) if n]
    if report.warnings:
        parts.append(_plural(len(report.warnings), "warning"))
    return " · ".join(parts)


def result_line(res: FileResult) -> str:
    """Строка результата под именем файла: «52 hits · …» или первая строка ошибки (состояние показывает LED)."""
    if res.ok:
        return report_summary(res.report)
    error = (res.error or "").strip()
    return error.splitlines()[0] if error else "Failed"


READY, OK, WARN, ERROR = "ready", "ok", "warn", "error"
READY_LINE = "Ready"


def file_state(res: FileResult | None) -> str:
    """ready — ещё не конвертировали; error — не сконвертирован; warn — есть предупреждения отчёта; иначе ok."""
    if res is None:
        return READY
    if not res.ok:
        return ERROR
    return WARN if res.report.warnings else OK


def state_tip(res: FileResult | None) -> tuple[str, str] | None:
    """Подсказка LED и строки результата: (заголовок, текст) — что значит состояние; до конвертации — нет."""
    state = file_state(res)
    if state == READY:
        return None
    if state == ERROR:
        return "Not converted", (res.error or "Failed").strip()
    if state == WARN:
        return "Converted with warnings", "\n".join(res.report.warnings) + "\nDETAILS shows the full report."
    return "Converted", "DETAILS shows the full report."


def totals(results) -> tuple[int, int, int]:
    """(сконвертировано — вместе с предупреждениями, из них с предупреждениями, не сконвертировано)."""
    states = [file_state(r) for r in results]
    return (sum(s in (OK, WARN) for s in states), states.count(WARN), states.count(ERROR))


def totals_parts(results) -> list[tuple[str, str]]:
    """Строка итогов экрана INPUT частями (текст, состояние для цвета); нулевые предупреждения и ошибки не пишутся."""
    converted, warned, failed = totals(results)
    parts = [(f"{converted} CONVERTED", OK)]
    if warned:
        parts.append((f"{warned} WITH WARNINGS", WARN))
    if failed:
        parts.append((f"{failed} FAILED", ERROR))
    return parts


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
