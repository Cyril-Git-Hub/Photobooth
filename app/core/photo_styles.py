"""Styles OpenCV appliqués sur l'écran de résultat, sans traitement dans l'aperçu caméra."""
from __future__ import annotations

import cv2
import numpy as np

STYLE_NAMES = {
    "original": "Originale",
    "cartoon": "Bande dessinée",
    "sketch": "Croquis",
    "watercolor": "Aquarelle",
    "pop_art": "Pop-art",
    "manga": "Manga noir et blanc",
}


def apply_style(image: np.ndarray, style: str) -> np.ndarray:
    """Rend une image BGR dans le style demandé, en conservant ses dimensions."""
    if style == "original":
        return image.copy()
    if style == "cartoon":
        smooth = image
        for _ in range(2):
            smooth = cv2.bilateralFilter(smooth, 9, 75, 75)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        edges = cv2.adaptiveThreshold(cv2.medianBlur(gray, 7), 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                      cv2.THRESH_BINARY, 9, 5)
        return cv2.bitwise_and(smooth, smooth, mask=edges)
    if style == "sketch":
        if hasattr(cv2, "pencilSketch"):
            gray, _color = cv2.pencilSketch(image, sigma_s=60, sigma_r=0.07, shade_factor=0.05)
            return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        inverted = 255 - gray
        blur = cv2.GaussianBlur(inverted, (21, 21), 0)
        return cv2.cvtColor(cv2.divide(gray, 255 - blur, scale=256), cv2.COLOR_GRAY2BGR)
    if style == "watercolor":
        if hasattr(cv2, "stylization"):
            return cv2.stylization(image, sigma_s=60, sigma_r=0.45)
        return cv2.bilateralFilter(image, 15, 100, 100)
    if style == "pop_art":
        quantized = (image // 64) * 64 + 32
        return cv2.convertScaleAbs(quantized, alpha=1.25, beta=8)
    if style == "manga":
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        lines = cv2.adaptiveThreshold(cv2.medianBlur(gray, 5), 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                      cv2.THRESH_BINARY, 9, 5)
        return cv2.cvtColor(lines, cv2.COLOR_GRAY2BGR)
    raise ValueError(f"Style photo inconnu : {style}")


def apply_to_subject(original: np.ndarray, styled: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Mélange le style sur la personne et garde le fond original."""
    if styled.shape != original.shape:
        raise ValueError("L'image stylisée n'a pas les dimensions de l'originale.")
    if mask.shape != original.shape[:2]:
        mask = cv2.resize(mask, (original.shape[1], original.shape[0]), interpolation=cv2.INTER_LINEAR)
    alpha = np.clip(mask.astype(np.float32), 0.0, 1.0)[:, :, None]
    result = original.astype(np.float32) * (1.0 - alpha) + styled.astype(np.float32) * alpha
    return np.clip(result, 0, 255).astype(np.uint8)
