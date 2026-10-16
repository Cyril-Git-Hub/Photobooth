"""Décors : un sous-dossier de fonds/ = un thème. Ajouter une image = la déposer dans le dossier."""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .webcam import shrink

log = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
LOOSE_THEME_NAME = "Divers"      # images posées directement dans fonds/
MAX_BACKGROUND_WIDTH = 3840      # au-delà, on réduit au chargement (économie de mémoire)


@dataclass(frozen=True)
class Theme:
    name: str
    images: tuple[Path, ...]


def _images_in(folder: Path) -> tuple[Path, ...]:
    try:
        files = [p for p in folder.iterdir()
                 if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS and not p.name.startswith(".")]
    except OSError:
        log.exception("Dossier illisible : %s", folder)
        return ()
    return tuple(sorted(files, key=lambda p: p.name.casefold()))


def scan_backgrounds(fonds_dir: Path) -> list[Theme]:
    """Thèmes triés par nom ; les thèmes sans image et les dossiers cachés (. ou _) sont ignorés."""
    if not fonds_dir.is_dir():
        return []
    try:
        subfolders = sorted((p for p in fonds_dir.iterdir()
                             if p.is_dir() and not p.name.startswith((".", "_"))),
                            key=lambda p: p.name.casefold())
    except OSError:
        log.exception("Dossier des fonds illisible : %s", fonds_dir)
        return []
    themes = [Theme(folder.name, images) for folder in subfolders if (images := _images_in(folder))]
    loose = _images_in(fonds_dir)
    if loose:
        themes.append(Theme(LOOSE_THEME_NAME, loose))
    return themes


def random_background(themes: list[Theme], rng: random.Random | None = None) -> Path | None:
    pool = [path for theme in themes for path in theme.images]
    return (rng or random).choice(pool) if pool else None


def load_image(path: Path) -> np.ndarray | None:
    """Charge une image en BGR (np.fromfile : fonctionne avec les accents sous Windows). None si illisible."""
    try:
        data = np.fromfile(str(path), dtype=np.uint8)
    except OSError:
        log.exception("Lecture impossible : %s", path)
        return None
    image = cv2.imdecode(data, cv2.IMREAD_COLOR) if data.size else None
    if image is None:
        log.error("Image illisible ou corrompue : %s", path)
        return None
    return shrink(image, MAX_BACKGROUND_WIDTH)
