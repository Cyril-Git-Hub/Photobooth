"""Diaporama de la soirée sur le second écran : choix de l'écran, rythme, arrivée des nouvelles photos."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from ..core.playlist import Playlist
from ..core.screens import pick_second_screen
from ..core.slideshow_log import SlideshowLog
from .slideshow_window import SlideshowWindow

log = logging.getLogger(__name__)

MIN_SHOW_SECONDS = 2.5   # une nouvelle photo n'écourte pas la précédente en dessous de ce temps
MAX_SKIPS = 20           # photos illisibles écartées d'affilée avant d'abandonner ce tour


@dataclass(frozen=True)
class SlideshowStatus:
    active: bool
    detail: str
    photos: int


class SlideshowController:
    def __init__(self, config, main_window, window_factory=None, screens_provider=None,
                 windowed_preview: bool = False, clock=time.monotonic) -> None:
        self.config = config
        self._main = main_window
        self._window_factory = window_factory or SlideshowWindow
        self._screens = screens_provider or QApplication.screens
        self._windowed = windowed_preview
        self._clock = clock
        self._log = SlideshowLog(config.fichier_diaporama, config.base_dir)
        self.playlist = Playlist(config.dp_ordre)
        self._window = None
        self._screen = None
        self._showing_photo = False
        self._last_change: float | None = None
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._advance)

    # ---------- cycle de vie ----------

    def start(self) -> None:
        self.playlist.load(self._log.load())
        app = QApplication.instance()
        app.screenAdded.connect(self._on_screens_changed)        # écran branché après le lancement
        app.screenRemoved.connect(self._on_screens_changed)
        self.refresh()

    def close(self) -> None:
        self._timer.stop()
        self._close_window()

    def reload(self) -> None:
        """Après « Recharger la configuration »."""
        self.playlist.set_order(self.config.dp_ordre)
        self.refresh()

    def _on_screens_changed(self, *_args) -> None:
        QTimer.singleShot(500, self.refresh)                     # on laisse Windows finir de reconfigurer les écrans

    def refresh(self) -> None:
        """Crée, déplace ou ferme la fenêtre selon les écrans disponibles et le réglage second_ecran_active."""
        if self._windowed:
            self._screen = None
            self._ensure_window()
            self._window.show_windowed()
        elif not self.config.second_ecran_active:
            self._close_window()
            return
        else:
            screen = pick_second_screen(list(self._screens()), self._main.screen())
            if screen is None:
                if self._window is not None:
                    log.info("Second écran débranché : diaporama arrêté")
                else:
                    log.info("Aucun second écran détecté : diaporama désactivé")
                self._close_window()
                return
            self._screen = screen
            self._ensure_window()
            self._window.show_on(screen)
        self._advance()

    def _ensure_window(self) -> None:
        if self._window is None:
            self._window = self._window_factory(self.config)

    def _close_window(self) -> None:
        self._timer.stop()
        if self._window is not None:
            self._window.close()
        self._window, self._screen, self._showing_photo, self._last_change = None, None, False, None

    # ---------- défilement ----------

    def _advance(self) -> None:
        if self._window is None:
            return
        self._showing_photo = False
        for _ in range(MAX_SKIPS):
            path = self.playlist.next()
            if path is None:
                self._window.show_idle()
                break
            if self._window.show_photo(path):
                self._showing_photo, self._last_change = True, self._clock()
                break
            self.playlist.remove(path)                           # illisible : retirée pour de bon
        self._timer.start(self.config.dp_duree * 1000)

    def add_photo(self, path: Path) -> None:
        """Photo validée par l'invité : elle est gardée pour la soirée et s'affiche dès que possible."""
        path = Path(path)
        if not self.playlist.add(path):
            return
        try:
            self._log.append(path)
        except OSError:
            log.exception("Journal du diaporama inaccessible : la photo s'affichera mais ne sera pas retrouvée au redémarrage")
        if self._window is None:
            return
        elapsed = None if self._last_change is None else self._clock() - self._last_change
        if not self._showing_photo or elapsed is None or elapsed >= MIN_SHOW_SECONDS:
            self._advance()
        else:                                                    # la photo en cours finit son temps minimal
            self._timer.start(int((MIN_SHOW_SECONDS - elapsed) * 1000) + 50)

    def clear(self) -> None:
        """Nouvelle soirée : le diaporama repart de zéro (les photos, elles, restent sur le disque)."""
        self._log.clear()
        self.playlist.clear()
        if self._window is not None:
            self._window.show_idle()
            self._showing_photo = False

    # ---------- état ----------

    def status(self) -> SlideshowStatus:
        count = len(self.playlist)
        if self._windowed:
            return SlideshowStatus(True, "fenêtre d'aperçu", count)
        if not self.config.second_ecran_active:
            return SlideshowStatus(False, "désactivé (second_ecran_active = false)", count)
        if self._window is None:
            return SlideshowStatus(False, "aucun second écran détecté (Windows+P puis « Étendre »)", count)
        name = self._screen.name() if self._screen is not None else "?"
        return SlideshowStatus(True, f"affiché sur l'écran {name}", count)
