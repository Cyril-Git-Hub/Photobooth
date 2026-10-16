"""Journal des photos validées, pour que le diaporama retrouve la soirée après un redémarrage.

Une photo n'y entre qu'une fois validée par l'invité (« Valider ») : une photo refusée, ou prise puis abandonnée,
n'apparaît jamais. Un fichier texte, une ligne par photo (data/diaporama.jsonl).
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

log = logging.getLogger(__name__)


class SlideshowLog:
    def __init__(self, path: Path, base_dir: Path) -> None:
        self.path = path
        self.base_dir = base_dir

    def _encode(self, photo: Path) -> str:
        try:
            return photo.relative_to(self.base_dir).as_posix()    # relatif : le dossier du logiciel peut changer de place
        except ValueError:
            return str(photo)

    def _decode(self, text: str) -> Path:
        path = Path(text)
        return path if path.is_absolute() else self.base_dir / path

    def append(self, photo: Path) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps({"path": self._encode(photo), "time": time.time()}, ensure_ascii=False)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def load(self) -> list[Path]:
        """Photos du journal, dans l'ordre, sans doublon ; celles qui n'existent plus sont ignorées."""
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return []
        except (OSError, UnicodeDecodeError):
            log.exception("Journal du diaporama illisible : %s", self.path)
            return []
        photos: list[Path] = []
        seen: set[Path] = set()
        for line in lines:
            try:
                path = self._decode(json.loads(line)["path"])
            except (ValueError, KeyError, TypeError):
                continue                                          # ligne abîmée : on passe à la suivante
            if path not in seen and path.is_file():
                seen.add(path)
                photos.append(path)
        return photos

    def clear(self) -> None:
        if self.path.exists():
            self.path.write_text("", encoding="utf-8")
