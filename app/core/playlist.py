"""Ordre de défilement du diaporama (logique pure, sans Qt).

- chronologique : la boucle suit l'ordre de prise de vue ;
- aleatoire     : chaque photo passe une fois par tour, dans le désordre, sans jamais se répéter d'un tour à l'autre.
Dans les deux cas, une photo qui vient d'arriver passe en premier (l'invité voit la sienne tout de suite),
puis elle rejoint la boucle normale.
"""
from __future__ import annotations

import random
from collections import deque
from pathlib import Path
from typing import Callable, Iterable


class Playlist:
    def __init__(self, order: str = "chronologique", rng: random.Random | None = None,
                 exists: Callable[[Path], bool] | None = None) -> None:
        self.order = order
        self._rng = rng or random.Random()
        self._exists = exists or (lambda path: path.is_file())
        self._items: list[Path] = []
        self._pos = -1
        self._deck: list[Path] = []
        self._priority: deque[Path] = deque()
        self._last: Path | None = None

    def __len__(self) -> int:
        return len(self._items)

    def __contains__(self, path: Path) -> bool:
        return path in self._items

    def load(self, paths: Iterable[Path]) -> None:
        self.clear()
        for path in paths:
            if path not in self._items:
                self._items.append(path)

    def clear(self) -> None:
        self._items, self._deck, self._pos, self._last = [], [], -1, None
        self._priority.clear()

    def set_order(self, order: str) -> None:
        if order != self.order:
            self.order, self._deck = order, []

    def add(self, path: Path) -> bool:
        """Nouvelle photo : elle passera en premier. Renvoie False si elle était déjà connue."""
        if path in self._items:
            return False
        self._items.append(path)
        self._priority.append(path)
        return True

    def remove(self, path: Path) -> None:
        if path in self._items:
            index = self._items.index(path)
            del self._items[index]
            if index <= self._pos:
                self._pos -= 1
        self._deck = [p for p in self._deck if p != path]
        self._priority = deque(p for p in self._priority if p != path)
        if self._last == path:
            self._last = None

    def next(self) -> Path | None:
        """Prochaine photo à afficher (celles qui ont disparu du disque sont écartées), None s'il n'y en a aucune."""
        while self._priority:
            path = self._priority.popleft()
            if self._exists(path):
                self._last = path
                return path
            self.remove(path)
        return self._next_random() if self.order == "aleatoire" else self._next_chronological()

    def _next_chronological(self) -> Path | None:
        for _ in range(len(self._items)):
            if not self._items:
                break
            self._pos = (self._pos + 1) % len(self._items)
            path = self._items[self._pos]
            if self._exists(path):
                self._last = path
                return path
            self.remove(path)                # retire la photo disparue : la suivante prend sa place
        return None

    def _next_random(self) -> Path | None:
        while True:
            if not self._deck:
                if not self._items:
                    return None
                self._deck = self._items[:]
                self._rng.shuffle(self._deck)
                if len(self._deck) > 1 and self._deck[-1] == self._last:     # pop() prend la dernière : pas deux fois de suite
                    self._deck[0], self._deck[-1] = self._deck[-1], self._deck[0]
            path = self._deck.pop()
            if self._exists(path):
                self._last = path
                return path
            self.remove(path)
