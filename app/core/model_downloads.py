"""Téléchargement des modèles sans dépendances de l'interface ni d'OpenCV."""
from __future__ import annotations

import os
import shutil
import urllib.request
from pathlib import Path

from .models import DEFAULT_DOWNLOADS, DOWNLOAD_MODELS

MIN_MODEL_SIZE = 20_000


def _download_one(name: str, folder: Path, force: bool) -> bool:
    spec = DOWNLOAD_MODELS[name]
    dest = folder / spec.filename
    if dest.exists() and not force:
        print(f"[{name}] déjà présent : {dest.name}")
        return True
    folder.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    print(f"[{name}] téléchargement ({spec.description})…")
    try:
        with urllib.request.urlopen(spec.url, timeout=60) as response, open(tmp, "wb") as out:
            shutil.copyfileobj(response, out)
    except OSError as exc:
        print(f"[{name}] échec : {exc}\nVérifie ta connexion internet (ou ton proxy / pare-feu).")
        tmp.unlink(missing_ok=True)
        return False
    if tmp.stat().st_size < MIN_MODEL_SIZE:
        print(f"[{name}] le fichier téléchargé est trop petit : ce n'est pas le modèle attendu.")
        tmp.unlink(missing_ok=True)
        return False
    os.replace(tmp, dest)
    print(f"[{name}] OK : {dest.name} ({dest.stat().st_size // 1024} Ko)")
    return True


def download_models(argv: list[str] | None, folder: Path) -> int:
    """Télécharge les modèles choisis dans le dossier fourni."""
    args = argv or []
    names = [arg for arg in args if not arg.startswith("--")]
    unknown = [name for name in names if name not in DOWNLOAD_MODELS]
    if unknown:
        print(f"Modèle inconnu : {', '.join(unknown)}. Choix possibles : {', '.join(DOWNLOAD_MODELS)}")
        return 2
    selected = list(DOWNLOAD_MODELS) if "--tous" in args else (names or list(DEFAULT_DOWNLOADS))
    results = [_download_one(name, folder, "--force" in args) for name in selected]
    return 0 if all(results) else 1
