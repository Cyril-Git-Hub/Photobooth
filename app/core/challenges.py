"""Chargement et validation des défis définis dans defis.json."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from ..paths import resource_path

log = logging.getLogger(__name__)
VALID_FORMATS = {"single", "strip", "gif"}
VALID_BACKGROUNDS = {"none", "choose", "random"}
VALID_STYLES = {"original", "cartoon", "sketch", "watercolor", "pop_art", "manga"}


@dataclass(frozen=True)
class Challenge:
    id: str
    title: str
    instruction: str
    photo_format: str
    background: str
    image: Path | None = None
    mask: str = ""
    style: str = ""


def load_challenges(user_file: Path, allow_gif: bool = True) -> list[Challenge]:
    """Charge le fichier modifiable de l'utilisateur ou les défis fournis avec l'application."""
    candidates = (user_file, resource_path("assets/defis.json"))
    raw_challenges = None
    for candidate in candidates:
        try:
            with candidate.open(encoding="utf-8-sig") as stream:
                raw_challenges = json.load(stream)
            break
        except FileNotFoundError:
            continue
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            log.exception("Fichier de défis illisible : %s", candidate)
    if not isinstance(raw_challenges, list):
        log.error("Aucun fichier de défis valide trouvé")
        return []

    challenges: list[Challenge] = []
    seen_ids: set[str] = set()
    for item in raw_challenges:
        if not isinstance(item, dict):
            continue
        challenge_id = str(item.get("id", "")).strip()
        title = str(item.get("titre", "")).strip()
        instruction = str(item.get("consigne", "")).strip()
        photo_format = str(item.get("format", "single")).strip().casefold()
        background = str(item.get("decor", "none")).strip().casefold()
        if (not challenge_id or challenge_id in seen_ids or not title or not instruction
                or photo_format not in VALID_FORMATS or background not in VALID_BACKGROUNDS):
            log.warning("Défi ignoré car sa définition est invalide : %r", challenge_id)
            continue
        if photo_format == "gif" and not allow_gif:
            continue
        image_value = str(item.get("image", "")).strip()
        image_path = None
        if image_value:
            image_path = Path(image_value)
            if not image_path.is_absolute():
                image_path = (user_file.parent / image_path).resolve()
                if not image_path.is_file():
                    image_path = resource_path(image_value)
            if not image_path.is_file():
                log.warning("Image de référence du défi introuvable : %s", image_path)
                image_path = None
        mask = str(item.get("masque", "")).strip()
        style = str(item.get("style", "")).strip().casefold()
        if style and style not in VALID_STYLES:
            log.warning("Style invalide ignoré pour le défi %s : %s", challenge_id, style)
            style = ""
        challenges.append(Challenge(
            challenge_id, title, instruction, photo_format, background, image_path, mask, style))
        seen_ids.add(challenge_id)
    return challenges
