"""Ajoute un repère visuel discret au rendu final d'une photo défi."""
from __future__ import annotations

import cv2
import numpy as np
from PIL import Image, ImageDraw

from .strip_builder import load_font


def stamp_challenge_title(image: np.ndarray, title: str) -> np.ndarray:
    """Renvoie une copie de l'image avec le nom du défi dans un bandeau supérieur."""
    if not title.strip():
        return image

    height, width = image.shape[:2]
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    canvas = Image.fromarray(rgb).convert("RGBA")
    draw = ImageDraw.Draw(canvas, "RGBA")

    margin = max(12, round(width * 0.025))
    banner_height = max(54, min(round(width * 0.105), round(height * 0.18)))
    left, top, right, bottom = margin, margin, width - margin, min(height - margin, margin + banner_height)
    radius = max(12, round(banner_height * 0.18))
    draw.rounded_rectangle((left, top, right, bottom), radius=radius, fill=(18, 16, 42, 218))

    accent_width = max(5, round(width * 0.008))
    draw.rounded_rectangle((left, top, left + accent_width * 2, bottom),
                           radius=radius, fill=(255, 196, 77, 255))
    label_size = max(12, round(banner_height * 0.19))
    label_font = load_font(label_size)
    label = "DÉFI"
    label_x = left + accent_width * 3 + max(8, round(width * 0.012))
    label_y = top + max(5, round(banner_height * 0.11))
    draw.text((label_x, label_y), label, font=label_font, fill=(255, 205, 95, 255))

    title_size = max(16, round(banner_height * 0.37))
    title_font = load_font(title_size)
    available_width = right - label_x - max(12, round(width * 0.025))
    while title_size > 14 and draw.textlength(title, font=title_font) > available_width:
        title_size -= 2
        title_font = load_font(title_size)
    title_y = top + round(banner_height * 0.43)
    draw.text((label_x, title_y), title, font=title_font, fill=(255, 255, 255, 255))

    stamped = cv2.cvtColor(np.asarray(canvas.convert("RGB")), cv2.COLOR_RGB2BGR)
    return stamped
