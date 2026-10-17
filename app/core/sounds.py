"""Lecture facultative des effets sonores du thème actif."""
from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtCore import QUrl

try:
    from PyQt6.QtMultimedia import QSoundEffect
except (ImportError, OSError):  # l'interface et la prise de photos restent utilisables sans QtMultimedia
    QSoundEffect = None  # type: ignore[assignment,misc]

from ..config import Config

log = logging.getLogger(__name__)

SOUND_FILES = {
    "countdown": "compte_a_rebours.wav",
    "shutter": "declencheur.wav",
    "success": "reussite.wav",
}


class SoundManager:
    """Gère des sons courts ; un fichier manquant ou un périphérique absent reste sans effet bloquant."""

    def __init__(self, config: Config, parent=None) -> None:
        self.config = config
        self.parent = parent
        self._effects: dict[str, QSoundEffect] = {}
        self._load_effects()

    def _load_effects(self) -> None:
        self._effects.clear()
        if QSoundEffect is None:
            log.warning("QtMultimedia indisponible : effets sonores désactivés")
            return

        theme = self.config.active_theme
        theme_sounds = getattr(theme, "sounds", self.config.dossier_theme / "sons")
        default_sounds = self.config.dossier_themes / "classique" / "sons"
        for name, filename in SOUND_FILES.items():
            path = next((folder / filename for folder in (theme_sounds, default_sounds)
                         if (folder / filename).is_file()), None)
            if path is None:
                log.info("Effet sonore %s absent ; il sera ignoré", filename)
                continue
            try:
                effect = QSoundEffect(self.parent)
                effect.setLoopCount(1)
                effect.setVolume(self.config.son_volume / 100)
                effect.setSource(QUrl.fromLocalFile(str(path.resolve())))
                effect.statusChanged.connect(lambda e=effect, p=path: self._check_status(e, p))
                self._effects[name] = effect
            except Exception:
                log.exception("Chargement du son impossible : %s", path)

    @staticmethod
    def _check_status(effect, path: Path) -> None:
        if QSoundEffect is not None and effect.status() == QSoundEffect.Status.Error:
            log.warning("Son illisible ou périphérique audio indisponible : %s", path)

    def play(self, name: str) -> None:
        if not self.config.son_active:
            return
        effect = self._effects.get(name)
        if effect is None:
            return
        try:
            effect.stop()
            effect.play()
        except Exception:
            log.exception("Lecture de l'effet sonore impossible : %s", name)

    def update_settings(self, active: bool, volume: int) -> None:
        self.config.son_active = bool(active)
        self.config.son_volume = max(0, min(100, int(volume)))
        for effect in self._effects.values():
            effect.setVolume(self.config.son_volume / 100)
            if not self.config.son_active:
                effect.stop()

    def reload(self) -> None:
        for effect in self._effects.values():
            effect.stop()
            effect.deleteLater()
        self._load_effects()

    def stop_all(self) -> None:
        for effect in self._effects.values():
            effect.stop()
