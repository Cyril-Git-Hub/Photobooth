"""Assemblage de la bande « photomaton » (Pillow) : poses empilées, marges, titre et date en bas."""
from __future__ import annotations

import functools
import logging
from dataclasses import dataclass
from typing import Sequence

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .compositor import cover_resize

log = logging.getLogger(__name__)

CELL_W, CELL_H = 800, 600     # chaque pose est recadrée au centre en 4:3 : 4 poses donnent une bande de format 1:3
MARGIN, GAP = 40, 30
FOOTER_H = 190                # bandeau du bas (titre + date), ajouté seulement s'il y a du texte
TITLE_SIZE, DATE_SIZE, MIN_FONT_SIZE = 76, 48, 24
MAX_TITLE_LINES, LINE_GAP = 2, 12
FONT_CANDIDATES = ("segoeuib.ttf", "segoeui.ttf", "arialbd.ttf", "arial.ttf",
                   "DejaVuSans-Bold.ttf", "DejaVuSans.ttf", "LiberationSans-Bold.ttf")


@dataclass(frozen=True)
class StripStyle:
    title: str = ""
    date_text: str = ""
    background: str = "#ffffff"
    text_color: str = "#1c1c1c"


@functools.lru_cache(maxsize=32)
def load_font(size: int):
    """Police système (Segoe UI sous Windows) ; à défaut, la police intégrée à Pillow."""
    for name in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    for fallback in (lambda: ImageFont.load_default(size),      # Pillow >= 10.1 : police à la bonne taille
                     ImageFont.load_default,
                     ImageFont.load_default_imagefont):          # dernier recours : police bitmap, sans FreeType
        try:
            return fallback()
        except (TypeError, OSError, AttributeError):
            continue
    raise OSError("Aucune police disponible")


def _line_height(draw: ImageDraw.ImageDraw, font) -> int:
    """Hauteur d'une ligne, identique pour tous les textes d'une même police (accents et jambages inclus)."""
    _, top, _, bottom = draw.textbbox((0, 0), "Éjg", font=font)
    return bottom - top


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int, max_lines: int) -> list[str] | None:
    """Coupe `text` en au plus `max_lines` lignes qui tiennent dans `max_width` ; None si impossible."""
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
        elif current and draw.textlength(word, font=font) <= max_width:
            lines.append(current)
            current = word
        else:
            return None                                  # un seul mot plus large que la bande
    if current:
        lines.append(current)
    return lines if 0 < len(lines) <= max_lines else None


def _truncate(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> str:
    text = text.strip()
    while text and draw.textlength(text + "…", font=font) > max_width:
        text = text[:-1].rstrip()
    return text + "…"


def _footer_lines(draw: ImageDraw.ImageDraw, style: StripStyle, usable: int, available_height: int) -> list[tuple[str, object]]:
    """Lignes du bandeau : titre (1 ou 2 lignes, police réduite au besoin), puis la date."""
    date_font = None
    date_block = 0
    if style.date_text:
        size = DATE_SIZE
        date_font = load_font(size)
        while size > MIN_FONT_SIZE and draw.textlength(style.date_text, font=date_font) > usable:
            size -= 4
            date_font = load_font(size)
        date_block = _line_height(draw, date_font) + LINE_GAP
    lines: list[tuple[str, object]] = []
    if style.title:
        size = TITLE_SIZE
        while True:
            font = load_font(size)
            wrapped = _wrap(draw, style.title, font, usable, MAX_TITLE_LINES)
            height = len(wrapped or []) * _line_height(draw, font) + LINE_GAP * max(len(wrapped or []) - 1, 0)
            if (wrapped is not None and height + date_block <= available_height) or size <= MIN_FONT_SIZE:
                break
            size -= 4
        if wrapped is None:                              # ne tient pas, même à la plus petite police
            wrapped = [_truncate(draw, style.title, font, usable)]
        lines += [(text, font) for text in wrapped]
    if date_font is not None:
        lines.append((style.date_text, date_font))
    return lines


def build_strip(poses: Sequence[np.ndarray], style: StripStyle) -> np.ndarray:
    """Bande verticale (image BGR) à partir de poses BGR de n'importe quelle taille."""
    if not poses:
        raise ValueError("Aucune pose à assembler")
    count = len(poses)
    has_footer = bool(style.title or style.date_text)
    width = CELL_W + 2 * MARGIN
    cells_bottom = MARGIN + count * CELL_H + (count - 1) * GAP
    height = cells_bottom + MARGIN + (FOOTER_H if has_footer else 0)

    canvas = Image.new("RGB", (width, height), style.background)
    for index, pose in enumerate(poses):
        cell = cover_resize(pose, CELL_W, CELL_H)
        canvas.paste(Image.fromarray(cv2.cvtColor(cell, cv2.COLOR_BGR2RGB)), (MARGIN, MARGIN + index * (CELL_H + GAP)))

    if has_footer:
        draw = ImageDraw.Draw(canvas)
        region_top, region_height = cells_bottom, FOOTER_H + MARGIN
        lines = _footer_lines(draw, style, width - 2 * MARGIN, region_height - MARGIN)
        total = sum(_line_height(draw, font) for _, font in lines) + LINE_GAP * (len(lines) - 1)
        y = region_top + (region_height - total) / 2
        for text, font in lines:
            _, top, _, _ = draw.textbbox((0, 0), "Éjg", font=font)
            x = (width - draw.textlength(text, font=font)) / 2
            draw.text((x, y - top), text, font=font, fill=style.text_color)
            y += _line_height(draw, font) + LINE_GAP
    return cv2.cvtColor(np.asarray(canvas), cv2.COLOR_RGB2BGR)
