"""Choix de l'écran du diaporama."""
from __future__ import annotations

from typing import Sequence


def pick_second_screen(screens: Sequence, main_screen):
    """Premier écran qui n'est pas celui de la borne ; None s'il n'y en a pas (un seul écran, ou écrans dupliqués)."""
    if main_screen not in screens:               # écran de la borne inconnu : on ne devine pas, sauf s'il y en a plusieurs
        return screens[1] if len(screens) > 1 else None
    others = [screen for screen in screens if screen is not main_screen]
    return others[0] if others else None


def pick_third_screen(screens: Sequence, main_screen):
    """Deuxième écran étendu après celui de la borne (le troisième au total)."""
    if main_screen not in screens:
        return screens[2] if len(screens) > 2 else None
    others = [screen for screen in screens if screen is not main_screen]
    return others[1] if len(others) > 1 else None
