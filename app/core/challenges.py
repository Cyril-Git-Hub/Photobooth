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
    background_image: Path | None = None
    image: Path | None = None
    mask: str = ""
    style: str = ""


def load_challenges(user_file: Path, allow_gif: bool = True) -> list[Challenge]:
    """Charge les défis du thème, puis les défis intégrés si aucun n'est exploitable."""
    candidates = (user_file, resource_path("assets/defis.json"))
    for candidate in candidates:
        try:
            with candidate.open(encoding="utf-8-sig") as stream:
                raw_challenges = json.load(stream)
        except FileNotFoundError:
            continue
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            log.exception("Fichier de défis illisible : %s", candidate)
            continue

        # An object permits explanatory `_commentaire` fields while keeping strict JSON.
        if isinstance(raw_challenges, dict):
            raw_config = raw_challenges
            raw_challenges = raw_config.get("defis", [])
            categories = raw_config.get("categories", [])
            if not isinstance(raw_challenges, list):
                log.warning("Liste de défis invalide dans %s", candidate)
                raw_challenges = []
            if isinstance(categories, list):
                for category in categories:
                    if not isinstance(category, dict):
                        continue
                    category_id = str(category.get("id", "")).strip()
                    images = category.get("images", [])
                    if not category_id or not isinstance(images, list):
                        log.warning("Catégorie de défis invalide dans %s", candidate)
                        continue
                    shared = {key: value for key, value in category.items()
                              if key not in {"id", "images"}}
                    for index, image in enumerate(images, start=1):
                        if not isinstance(image, str) or not image.strip():
                            log.warning("Image vide ou invalide dans la catégorie %s", category_id)
                            continue
                        raw_challenges.append({
                            **shared,
                            "id": f"{category_id}-{index:02d}",
                            "image": image.strip(),
                        })
        else:
            categories = []
        if not isinstance(raw_challenges, list):
            log.warning("Format de liste invalide dans %s", candidate)
            continue

        challenges: list[Challenge] = []
        seen_ids: set[str] = set()
        log.info("Lecture des défis dans %s", candidate)
        for item in raw_challenges:
            if not isinstance(item, dict):
                log.warning("Défi ignoré dans %s : entrée JSON invalide", candidate)
                continue
            challenge_id = str(item.get("id", "")).strip()
            title = str(item.get("titre", "")).strip()
            instruction = str(item.get("consigne", "")).strip()
            photo_format = str(item.get("format", "single")).strip().casefold()
            background = str(item.get("decor", "none")).strip().casefold()
            background_value = str(item.get("fond", "")).strip()
            if (not challenge_id or challenge_id in seen_ids or not title or not instruction
                    or photo_format not in VALID_FORMATS or background not in VALID_BACKGROUNDS):
                log.warning("Défi ignoré car sa définition est invalide : %r (fichier %s)",
                            challenge_id, candidate)
                continue
            if photo_format == "gif" and not allow_gif:
                log.info("Défi %s ignoré : format GIF désactivé", challenge_id)
                continue
            background_image = None
            if background_value:
                background_image = Path(background_value)
                if not background_image.is_absolute():
                    background_image = (candidate.parent / background_image).resolve()
                    if not background_image.is_file():
                        background_image = resource_path(background_value)
                if not background_image.is_file():
                    log.warning("Fond imposé du défi introuvable : %s", background_image)
                    continue
            image_value = str(item.get("image", "")).strip()
            image_path = None
            if image_value:
                image_path = Path(image_value)
                if not image_path.is_absolute():
                    image_path = (candidate.parent / image_path).resolve()
                    if not image_path.is_file():
                        image_path = resource_path(image_value)
                if not image_path.is_file():
                    log.error("Défi ignoré : image de référence introuvable | id=%s | chemin=%s",
                              challenge_id, image_path)
                    continue
            mask = str(item.get("masque", "")).strip()
            style = str(item.get("style", "")).strip().casefold()
            if style and style not in VALID_STYLES:
                log.warning("Style invalide ignoré pour le défi %s : %s", challenge_id, style)
                style = ""
            challenges.append(Challenge(
                challenge_id, title, instruction, photo_format, background,
                background_image, image_path, mask, style))
            seen_ids.add(challenge_id)
            log.info("Défi chargé : id=%s | titre=%s | image=%s | fond=%s",
                     challenge_id, title, image_path if image_path else "aucune",
                     background_image if background_image else background)
        log.info("%d défi(s) chargé(s) depuis %s", len(challenges), candidate)
        if challenges:
            if candidate != user_file:
                log.info("Aucun défi valide dans %s ; défis intégrés utilisés", user_file)
            return challenges
        if candidate == user_file:
            log.info("Aucun défi complet dans %s ; utilisation des défis intégrés", user_file)
    log.error("Aucun fichier de défis valide trouvé")
    return []
