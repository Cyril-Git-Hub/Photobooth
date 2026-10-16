"""Ouverture de la webcam et petits utilitaires d'image, sans dépendance à Qt (donc testables)."""
from __future__ import annotations

import logging
import sys

import cv2

log = logging.getLogger(__name__)

FOURCC_MJPG = cv2.VideoWriter_fourcc(*"MJPG")  # MJPG : bien plus fluide que YUY2 en haute résolution


def candidate_backends() -> list[int]:
    """Sous Windows, DirectShow est le plus fiable ; MSMF et le choix automatique en secours."""
    if sys.platform == "win32":
        return [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY]
    return [cv2.CAP_ANY]


def open_capture(index: int, width: int, height: int):
    """Ouvre la caméra et vérifie qu'elle délivre vraiment une image. Renvoie None si échec."""
    for backend in candidate_backends():
        cap = cv2.VideoCapture(index, backend)
        if not cap.isOpened():
            cap.release()
            continue
        cap.set(cv2.CAP_PROP_FOURCC, FOURCC_MJPG)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # moins de latence (ignoré par certains pilotes)
        ok, _ = cap.read()
        if ok:
            log.info("Caméra %d ouverte (backend %s) : %dx%d", index, backend,
                     int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
            return cap
        log.warning("Caméra %d ouverte mais sans image (backend %s)", index, backend)
        cap.release()
    return None


def shrink(frame, max_width: int):
    """Réduit l'image à `max_width` de large (sans l'agrandir), pour l'aperçu à l'écran."""
    height, width = frame.shape[:2]
    if width <= max_width:
        return frame
    new_height = max(1, int(height * max_width / width))
    return cv2.resize(frame, (max_width, new_height), interpolation=cv2.INTER_AREA)
