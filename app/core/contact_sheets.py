"""Génération de planches PNG à partir des photos d'une soirée et d'un invité."""
from __future__ import annotations

import hashlib
import io
import logging
import os
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from .events import Event, EventStore
from .strip_builder import load_font

log = logging.getLogger(__name__)

BACKGROUND = (20, 18, 43)
CARD = (38, 34, 76)
ACCENT = (255, 209, 102)
TEXT = (244, 241, 255)
MUTED = (184, 178, 217)
COLUMNS = 4
CELL_W, CELL_H = 280, 340
MARGIN, GAP = 44, 20
HEADER_H = 170
IMAGE_BOX = (240, 235)

MEDIA_LABELS = {
    "single": "Photo",
    "framed": "Photo avec cadre",
    "strip": "Photomaton",
    "gif": "GIF animé · première image",
}


def _slug(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-zA-Z0-9]+", "-", ascii_text).strip("-").lower()[:48] or "invite"


def _load_thumbnail(path: Path) -> Image.Image:
    with Image.open(path) as source:
        if getattr(source, "is_animated", False):
            source.seek(0)
        image = source.convert("RGB")
        return ImageOps.contain(image, IMAGE_BOX, method=Image.Resampling.LANCZOS)


def _draw_centered(draw: ImageDraw.ImageDraw, text: str, center_x: int, y: int,
                   font, fill, max_width: int | None = None) -> None:
    size = getattr(font, "size", 32)
    while max_width is not None and size > 15 and draw.textlength(text, font=font) > max_width:
        size -= 2
        font = load_font(size)
    width = draw.textlength(text, font=font)
    draw.text((center_x - width / 2, y), text, font=font, fill=fill)


def _output_folder(root: Path, event: Event) -> Path:
    started = datetime.fromtimestamp(event.started_at)
    return root / "planches-contact" / f"{started:%Y-%m-%d_%H%M}_{event.id[:8]}"


def create_contact_sheets(store: EventStore, event: Event, output_root: Path) -> tuple[list[Path], int]:
    """Crée une planche PNG par invité ayant au moins une photo encore disponible."""
    destination = _output_folder(output_root, event)
    created: list[Path] = []
    missing = 0
    for guest in store.guests(event.id):
        records = store.photos_for_guest(event.id, guest.email)
        entries = []
        for record in records:
            try:
                thumbnail = _load_thumbnail(record.path)
            except (OSError, ValueError) as exc:
                log.warning("Photo ignorée pour la planche-contact (%s) : %s", record.path, exc)
                missing += 1
                continue
            entries.append((record, thumbnail))
        if not entries:
            continue

        rows = (len(entries) + COLUMNS - 1) // COLUMNS
        width = MARGIN * 2 + COLUMNS * CELL_W + (COLUMNS - 1) * GAP
        height = HEADER_H + MARGIN + rows * CELL_H + max(0, rows - 1) * GAP + MARGIN
        canvas = Image.new("RGB", (width, height), BACKGROUND)
        draw = ImageDraw.Draw(canvas)
        _draw_centered(draw, guest.display_name, width // 2, 28, load_font(46), ACCENT, width - 2 * MARGIN)
        _draw_centered(draw, event.name, width // 2, 92, load_font(27), MUTED, width - 2 * MARGIN)
        _draw_centered(draw, f"{len(entries)} photo(s)", width // 2, 130, load_font(19), MUTED)

        for index, (record, thumbnail) in enumerate(entries):
            column, row = index % COLUMNS, index // COLUMNS
            x = MARGIN + column * (CELL_W + GAP)
            y = HEADER_H + row * (CELL_H + GAP)
            draw.rounded_rectangle((x, y, x + CELL_W, y + CELL_H), radius=18, fill=CARD)
            image_x = x + (CELL_W - thumbnail.width) // 2
            image_y = y + 12 + (IMAGE_BOX[1] - thumbnail.height) // 2
            canvas.paste(thumbnail, (image_x, image_y))
            label = MEDIA_LABELS.get(record.media_type, "Photo")
            captured = datetime.fromtimestamp(record.created_at).strftime("%H:%M")
            _draw_centered(draw, label, x + CELL_W // 2, y + 263, load_font(21), TEXT, CELL_W - 24)
            _draw_centered(draw, captured, x + CELL_W // 2, y + 299, load_font(18), MUTED)

        email_hash = hashlib.sha256(guest.email.encode("utf-8")).hexdigest()[:8]
        destination.mkdir(parents=True, exist_ok=True)
        path = destination / f"{_slug(guest.display_name)}_{email_hash}.png"
        buffer = io.BytesIO()
        canvas.save(buffer, format="PNG", optimize=True)
        temporary = path.with_suffix(".png.tmp")
        temporary.write_bytes(buffer.getvalue())
        os.replace(temporary, path)
        created.append(path)
        log.info("Planche-contact créée : %s (%d image(s))", path, len(entries))
    return created, missing
