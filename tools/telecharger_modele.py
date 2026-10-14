r"""Télécharge les modèles de détourage IA (une seule fois, internet requis).

    python tools\telecharger_modele.py                 # paysage + carre (petits fichiers)
    python tools\telecharger_modele.py multiclasse     # un modèle précis, par son nom
    python tools\telecharger_modele.py --tous          # les trois
    python tools\telecharger_modele.py --force         # retélécharge même si déjà présents

Sans Python (PC de la fête) : photobooth-outils.exe --telecharger-modeles
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.cli import download_models as main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
