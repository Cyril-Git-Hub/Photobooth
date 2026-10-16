"""Cadres PNG transparents à superposer aux photos uniques sans décor."""
from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np

log = logging.getLogger(__name__)

FRAME_EXTENSIONS = {".png", ".webp"}
MAX_FRAME_DIMENSION = 3840


def scan_frames(directory: Path) -> list[Path]:
    """Liste les cadres visibles du dossier, triés par nom. Les sous-dossiers sont ignorés."""
    try:
        return sorted((path for path in directory.iterdir()
                       if path.is_file() and path.suffix.casefold() in FRAME_EXTENSIONS
                       and not path.name.startswith((".", "_"))), key=lambda path: path.name.casefold())
    except OSError:
        log.exception("Dossier de cadres illisible : %s", directory)
        return []


def load_frame(path: Path) -> np.ndarray | None:
    """Charge un cadre en BGRA. Les images sans transparence ou illisibles sont ignorées."""
    try:
        raw = np.fromfile(str(path), dtype=np.uint8)
    except OSError:
        log.exception("Lecture du cadre impossible : %s", path)
        return None
    try:
        image = cv2.imdecode(raw, cv2.IMREAD_UNCHANGED) if raw.size else None
    except cv2.error:
        log.exception("Décodage du cadre impossible : %s", path)
        return None
    if image is None or image.ndim != 3 or image.shape[2] != 4:
        log.warning("Cadre ignoré (image transparente PNG/WebP attendue) : %s", path)
        return None
    if image.dtype != np.uint8:
        image = cv2.convertScaleAbs(image, alpha=255.0 / np.iinfo(image.dtype).max)
    if not np.any(image[:, :, 3]):
        log.warning("Cadre ignoré (image entièrement transparente) : %s", path)
        return None
    height, width = image.shape[:2]
    scale = min(1.0, MAX_FRAME_DIMENSION / max(width, height))
    if scale < 1.0:
        image = cv2.resize(image, (round(width * scale), round(height * scale)),
                           interpolation=cv2.INTER_AREA)
    return image


def apply_frame(photo_bgr: np.ndarray, frame_bgra: np.ndarray) -> np.ndarray:
    """Superpose le cadre en conservant ses proportions et toute sa transparence."""
    height, width = photo_bgr.shape[:2]
    frame_h, frame_w = frame_bgra.shape[:2]
    scale = min(width / frame_w, height / frame_h)
    target_w = max(1, min(width, round(frame_w * scale)))
    target_h = max(1, min(height, round(frame_h * scale)))
    interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR

    alpha = frame_bgra[:, :, 3].astype(np.float32) / 255.0
    premultiplied = frame_bgra[:, :, :3].astype(np.float32) * alpha[:, :, None]
    if (target_w, target_h) != (frame_w, frame_h):
        alpha = cv2.resize(alpha, (target_w, target_h), interpolation=interpolation)
        premultiplied = cv2.resize(premultiplied, (target_w, target_h), interpolation=interpolation)
    x, y = (width - target_w) // 2, (height - target_h) // 2
    result = photo_bgr.copy()
    region = result[y:y + target_h, x:x + target_w].astype(np.float32)
    result[y:y + target_h, x:x + target_w] = np.clip(
        region * (1.0 - alpha[:, :, None]) + premultiplied, 0, 255
    ).astype(np.uint8)
    return result
