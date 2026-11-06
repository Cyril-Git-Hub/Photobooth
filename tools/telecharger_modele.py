r"""Télécharge les modèles de détourage et d'accessoires photo (une seule fois, internet requis).

    python tools\telecharger_modele.py                 # paysage + carre (petits fichiers)
    python tools\telecharger_modele.py multiclasse     # un modèle précis, par son nom
    python tools\telecharger_modele.py pose            # requis pour le défi du sabre laser
    python tools\telecharger_modele.py --tous          # les quatre modèles disponibles
    python tools\telecharger_modele.py --force         # retélécharge même si déjà présents

Sans Python (PC de la fête) : photobooth-outils.exe --telecharger-modeles
"""
from __future__ import annotations

import configparser
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.core.model_downloads import download_models  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    base_dir = Path(__file__).resolve().parent.parent
    config = configparser.ConfigParser(interpolation=None)
    config_path = base_dir / "config.ini"
    if config_path.is_file():
        try:
            with config_path.open(encoding="utf-8-sig") as stream:
                config.read_file(stream)
        except (OSError, configparser.Error, UnicodeDecodeError) as exc:
            print(f"Configuration illisible ({exc}) ; le dossier models/ sera utilisé.")
    model_dir = Path(config.get("chemins", "dossier_modeles", fallback="models")).expanduser()
    if not model_dir.is_absolute():
        model_dir = (base_dir / model_dir).resolve()
    return download_models(argv, model_dir)

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
