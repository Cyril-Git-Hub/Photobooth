"""Une seule borne à la fois : lancer le logiciel deux fois ferait se battre les deux copies pour la caméra et les fichiers."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QLockFile

STALE_LOCK_MS = 60_000


def acquire(lock_path: Path):
    """Verrou à garder (référence vivante) jusqu'à la fermeture ; None si une autre copie tourne déjà.

    Après un plantage, le verrou laissé derrière est reconnu comme périmé (le processus n'existe plus) :
    la relance automatique n'est donc jamais bloquée.
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(lock_path))
    lock.setStaleLockTime(STALE_LOCK_MS)
    return lock if lock.tryLock(200) else None
