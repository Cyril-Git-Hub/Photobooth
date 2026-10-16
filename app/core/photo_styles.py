"""Rendus photo OpenCV appliqués au résultat, jamais à l'aperçu de la caméra."""
from __future__ import annotations

import cv2
import numpy as np

STYLE_NAMES = {
    "original": "Originale",
    "cartoon": "Bande dessinée",
    "sketch": "Croquis",
    "watercolor": "Aquarelle",
    "pop_art": "Pop-art",
    "manga": "Manga",
}


def apply_style(image: np.ndarray, style: str) -> np.ndarray:
    """Rend une image BGR dans le style demandé, en conservant ses dimensions."""
    if image.ndim != 3 or image.shape[2] != 3:
        raise ValueError("L'image doit être au format BGR à trois canaux.")
    if style == "original":
        return image.copy()
    if style == "cartoon":
        return _cartoon(image)
    if style == "sketch":
        return _sketch(image)
    if style == "watercolor":
        return _watercolor(image)
    if style == "pop_art":
        return _pop_art(image)
    if style == "manga":
        return _manga(image)
    raise ValueError(f"Style photo inconnu : {style}")


def _cartoon(image: np.ndarray) -> np.ndarray:
    smooth = image
    for _ in range(3):
        smooth = cv2.bilateralFilter(smooth, 9, 85, 85)

    hsv = cv2.cvtColor(smooth, cv2.COLOR_BGR2HSV)
    hsv[:, :, 1] = cv2.convertScaleAbs(hsv[:, :, 1], alpha=1.22, beta=8)
    vibrant = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
    # Une palette réduite donne des aplats nets plutôt qu'un simple lissage.
    quantized = ((vibrant.astype(np.uint16) // 40) * 40 + 20).clip(0, 255).astype(np.uint8)

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.adaptiveThreshold(cv2.medianBlur(gray, 7), 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                  cv2.THRESH_BINARY, 9, 5)
    edges = cv2.medianBlur(edges, 3)
    ink = cv2.erode(edges, np.ones((2, 2), np.uint8), iterations=1)
    return cv2.bitwise_and(quantized, quantized, mask=ink)


def _sketch(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    if hasattr(cv2, "pencilSketch"):
        pencil, _color = cv2.pencilSketch(image, sigma_s=60, sigma_r=0.08, shade_factor=0.06)
        gray = cv2.addWeighted(gray, 0.28, pencil, 0.72, 0)
    else:
        inverted = 255 - gray
        blur = cv2.GaussianBlur(inverted, (21, 21), 0)
        gray = cv2.divide(gray, 255 - blur, scale=256)

    # Papier ivoire et traits plus profonds donnent un aspect dessin fini.
    gray = cv2.convertScaleAbs(gray, alpha=1.24, beta=-16)
    paper = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR).astype(np.float32)
    paper[:, :, 0] *= 0.91
    paper[:, :, 1] *= 0.97
    paper[:, :, 2] = np.minimum(255, paper[:, :, 2] * 1.03 + 3)
    return np.clip(paper, 0, 255).astype(np.uint8)


def _watercolor(image: np.ndarray) -> np.ndarray:
    if hasattr(cv2, "stylization"):
        painted = cv2.stylization(image, sigma_s=70, sigma_r=0.38)
    else:
        painted = cv2.bilateralFilter(image, 17, 110, 110)

    # Renforce doucement les pigments et les aplats, sans durcir les contours.
    hsv = cv2.cvtColor(painted, cv2.COLOR_BGR2HSV)
    hsv[:, :, 1] = cv2.convertScaleAbs(hsv[:, :, 1], alpha=1.12, beta=3)
    saturated = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
    palette = ((saturated.astype(np.uint16) // 32) * 32 + 16).clip(0, 255).astype(np.uint8)
    return cv2.addWeighted(saturated, 0.68, palette, 0.32, 0)


def _pop_art(image: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    hsv[:, :, 1] = cv2.convertScaleAbs(hsv[:, :, 1], alpha=1.5, beta=18)
    hsv[:, :, 2] = cv2.convertScaleAbs(hsv[:, :, 2], alpha=1.12, beta=-8)
    vivid = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
    poster = ((vivid.astype(np.uint16) // 48) * 48 + 24).clip(0, 255).astype(np.uint8)

    height, width = image.shape[:2]
    period = max(7, round(width / 75))
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    x = (np.arange(width) % period - period / 2).astype(np.float32)
    y = (np.arange(height) % period - period / 2).astype(np.float32)
    radius = (1.0 - gray) * (period * 0.48)
    dots = x[None, :] ** 2 + y[:, None] ** 2 < radius ** 2
    poster[dots] = (poster[dots].astype(np.float32) * 0.28).astype(np.uint8)
    return poster


def _manga(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    smooth = cv2.bilateralFilter(gray, 7, 45, 45)
    lines = cv2.adaptiveThreshold(smooth, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                  cv2.THRESH_BINARY, 11, 4)
    lines = cv2.medianBlur(lines, 3)

    height, width = gray.shape
    period = max(5, round(width / 95))
    x = (np.arange(width) % period - period / 2).astype(np.float32)
    y = (np.arange(height) % period - period / 2).astype(np.float32)
    darkness = np.clip((190.0 - smooth.astype(np.float32)) / 145.0, 0.0, 1.0)
    radius = darkness * (period * 0.48)
    dots = x[None, :] ** 2 + y[:, None] ** 2 < radius ** 2
    tone = np.where(dots, 0, 255).astype(np.uint8)
    # Les noirs francs deviennent de l'encre, les gris des trames manga.
    tone[smooth < 42] = 0
    ink = cv2.bitwise_and(lines, tone)
    return cv2.cvtColor(ink, cv2.COLOR_GRAY2BGR)


def apply_to_subject(original: np.ndarray, styled: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Mélange le style sur la personne et garde le fond original."""
    if styled.shape != original.shape:
        raise ValueError("L'image stylisée n'a pas les dimensions de l'originale.")
    if mask.shape != original.shape[:2]:
        mask = cv2.resize(mask, (original.shape[1], original.shape[0]), interpolation=cv2.INTER_LINEAR)
    alpha = np.clip(mask.astype(np.float32), 0.0, 1.0)[:, :, None]
    result = original.astype(np.float32) * (1.0 - alpha) + styled.astype(np.float32) * alpha
    return np.clip(result, 0, 255).astype(np.uint8)
