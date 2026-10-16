"""Classe de base de tous les écrans."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QWidget

if TYPE_CHECKING:
    from ...config import Config
    from ...session import Session
    from ..main_window import MainWindow


class BaseScreen(QWidget):
    """Un écran du parcours. La navigation passe toujours par `self.nav` (la fenêtre principale)."""

    # False pour les écrans où l'invité ne touche pas l'écran (décompte, envoi) :
    # le retour automatique à l'accueil y est suspendu.
    allow_inactivity_reset: bool = True

    def __init__(self, nav: "MainWindow") -> None:
        super().__init__()
        self.nav = nav

    @property
    def config(self) -> "Config":
        return self.nav.config

    @property
    def session(self) -> "Session":
        return self.nav.session

    def on_enter(self) -> None:
        """Appelé à chaque affichage de l'écran."""

    def on_leave(self) -> None:
        """Appelé quand on quitte l'écran."""
