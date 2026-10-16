"""Mélange de la personne détourée avec le décor choisi."""
from __future__ import annotations

import logging
import threading
import time

import cv2
import numpy as np

from .segmentation import Segmenter

log = logging.getLogger(__name__)

STATS_EVERY = 60          # une ligne de statistiques dans les logs toutes les N images d'aperçu


def cover_resize(image: np.ndarray, width: int, height: int) -> np.ndarray:
    """Remplit exactement width x height : redimensionne puis recadre au centre (aucune déformation)."""
    src_h, src_w = image.shape[:2]
    scale = max(width / src_w, height / src_h)
    new_w, new_h = max(width, round(src_w * scale)), max(height, round(src_h * scale))
    interpolation = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
    resized = cv2.resize(image, (new_w, new_h), interpolation=interpolation)
    x, y = (new_w - width) // 2, (new_h - height) // 2
    return np.ascontiguousarray(resized[y:y + height, x:x + width])


def blend(frame: np.ndarray, mask: np.ndarray, background: np.ndarray) -> np.ndarray:
    """frame * mask + background * (1 - mask). Les trois ont la même taille."""
    if frame.shape != background.shape or mask.shape != frame.shape[:2]:
        raise ValueError(f"Tailles incompatibles : image {frame.shape}, masque {mask.shape}, décor {background.shape}")
    fg = frame.astype(np.float32)
    bg = background.astype(np.float32)
    out = bg + (fg - bg) * mask[:, :, None]
    return np.clip(out, 0, 255).astype(np.uint8)


class SceneRenderer:
    """Détoure puis incruste dans le décor. Une instance par décor choisi."""

    def __init__(self, segmenter: Segmenter, background_bgr: np.ndarray) -> None:
        self._segmenter = segmenter
        self._background = background_bgr
        self._cache: dict[tuple[int, int], np.ndarray] = {}
        self._cache_lock = threading.Lock()
        self._frames = 0
        self._total_s = 0.0

    def _background_for(self, width: int, height: int) -> np.ndarray:
        with self._cache_lock:
            cached = self._cache.get((width, height))
            if cached is None:
                cached = cover_resize(self._background, width, height)
                self._cache[(width, height)] = cached
            return cached

    def _render(self, frame: np.ndarray, mask: np.ndarray) -> np.ndarray:
        if mask.shape != frame.shape[:2]:
            mask = cv2.resize(mask, (frame.shape[1], frame.shape[0]), interpolation=cv2.INTER_LINEAR)
        frame = self._segmenter.clean_frame(frame, mask)
        return blend(frame, mask, self._background_for(frame.shape[1], frame.shape[0]))

    def render_preview(self, frame: np.ndarray) -> np.ndarray:
        """Aperçu en direct. Le masque n'est volontairement PAS lissé d'une image à l'autre : un lissage
        dans le temps laisse une image fantôme derrière une personne qui bouge."""
        started = time.perf_counter()
        out = self._render(frame, self._segmenter.segment(frame))
        self._record(time.perf_counter() - started, frame.shape)
        return out

    def render_photo(self, frame: np.ndarray) -> np.ndarray:
        """Photo finale en pleine résolution."""
        return self._render(frame, self._segmenter.segment(frame))

    def _record(self, seconds: float, shape: tuple) -> None:
        self._frames += 1
        self._total_s += seconds
        if self._frames % STATS_EVERY == 0:
            average_ms = 1000 * self._total_s / STATS_EVERY
            log.info("Aperçu avec décor : %.0f ms par image (%.0f images/s max) en %dx%d",
                     average_ms, 1000 / max(average_ms, 0.001), shape[1], shape[0])
            self._total_s = 0.0
