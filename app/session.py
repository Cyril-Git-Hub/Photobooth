"""État d'un passage devant le photo booth : remis à zéro à chaque retour à l'accueil."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Session:
    guest_last_name: str = ""
    guest_first_name: str = ""
    email: str = ""
    photo_format: str = "single"        # "single" (photo unique) ou "strip" (photomaton)
    background_path: Path | None = None
    frame_mode: bool = False
    frame_path: Path | None = None
    photos: list[Path] = field(default_factory=list)
    poses: list[Path] = field(default_factory=list)   # poses individuelles de la bande (mode photomaton)

    @property
    def display_name(self) -> str:
        return f"{self.guest_first_name} {self.guest_last_name}".strip()

    def reset(self) -> None:
        self.__dict__.update(vars(Session()))
