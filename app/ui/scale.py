"""Échelle de l'interface : toutes les tailles sont conçues pour un écran 1920x1080 et réduites (ou agrandies) selon l'écran réel.

Sans cela, sur un portable 1366x768 (ou un 1080p affiché à 125-150 %), les écrans dépassent la hauteur disponible et les boutons du bas
sortent du cadre. Les pixels de Qt sont « logiques » : l'échelle d'affichage de Windows est déjà prise en compte dans la taille de l'écran.
"""
from __future__ import annotations

import re

BASE_WIDTH, BASE_HEIGHT = 1920, 1080
MIN_SCALE, MAX_SCALE = 0.5, 1.3       # limites de l'échelle automatique
MIN_MANUAL, MAX_MANUAL = 0.4, 2.0     # limites d'un réglage manuel (config.ini : echelle_interface)

_scale = 1.0


def compute_scale(width: int, height: int) -> float:
    """Échelle automatique : le plus contraignant du rapport en hauteur et du rapport en largeur."""
    if width <= 0 or height <= 0:
        return 1.0
    return max(MIN_SCALE, min(MAX_SCALE, min(height / BASE_HEIGHT, width / BASE_WIDTH)))


def resolve(manual: float | None, width: int, height: int) -> float:
    """Réglage manuel s'il y en a un, sinon échelle automatique."""
    if manual is not None:
        return max(MIN_MANUAL, min(MAX_MANUAL, manual))
    return compute_scale(width, height)


def set_scale(value: float) -> None:
    global _scale
    _scale = value


def get_scale() -> float:
    return _scale


def px(value: int | float) -> int:
    """Taille de conception (écran 1080p) convertie à l'échelle courante ; 0 reste 0, le reste vaut au moins 1."""
    if not value:
        return 0
    return max(1, round(value * _scale))


def scale_stylesheet(stylesheet: str, scale: float | None = None) -> str:
    """Multiplie chaque valeur « NNpx » d'une feuille de style par l'échelle."""
    factor = _scale if scale is None else scale
    return re.sub(r"(\d+)px", lambda m: f"{max(1, round(int(m.group(1)) * factor))}px", stylesheet)


def windowed_size(wanted_width: int, wanted_height: int, screen=None, margin: float = 0.9) -> tuple[int, int]:
    """Taille d'une fenêtre ordinaire (mode fenêtré, développement) : celle souhaitée, sans dépasser 90 % de la zone utile de l'écran.

    Une fenêtre plus grande que l'écran (barre de titre et barre des tâches comprises) cacherait ses boutons du bas,
    et le défilement ne peut rien y faire. `screen` : un QScreen (ou tout objet ayant availableGeometry()) ; None = taille souhaitée.
    """
    try:
        area = screen.availableGeometry()
        avail_w, avail_h = int(area.width()), int(area.height())
    except Exception:
        return wanted_width, wanted_height
    if avail_w <= 0 or avail_h <= 0:
        return wanted_width, wanted_height
    return min(wanted_width, int(avail_w * margin)), min(wanted_height, int(avail_h * margin))
