"""Chemins du logiciel.

Tout est relatif au dossier du logiciel (à côté du .exe une fois packagé),
pour pouvoir copier le dossier tel quel sur un autre PC.
"""
from __future__ import annotations

import sys
from pathlib import Path


def app_dir() -> Path:
    """Dossier du logiciel : à côté du .exe (PyInstaller) ou racine du projet (développement)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resolve(path_str: str, base: Path) -> Path:
    """Chemin absolu : un chemin relatif est interprété par rapport à `base`."""
    p = Path(path_str).expanduser()
    return p if p.is_absolute() else (base / p).resolve()


def resource_path(relative: str) -> Path:
    """Fichier embarqué avec le logiciel (icône...) : dans le dossier _internal de l'exécutable, ou dans le projet."""
    base = getattr(sys, "_MEIPASS", None)
    return (Path(base) if base else Path(__file__).resolve().parent.parent) / relative
