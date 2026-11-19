"""Ajoute un repère visuel discret au rendu final d'une photo défi."""
from __future__ import annotations

import cv2
import numpy as np
from PIL import Image, ImageColor, ImageDraw, ImageOps

from .strip_builder import load_font


def stamp_challenge_title(image: np.ndarray, title: str, instruction: str = "",
                          colors: dict[str, str] | None = None) -> np.ndarray:
    """Ajoute en bas à gauche le titre du défi et sa consigne, si elle existe."""
    if not title.strip() and not instruction.strip():
        return image

    height, width = image.shape[:2]
    palette = colors or {}

    def rgba(key: str, fallback: str, alpha: int = 255) -> tuple[int, int, int, int]:
        return (*ImageColor.getrgb(palette.get(key, fallback)), alpha)
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    canvas = Image.fromarray(rgb).convert("RGBA")
    draw = ImageDraw.Draw(canvas, "RGBA")

    margin = max(12, round(width * 0.025))
    padding = max(6, round(width * 0.008))
    max_panel_width = max(1, round(width * 0.63))
    accent_width = max(4, round(width * 0.005))
    content_width = max(1, max_panel_width - 2 * padding - accent_width)
    title_size = max(12, round(width * 0.018))
    title_font = load_font(title_size)
    instruction_size = max(10, round(width * 0.012))
    instruction_font = load_font(instruction_size)

    def wrap(text: str, font) -> list[str]:
        lines: list[str] = []
        for paragraph in text.splitlines():
            words = paragraph.split()
            line = ""
            for word in words:
                candidate = f"{line} {word}".strip()
                if line and draw.textlength(candidate, font=font) > content_width:
                    lines.append(line)
                    line = word
                else:
                    line = candidate
            if line:
                lines.append(line)
        return lines

    title_lines = wrap(title.strip(), title_font)
    instruction_lines = wrap(instruction.strip(), instruction_font)
    widest_line = max(
        (draw.textlength(line, font=font)
         for lines, font in ((title_lines, title_font), (instruction_lines, instruction_font))
         for line in lines),
        default=0,
    )
    panel_width = min(max_panel_width, max(1, round(widest_line) + 2 * padding + accent_width))
    title_line_height = max(title_size + 5, round(title_size * 1.2))
    instruction_line_height = max(instruction_size + 4, round(instruction_size * 1.25))
    gap = max(3, round(padding * 0.35)) if title_lines and instruction_lines else 0
    panel_height = 2 * padding + len(title_lines) * title_line_height
    if instruction_lines:
        panel_height += gap + len(instruction_lines) * instruction_line_height
    left = margin
    top = max(0, height - margin - panel_height)
    right = min(width - margin, left + panel_width)
    bottom = min(height - margin, top + panel_height)
    radius = max(8, round(padding * 0.75))
    draw.rounded_rectangle((left, top, right, bottom), radius=radius,
                           fill=rgba("challenge_panel", "#12102a", 218))
    draw.rounded_rectangle((left, top, left + accent_width * 2, bottom),
                           radius=radius, fill=rgba("accent", "#ffd166"))

    text_x = left + padding + accent_width
    text_y = top + padding
    for line in title_lines:
        draw.text((text_x, text_y), line, font=title_font,
                  fill=rgba("challenge_title", "#ffcd5f"))
        text_y += title_line_height
    if instruction_lines:
        text_y += gap
        for line in instruction_lines:
            draw.text((text_x, text_y), line, font=instruction_font,
                      fill=rgba("challenge_description", "#ffffff"))
            text_y += instruction_line_height

    stamped = cv2.cvtColor(np.asarray(canvas.convert("RGB")), cv2.COLOR_RGB2BGR)
    return stamped


def stamp_challenge_reference(image: np.ndarray, reference_png: bytes | None,
                              colors: dict[str, str] | None = None) -> np.ndarray:
    """Ajoute l'image modèle dans un encart en bas à droite du rendu final."""
    if not reference_png:
        return image
    reference = cv2.imdecode(np.frombuffer(reference_png, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    if reference is None or reference.size == 0:
        return image
    if reference.ndim == 2:
        reference = cv2.cvtColor(reference, cv2.COLOR_GRAY2BGRA)
    elif reference.shape[2] == 3:
        reference = cv2.cvtColor(reference, cv2.COLOR_BGR2BGRA)
    reference_rgb = cv2.cvtColor(reference, cv2.COLOR_BGRA2RGBA)

    height, width = image.shape[:2]
    canvas = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB)).convert("RGBA")
    source = Image.fromarray(reference_rgb).convert("RGBA")
    margin = max(8, round(min(width, height) * 0.025))
    palette = colors or {}
    card_width = max(1, round(width * 0.24))
    card_height = max(1, round(height * 0.30))
    padding = max(5, round(min(width, height) * 0.012))
    fitted = ImageOps.contain(source, (max(1, card_width - 2 * padding),
                                       max(1, card_height - 2 * padding)),
                              method=Image.Resampling.LANCZOS)
    card = Image.new("RGBA", (fitted.width + 2 * padding, fitted.height + 2 * padding),
                     (*ImageColor.getrgb(palette.get("challenge_panel", "#12102a")), 230))
    card.alpha_composite(fitted, (padding, padding))
    ImageDraw.Draw(card).rectangle((0, 0, card.width - 1, card.height - 1),
                                   outline=ImageColor.getrgb(palette.get("reference_border", "#ffc44d")),
                                   width=max(2, padding // 3))
    canvas.alpha_composite(card, (width - margin - card.width, height - margin - card.height))
    return cv2.cvtColor(np.asarray(canvas.convert("RGB")), cv2.COLOR_RGB2BGR)
