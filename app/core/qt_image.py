"""Conversion d'une image OpenCV (BGR) en QImage."""
from __future__ import annotations

import cv2
import numpy as np
from PyQt6.QtGui import QImage


def bgr_to_qimage(frame: np.ndarray) -> QImage:
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    height, width = rgb.shape[:2]
    # .copy() : l'image Qt ne doit plus dépendre du tampon numpy, qui sera libéré
    return QImage(rgb.data, width, height, 3 * width, QImage.Format.Format_RGB888).copy()
