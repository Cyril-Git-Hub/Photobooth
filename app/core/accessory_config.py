"""Configuration des profils de placement réutilisables pour les accessoires."""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AccessoryPlacement:
    body_anchor: str = "main"
    orientation: str = "axe_main"
    direction: str = "libre"
    hand_layer: str = "devant"
    image_anchor: tuple[float, float] = (0.5, 0.82)
    size_reference: str = "avant_bras"
    size_ratio: float = 1.8
    rotation_degrees: float = 0.0
    offset: tuple[float, float] = (0.0, 0.0)


@dataclass(frozen=True)
class AccessorySpec:
    image: Path
    placement: AccessoryPlacement
    hand_images: tuple[Path, Path] | None = None
    hand_images_back: tuple[Path, Path] | None = None


DEFAULT_ACCESSORY_PLACEMENT = AccessoryPlacement()
BODY_ANCHORS = {"main", "poignet"}
ORIENTATIONS = {"axe_main", "axe_avant_bras", "verticale", "horizontale"}
SIZE_REFERENCES = {"avant_bras", "main"}
HAND_LAYERS = {"devant", "derriere"}
DIRECTIONS = {"libre", "vers_le_haut"}


def parse_placement(value: Any, base: AccessoryPlacement) -> AccessoryPlacement:
    if not isinstance(value, dict):
        raise ValueError("« placement » doit être un objet JSON.")

    body_anchor = value.get("ancrage_corps", base.body_anchor)
    orientation = value.get("orientation", base.orientation)
    direction = value.get("sens", base.direction)
    hand_layer = value.get("couche", base.hand_layer)
    size = value.get("taille", {})
    image_anchor = value.get("ancrage_image", {})
    offset = value.get("decalage", {})
    if not isinstance(size, dict) or not isinstance(image_anchor, dict) or not isinstance(offset, dict):
        raise ValueError("« taille », « ancrage_image » et « decalage » doivent être des objets JSON.")

    size_reference = size.get("repere", base.size_reference)
    if not isinstance(body_anchor, str) or body_anchor not in BODY_ANCHORS:
        raise ValueError(f"Ancrage corps inconnu : {body_anchor!r}.")
    if not isinstance(orientation, str) or orientation not in ORIENTATIONS:
        raise ValueError(f"Orientation inconnue : {orientation!r}.")
    if not isinstance(direction, str) or direction not in DIRECTIONS:
        raise ValueError(f"Sens d'orientation inconnu : {direction!r}.")
    if not isinstance(hand_layer, str) or hand_layer not in HAND_LAYERS:
        raise ValueError(f"Couche d'accessoire inconnue : {hand_layer!r}.")
    if not isinstance(size_reference, str) or size_reference not in SIZE_REFERENCES:
        raise ValueError(f"Repère de taille inconnu : {size_reference!r}.")

    anchor_x = _number(image_anchor, "x", base.image_anchor[0])
    anchor_y = _number(image_anchor, "y", base.image_anchor[1])
    if not (0 <= anchor_x <= 1 and 0 <= anchor_y <= 1):
        raise ValueError("Les coordonnées de « ancrage_image » doivent être entre 0 et 1.")

    size_ratio = _number(size, "ratio", base.size_ratio)
    if not 0.05 <= size_ratio <= 20:
        raise ValueError("« taille.ratio » doit être compris entre 0.05 et 20.")
    rotation = _number(value, "rotation_deg", base.rotation_degrees)
    if not -360 <= rotation <= 360:
        raise ValueError("« rotation_deg » doit être compris entre -360 et 360.")
    offset_x = _number(offset, "x", base.offset[0])
    offset_y = _number(offset, "y", base.offset[1])
    if not (-5 <= offset_x <= 5 and -5 <= offset_y <= 5):
        raise ValueError("Les valeurs de « decalage » doivent être comprises entre -5 et 5.")

    return AccessoryPlacement(
        body_anchor=body_anchor,
        orientation=orientation,
        direction=direction,
        hand_layer=hand_layer,
        image_anchor=(anchor_x, anchor_y),
        size_reference=size_reference,
        size_ratio=size_ratio,
        rotation_degrees=rotation,
        offset=(offset_x, offset_y),
    )


def _number(value: dict[str, Any], key: str, default: float) -> float:
    raw = value.get(key, default)
    if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(raw):
        raise ValueError(f"Le paramètre numérique {key!r} est invalide.")
    return float(raw)
