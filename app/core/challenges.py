"""Chargement et validation des défis définis dans defis.json."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .accessory_config import (
    AccessoryPlacement, AccessorySpec, DEFAULT_ACCESSORY_PLACEMENT, parse_placement,
)
from ..paths import resource_path

log = logging.getLogger(__name__)
VALID_FORMATS = {"single", "strip", "gif"}
VALID_BACKGROUNDS = {"none", "choose", "random"}
VALID_STYLES = {"original", "cartoon", "sketch", "watercolor", "pop_art", "manga"}
VALID_TYPES = {"photo", "guest_wheel", "dance"}


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
    challenge_type: str = "photo"
    accessory: AccessorySpec | None = None


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
            profiles_raw = raw_config.get("profils_accessoires", {})
            profiles: dict[str, AccessoryPlacement] = {}
            if isinstance(profiles_raw, dict):
                for profile_name, profile_data in profiles_raw.items():
                    try:
                        profiles[str(profile_name)] = parse_placement(
                            profile_data, DEFAULT_ACCESSORY_PLACEMENT)
                    except ValueError as exc:
                        log.warning("Profil d'accessoire invalide %r dans %s : %s",
                                    profile_name, candidate, exc)
            elif profiles_raw:
                log.warning("« profils_accessoires » doit être un objet dans %s", candidate)
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
            profiles = {}
        if not isinstance(raw_challenges, list):
            log.warning("Format de liste invalide dans %s", candidate)
            continue

        challenges: list[Challenge] = []
        seen_ids: set[str] = set()
        has_disabled_challenge = False
        log.info("Lecture des défis dans %s", candidate)
        for item in raw_challenges:
            if not isinstance(item, dict):
                log.warning("Défi ignoré dans %s : entrée JSON invalide", candidate)
                continue
            active = item.get("actif", True)
            if not isinstance(active, bool):
                log.warning("Défi ignoré : « actif » doit être un booléen | id=%r", item.get("id"))
                continue
            if not active:
                has_disabled_challenge = True
                log.info("Défi désactivé : %s", item.get("id", "(sans identifiant)"))
                continue
            challenge_id = str(item.get("id", "")).strip()
            title = str(item.get("titre", "")).strip()
            instruction = str(item.get("consigne", "")).strip()
            photo_format = str(item.get("format", "single")).strip().casefold()
            background = str(item.get("decor", "none")).strip().casefold()
            challenge_type = str(item.get("type", "photo")).strip().casefold()
            background_value = str(item.get("fond", "")).strip()
            accessory_value = item.get("accessoire", "")
            if (not challenge_id or challenge_id in seen_ids or not title or not instruction
                    or photo_format not in VALID_FORMATS or background not in VALID_BACKGROUNDS
                    or challenge_type not in VALID_TYPES
                    or (challenge_type == "guest_wheel" and photo_format != "single")
                    or (challenge_type == "dance" and photo_format != "gif")
                    or (accessory_value and
                        (photo_format != "single" or challenge_type != "photo"))):
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
            accessory_path = None
            accessory_spec = None
            accessory_data: dict[str, Any] = {}
            hand_accessory_paths: tuple[Path, Path] | None = None
            hand_accessory_back_paths: tuple[Path, Path] | None = None
            accessory_configured = bool(accessory_value)
            if isinstance(accessory_value, str):
                accessory_image = accessory_value.strip()
                if accessory_configured and not accessory_image:
                    log.error("Défi ignoré : chemin d'accessoire vide | id=%s", challenge_id)
                    continue
            elif isinstance(accessory_value, dict):
                accessory_data = accessory_value
                accessory_image = accessory_data.get("image", "")
                images_value = accessory_data.get("images")
                back_images_value = None
                if images_value is not None:
                    if not isinstance(images_value, dict):
                        log.error("Défi ignoré : « accessoire.images » doit être un objet | id=%s",
                                  challenge_id)
                        continue
                    if "paume" in images_value or "dos" in images_value:
                        palm_images_value = images_value.get("paume")
                        back_images_value = images_value.get("dos")
                        if palm_images_value is None:
                            log.error("Défi ignoré : « accessoire.images.paume » est obligatoire | id=%s",
                                      challenge_id)
                            continue
                    else:
                        palm_images_value = images_value

                    def resolve_hand_images(
                        image_set: Any, orientation: str,
                    ) -> tuple[Path, Path] | None:
                        if (not isinstance(image_set, dict)
                                or not all(isinstance(image_set.get(side), str)
                                           and image_set[side].strip()
                                           for side in ("gauche", "droite"))):
                            log.error(
                                "Défi ignoré : « accessoire.images.%s » doit définir gauche et droite | id=%s",
                                orientation, challenge_id)
                            return None
                        paths = []
                        for side in ("gauche", "droite"):
                            path = Path(image_set[side].strip())
                            if not path.is_absolute():
                                path = (candidate.parent / path).resolve()
                                if not path.is_file():
                                    path = resource_path(image_set[side].strip())
                            if path.suffix.casefold() != ".png" or not path.is_file():
                                log.error(
                                    "Défi ignoré : image d'accessoire %s introuvable | id=%s | chemin=%s",
                                    side, challenge_id, path)
                                return None
                            paths.append(path)
                        return paths[0], paths[1]

                    hand_accessory_paths = resolve_hand_images(palm_images_value, "paume")
                    if hand_accessory_paths is None:
                        continue
                    if back_images_value is not None:
                        hand_accessory_back_paths = resolve_hand_images(back_images_value, "dos")
                        if hand_accessory_back_paths is None:
                            continue
                    else:
                        hand_accessory_back_paths = None
                    accessory_image = str(hand_accessory_paths[0])
                elif not isinstance(accessory_image, str) or not accessory_image.strip():
                    log.error("Défi ignoré : « accessoire.image » est obligatoire | id=%s",
                              challenge_id)
                    continue
                else:
                    accessory_image = accessory_image.strip()
            elif accessory_value:
                log.warning("Défi ignoré : « accessoire » doit être un chemin ou un objet | id=%s",
                            challenge_id)
                continue
            else:
                accessory_image = ""
            if accessory_image:
                accessory_path = Path(accessory_image)
                if not accessory_path.is_absolute():
                    accessory_path = (candidate.parent / accessory_path).resolve()
                    if not accessory_path.is_file():
                        accessory_path = resource_path(accessory_image)
                if accessory_path.suffix.casefold() != ".png" or not accessory_path.is_file():
                    log.error("Défi ignoré : accessoire PNG introuvable | id=%s | chemin=%s",
                              challenge_id, accessory_path)
                    continue
                profile_name = accessory_data.get("profil", "")
                if not isinstance(profile_name, str):
                    log.error("Défi ignoré : « accessoire.profil » doit être un nom | id=%s",
                              challenge_id)
                    continue
                if profile_name and profile_name not in profiles:
                    log.error("Défi ignoré : profil d'accessoire inconnu %r | id=%s",
                              profile_name, challenge_id)
                    continue
                placement = profiles.get(profile_name, DEFAULT_ACCESSORY_PLACEMENT)
                if "placement" in accessory_data:
                    try:
                        placement = parse_placement(accessory_data["placement"], placement)
                    except ValueError as exc:
                        log.error("Défi ignoré : placement d'accessoire invalide | id=%s | %s",
                                  challenge_id, exc)
                        continue
                accessory_spec = AccessorySpec(
                    accessory_path, placement, hand_accessory_paths,
                    hand_accessory_back_paths)
            mask = str(item.get("masque", "")).strip()
            style = str(item.get("style", "")).strip().casefold()
            if style and style not in VALID_STYLES:
                log.warning("Style invalide ignoré pour le défi %s : %s", challenge_id, style)
                style = ""
            challenges.append(Challenge(
                challenge_id, title, instruction, photo_format, background,
                background_image, image_path, mask, style, challenge_type, accessory_spec))
            seen_ids.add(challenge_id)
            log.info("Défi chargé : id=%s | titre=%s | image=%s | fond=%s",
                     challenge_id, title, image_path if image_path else "aucune",
                     background_image if background_image else background)
        log.info("%d défi(s) chargé(s) depuis %s", len(challenges), candidate)
        if challenges:
            if candidate != user_file:
                log.info("Aucun défi valide dans %s ; défis intégrés utilisés", user_file)
            return challenges
        if candidate == user_file and has_disabled_challenge:
            log.info("Tous les défis du thème sont désactivés dans %s", user_file)
            return []
        if candidate == user_file:
            log.info("Aucun défi complet dans %s ; utilisation des défis intégrés", user_file)
    log.error("Aucun fichier de défis valide trouvé")
    return []
