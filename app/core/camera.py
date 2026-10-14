"""Capture webcam dans un thread séparé : l'écran tactile ne se fige jamais.

- Le thread lit la caméra en continu et garde la dernière image pleine résolution
  (`grab_frame()`), utilisée pour la photo finale.
- Pour l'écran, il émet une version réduite (`preview_ready`), au plus une à la fois :
  tant que l'interface n'a pas fini de traiter la précédente (`preview_consumed()`),
  les suivantes sont ignorées, ce qui évite d'accumuler du retard.
"""
from __future__ import annotations

import logging
import threading

import cv2
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QImage

from ..config import Config
from . import webcam
from .qt_image import bgr_to_qimage

log = logging.getLogger(__name__)

MAX_MISSED_READS = 30  # ~1 seconde sans image : on considère la caméra perdue

MSG_NOT_FOUND = ("Caméra introuvable.\nVérifie qu'elle est branchée, qu'aucun autre logiciel "
                 "ne l'utilise (Teams, Zoom…) et que l'accès à la caméra est autorisé "
                 "dans les paramètres de confidentialité de Windows.")
MSG_LOST = "La caméra ne répond plus.\nVérifie le branchement."
MSG_ERROR = "Erreur inattendue avec la caméra."


class CameraWorker(QThread):
    preview_ready = pyqtSignal(QImage)
    failed = pyqtSignal(str)

    def __init__(self, config: Config, parent=None) -> None:
        super().__init__(parent)
        self._config = config
        self._lock = threading.Lock()
        self._latest: np.ndarray | None = None
        self._running = False
        self._preview_enabled = threading.Event()
        self._preview_pending = threading.Event()
        self._preview_processor = None        # fonction image BGR -> image BGR (incrustation du décor)
        self._processor_failed = False

    # ---------- appelé depuis l'interface ----------

    def set_preview_processor(self, processor) -> None:
        """Traitement appliqué à chaque image d'aperçu, dans le thread caméra (None = aperçu brut)."""
        self._processor_failed = False
        self._preview_processor = processor

    def start_camera(self) -> None:
        """Démarre la capture (sans effet si elle tourne déjà)."""
        if self.isRunning():
            if self._running:
                return
            self.wait(2000)  # le thread vient de s'arrêter sur une erreur : on le laisse finir
        with self._lock:
            self._latest = None
        self._preview_pending.clear()
        self._running = True
        self.start()

    def stop_camera(self) -> None:
        self._running = False
        if self.isRunning() and not self.wait(3000):
            log.warning("Le thread caméra ne s'est pas arrêté dans les temps")

    def is_active(self) -> bool:
        return self._running and self.isRunning()

    def has_frame(self) -> bool:
        with self._lock:
            return self._latest is not None

    def grab_frame(self) -> np.ndarray | None:
        """Copie de la dernière image pleine résolution (BGR), ou None si aucune."""
        with self._lock:
            return None if self._latest is None else self._latest.copy()

    def set_preview_enabled(self, enabled: bool) -> None:
        if enabled:
            self._preview_pending.clear()
            self._preview_enabled.set()
        else:
            self._preview_enabled.clear()

    def preview_consumed(self) -> None:
        """À appeler quand l'interface a fini d'afficher la dernière image d'aperçu."""
        self._preview_pending.clear()

    # ---------- thread ----------

    def run(self) -> None:
        cap = None
        try:
            cap = webcam.open_capture(self._config.camera_index,
                                      self._config.resolution_largeur,
                                      self._config.resolution_hauteur)
            if cap is None:
                log.error("Aucune caméra utilisable (index %d)", self._config.camera_index)
                self._running = False
                self.failed.emit(MSG_NOT_FOUND)
                return

            missed = 0
            while self._running:
                ok, frame = cap.read()
                if not ok:
                    missed += 1
                    if missed >= MAX_MISSED_READS:
                        log.error("Caméra perdue (plus d'image)")
                        self._running = False
                        self.failed.emit(MSG_LOST)
                        return
                    self.msleep(30)
                    continue
                missed = 0
                with self._lock:
                    self._latest = frame
                if self._preview_enabled.is_set() and not self._preview_pending.is_set():
                    self._preview_pending.set()
                    self.preview_ready.emit(self._make_preview(frame))
        except Exception:
            log.exception("Erreur dans le thread caméra")
            self._running = False
            self.failed.emit(MSG_ERROR)
        finally:
            if cap is not None:
                cap.release()
            with self._lock:
                self._latest = None
            log.info("Caméra arrêtée")

    def _make_preview(self, frame: np.ndarray) -> QImage:
        small = webcam.shrink(frame, self._config.apercu_largeur)
        if self._config.miroir:
            small = cv2.flip(small, 1)   # avant le décor : seule la personne est inversée, pas le décor
        processor = self._preview_processor
        if processor is not None:
            try:
                small = processor(small)
            except Exception:
                if not self._processor_failed:   # une seule trace dans les logs, pas une par image
                    log.exception("Traitement de l'aperçu en échec : aperçu brut")
                    self._processor_failed = True
        return bgr_to_qimage(small)
