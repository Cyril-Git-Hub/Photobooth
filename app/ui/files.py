"""Petits services de fichiers pour l'interface."""
from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices

log = logging.getLogger(__name__)


def open_folder(path: Path) -> bool:
    """Ouvre un dossier dans l'Explorateur Windows. Renvoie False si ce n'est pas possible."""
    try:
        return bool(QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))))
    except Exception:
        log.exception("Impossible d'ouvrir le dossier %s", path)
        return False
