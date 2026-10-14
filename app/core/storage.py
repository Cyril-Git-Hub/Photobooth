"""Enregistrement des photos : photos/AAAA-MM-JJ/HHMMSS_prenom-nom.jpg"""
from __future__ import annotations

import logging
import os
import re
import unicodedata
from datetime import datetime
from pathlib import Path

import cv2

from ..config import Config

log = logging.getLogger(__name__)

JPEG_QUALITY = 92
POSES_DIR = "poses"   # poses individuelles, dans le dossier du jour


def slugify(text: str, max_len: int = 40) -> str:
    """« Léa Martin » -> « lea-martin » : sûr pour un nom de fichier Windows."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^A-Za-z0-9]+", "-", ascii_text).strip("-").lower()
    return slug[:max_len].strip("-")


def next_photo_path(config: Config, guest_name: str = "", now: datetime | None = None) -> Path:
    now = now or datetime.now()
    folder = config.dossier_photos / now.strftime("%Y-%m-%d")
    stem = now.strftime("%H%M%S")
    slug = slugify(guest_name)
    if slug:
        stem = f"{stem}_{slug}"
    candidate = folder / f"{stem}.jpg"
    counter = 2
    while candidate.exists():  # deux photos dans la même seconde
        candidate = folder / f"{stem}_{counter}.jpg"
        counter += 1
    return candidate


def _write_jpeg(frame, dest: Path) -> None:
    """Écrit une image BGR en JPEG.

    - cv2.imwrite échoue en silence si le chemin contient des accents sous Windows :
      on encode en mémoire puis on écrit nous-mêmes.
    - Écriture dans un fichier temporaire puis renommage : un diaporama qui surveille le
      dossier ne verra jamais une photo à moitié écrite.
    """
    ok, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    if not ok:
        raise ValueError("Encodage JPEG impossible")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".jpg.tmp")
    tmp.write_bytes(buffer.tobytes())
    os.replace(tmp, dest)


def save_photo(config: Config, frame, guest_name: str = "", now: datetime | None = None) -> Path:
    """Enregistre une image BGR en JPEG et renvoie son chemin."""
    path = next_photo_path(config, guest_name, now)
    _write_jpeg(frame, path)
    log.info("Photo enregistrée : %s", path)
    return path


def save_strip(config: Config, strip, poses, guest_name: str = "",
               now: datetime | None = None) -> tuple[Path, list[Path]]:
    """Enregistre la bande photomaton et ses poses individuelles (dans le sous-dossier poses/).

    La bande est ce qui sera envoyé et affiché ; les poses sont gardées au cas où. Si une écriture échoue,
    tout ce qui vient d'être créé est supprimé : jamais de bande sans ses poses, ni de poses orphelines.
    """
    strip_path = next_photo_path(config, guest_name, now)
    created: list[Path] = []
    pose_paths: list[Path] = []
    try:
        _write_jpeg(strip, strip_path)
        created.append(strip_path)
        for index, pose in enumerate(poses, start=1):
            dest = strip_path.parent / POSES_DIR / f"{strip_path.stem}_pose{index}.jpg"
            _write_jpeg(pose, dest)
            created.append(dest)
            pose_paths.append(dest)
    except Exception:
        for path in created:
            path.unlink(missing_ok=True)
        raise
    log.info("Bande enregistrée : %s (%d poses)", strip_path, len(pose_paths))
    return strip_path, pose_paths
