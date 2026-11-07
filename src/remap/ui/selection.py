"""Выделение в списке как в Проводнике Windows, без Qt: клик — только этот элемент (и якорь), Ctrl+клик —
переключить, Shift+клик — диапазон от якоря, Ctrl+Shift+клик — добавить диапазон, Ctrl+A — всё, клик по пустому
месту — снять. Элементы — любые хешируемые ключи в порядке показа; вид спрашивает `is_selected()`."""

from __future__ import annotations

from collections.abc import Hashable, Iterable


class Selection:
    def __init__(self, items: Iterable[Hashable] = ()) -> None:
        self._items: list[Hashable] = list(items)
        self._selected: set[Hashable] = set()
        self.anchor: Hashable | None = None

    @property
    def items(self) -> list[Hashable]:
        return list(self._items)

    def set_items(self, items: Iterable[Hashable]) -> None:
        """Новый порядок элементов: выделение и якорь остаются у тех, что не исчезли."""
        self._items = list(items)
        present = set(self._items)
        self._selected &= present
        if self.anchor not in present:
            self.anchor = None

    @property
    def selected(self) -> list[Hashable]:
        """Выделенные в порядке показа."""
        return [k for k in self._items if k in self._selected]

    def is_selected(self, key: Hashable) -> bool:
        return key in self._selected

    def __len__(self) -> int:
        return len(self._selected)

    def click(self, key: Hashable) -> None:
        self._selected = {key}
        self.anchor = key

    def toggle(self, key: Hashable) -> None:
        self._selected ^= {key}
        self.anchor = key

    def _range(self, key: Hashable) -> set[Hashable]:
        a, b = self._items.index(self.anchor), self._items.index(key)
        lo, hi = min(a, b), max(a, b)
        return set(self._items[lo:hi + 1])

    def extend(self, key: Hashable, add: bool = False) -> None:
        """Shift: диапазон от якоря (якорь не двигается); `add` (Ctrl+Shift) — диапазон добавляется к выделенному.
        Якоря нет — как обычный клик (с `add` — как Ctrl+клик)."""
        if self.anchor is None:
            self.toggle(key) if add else self.click(key)
            return
        span = self._range(key)
        self._selected = self._selected | span if add else span

    def press(self, key: Hashable, ctrl: bool = False, shift: bool = False) -> None:
        """Клик мышью с модификаторами."""
        if shift:
            self.extend(key, add=ctrl)
        elif ctrl:
            self.toggle(key)
        else:
            self.click(key)

    def select_all(self) -> None:
        self._selected = set(self._items)

    def clear(self) -> None:
        self._selected = set()

    def reset(self) -> None:
        """Снять выделение и забыть якорь (другой профиль, направление, карта)."""
        self._selected = set()
        self.anchor = None

    def targets(self, key: Hashable) -> list[Hashable]:
        """На что действует кнопка элемента (× и т.п.): на всё выделенное, если элемент выделен, иначе на него один."""
        return self.selected if key in self._selected else [key]
