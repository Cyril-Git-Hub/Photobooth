"""Création de GIF animés compacts à partir des poses capturées par OpenCV."""
from __future__ import annotations

import io
import os
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from ..config import Config
from .storage import slugify


def _destination(config: Config, guest_name: str, now: datetime | None = None) -> Path:
    now = now or datetime.now()
    folder = config.dossier_photos / now.strftime("%Y-%m-%d")
    stem = now.strftime("%H%M%S")
    slug = slugify(guest_name)
    if slug:
        stem += f"_{slug}"
    candidate = folder / f"{stem}.gif"
    counter = 2
    while candidate.exists():
        candidate = folder / f"{stem}_{counter}.gif"
        counter += 1
    return candidate


def _ordered_frames(frames: list[np.ndarray], effect: str) -> list[np.ndarray]:
    if effect == "boomerang" and len(frames) > 2:
        return [*frames, *frames[-2:0:-1]]
    return frames


def _encode(frames: list[np.ndarray], width: int, colors: int, durations: list[int]) -> bytes:
    images: list[Image.Image] = []
    for frame in frames:
        height, original_width = frame.shape[:2]
        target_height = max(1, round(height * width / original_width))
        resized = cv2.resize(frame, (width, target_height), interpolation=cv2.INTER_AREA) if width < original_width else frame
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(rgb).quantize(colors=colors, method=Image.Quantize.MEDIANCUT)
        images.append(image)
    output = io.BytesIO()
    images[0].save(output, format="GIF", save_all=True, append_images=images[1:],
                    duration=durations, loop=0, optimize=True, disposal=2)
    return output.getvalue()


def save_gif(config: Config, frames: list[np.ndarray], guest_name: str = "", *,
             effect: str = "loop", hold_last: bool = False,
             now: datetime | None = None) -> Path:
    """Encode et enregistre le GIF, en réduisant résolution puis palette jusqu'à la limite configurée."""
    if not frames:
        raise ValueError("Aucune image à encoder en GIF")
    sequence = _ordered_frames(frames, effect)
    width = min(960, max(frame.shape[1] for frame in sequence))
    multiplier = {"fast": 0.5, "slow": 2.0}.get(effect, 1.0)
    normal_duration = max(20, round(config.gif_duree_image_ms * multiplier / 10) * 10)
    durations = [normal_duration] * len(sequence)
    if hold_last:
        durations[-1] = max(normal_duration, config.gif_pause_derniere_image_ms)

    maximum = config.gif_limite_mo * 1024 * 1024
    data = b""
    for colors in (192, 128, 96, 64):
        current_width = width
        while current_width >= min(320, width):
            data = _encode(sequence, current_width, colors, durations)
            if len(data) <= maximum:
                destination = _destination(config, guest_name, now)
                destination.parent.mkdir(parents=True, exist_ok=True)
                temporary = destination.with_suffix(".gif.tmp")
                temporary.write_bytes(data)
                os.replace(temporary, destination)
                return destination
            next_width = int(current_width * 0.85)
            if next_width >= current_width:
                break
            current_width = max(min(320, width), next_width)
            if current_width == min(320, width):
                data = _encode(sequence, current_width, colors, durations)
                if len(data) <= maximum:
                    destination = _destination(config, guest_name, now)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    temporary = destination.with_suffix(".gif.tmp")
                    temporary.write_bytes(data)
                    os.replace(temporary, destination)
                    return destination
                break
    raise ValueError(f"Le GIF dépasse la limite de {config.gif_limite_mo} Mo même après optimisation.")
