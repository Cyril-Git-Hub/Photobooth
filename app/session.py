"""État d'un passage devant le Photobooth : remis à zéro à chaque retour à l'accueil."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


@dataclass
class Session:
    guest_last_name: str = ""
    guest_first_name: str = ""
    guest_pseudo: str = ""
    guest_from_list: bool = False
    email: str = ""
    photo_format: str = "single"        # "single" (photo), "strip" (photomaton), "gif"
    gif_capture_mode: str = "spaced"     # "spaced" ou "burst"
    gif_effect: str = "loop"             # loop, boomerang, fast ou slow
    gif_hold_last: bool = False
    background_path: Path | None = None
    frame_mode: bool = False
    frame_path: Path | None = None
    virtual_mask_path: Path | None = None
    virtual_mask_paths: list[Path] = field(default_factory=list)
    challenge_id: str = ""
    challenge_title: str = ""
    challenge_instruction: str = ""
    challenge_background_required: bool = False
    challenge_mask: str = ""
    challenge_style: str = ""
    challenge_reference_png: bytes | None = None
    event_id: str = ""
    event_started_at: float = 0.0
    photo_source_frame: np.ndarray | None = None  # image caméra sans décor, gardée pour segmenter le sujet au résultat
    photo_style: str = "original"
    photo_style_person_only: bool = False
    photos: list[Path] = field(default_factory=list)
    poses: list[Path] = field(default_factory=list)   # poses individuelles de la bande (mode photomaton)

    @property
    def display_name(self) -> str:
        return self.guest_pseudo or f"{self.guest_first_name} {self.guest_last_name}".strip()

    def reset(self) -> None:
        self.__dict__.update(vars(Session()))
