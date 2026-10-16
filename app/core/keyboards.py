"""Dispositions des claviers virtuels (AZERTY, minuscules : une adresse mail n'a pas besoin de majuscules)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Key:
    label: str
    text: str = ""        # texte inséré (par défaut : le libellé)
    action: str = ""      # "backspace" ou "clear" (touches sans texte)
    weight: int = 2       # largeur relative

    @property
    def insert_text(self) -> str:
        return "" if self.action else (self.text or self.label)


def _letters(chars: str) -> list[Key]:
    return [Key(c) for c in chars]


BACKSPACE = Key("⌫", action="backspace", weight=3)
CLEAR = Key("Effacer", action="clear", weight=3)

EMAIL_ROWS: list[list[Key]] = [
    _letters("1234567890"),
    _letters("azertyuiop"),
    _letters("qsdfghjklm"),
    _letters("wxcvbn") + [Key("."), Key("-"), Key("_"), Key("@")],
    [Key(".com", weight=3), Key(".fr", weight=3), Key("@gmail.com", weight=5), Key("@orange.fr", weight=5), BACKSPACE, CLEAR],
]

SEARCH_ROWS: list[list[Key]] = [
    _letters("azertyuiop"),
    _letters("qsdfghjklm"),
    _letters("wxcvbn") + [BACKSPACE],
    [Key("Espace", text=" ", weight=8), CLEAR],
]
