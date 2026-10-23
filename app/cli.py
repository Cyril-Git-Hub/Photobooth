"""Commandes en ligne : test d'envoi de mail, téléchargement des modèles, version.

Elles tournent sans Python grâce à photobooth-outils.exe (même programme que la borne, avec une console).
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
import urllib.request
from pathlib import Path

import cv2
import numpy as np

from . import __version__
from .config import Config
from .core.emails import is_valid_email, normalize_email
from .core.mail_queue import GUEST, MailJob
from .core.mailer import MailSettings, NetworkError, PermanentMailError, SmtpSender, TemporaryMailError
from .core.models import DEFAULT_DOWNLOADS, MODEL_NAMES, MODELS

MIN_MODEL_SIZE = 20_000  # un fichier plus petit est forcément une page d'erreur, pas un modèle


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="photobooth", description="Photobooth")
    parser.add_argument("--windowed", action="store_true", help="fenêtre normale au lieu du plein écran (développement)")
    parser.add_argument("--diaporama-fenetre", action="store_true",
                        help="affiche le diaporama dans une fenêtre ordinaire (pour le voir sans second écran)")
    parser.add_argument("--config", type=Path, default=None, help="chemin d'un config.ini alternatif")
    parser.add_argument("--version", action="store_true", help="affiche la version et quitte")
    parser.add_argument("--autotest", action="store_true",
                        help="vérifie caméra, modèle, décors, invités, mail, écrans... et écrit logs/diagnostic.txt")
    parser.add_argument("--test-mail", nargs="?", const="", default=None, metavar="ADRESSE",
                        help="envoie un mail de test (à adresse_organisateur, ou à ADRESSE)")
    parser.add_argument("--configurer-drive", action="store_true",
                        help="connecte Google Drive et programme le retrait automatique des liens expirés")
    parser.add_argument("--cleanup-drive-links", action="store_true",
                        help=argparse.SUPPRESS)
    parser.add_argument("--telecharger-modeles", nargs="*", default=None, metavar="MODELE",
                        help=f"télécharge les modèles de détourage ({', '.join(MODEL_NAMES)} ; par défaut {' + '.join(DEFAULT_DOWNLOADS)})")
    parser.add_argument("--tous", action="store_true", help="avec --telecharger-modeles : les télécharge tous")
    parser.add_argument("--force", action="store_true", help="avec --telecharger-modeles : retélécharge même si présents")
    return parser


def run_tools(args: argparse.Namespace) -> int | None:
    """Exécute une commande sans interface. Renvoie son code de sortie, ou None s'il faut lancer la borne."""
    if args.version:
        print(f"Photobooth {__version__}")
        return 0
    if args.telecharger_modeles is not None:
        extra = (["--tous"] if args.tous else []) + (["--force"] if args.force else [])
        return download_models(list(args.telecharger_modeles) + extra)
    if args.test_mail is not None:
        return test_mail([args.test_mail] if args.test_mail else [])
    if args.configurer_drive:
        from .core.drive_sharing import authorize_google_drive, register_cleanup_task
        config = Config.load(args.config)
        config.ensure_directories()
        try:
            authorize_google_drive(config.base_dir)
        except Exception as exc:
            print(f"Connexion Google Drive impossible : {exc}")
            return 1
        print("Google Drive est connecté. Le jeton OAuth est conservé dans le dossier local data/.")
        if register_cleanup_task(config.base_dir, config.config_path):
            print("Le nettoyage automatique des liens expirés est programmé toutes les heures.")
        else:
            print("La tâche Windows n'a pas pu être créée ; le nettoyage sera tenté au prochain démarrage.")
        return 0
    if args.cleanup_drive_links:
        from .core.drive_sharing import DriveShareService
        config = Config.load(args.config)
        try:
            revoked, failed = DriveShareService(config.base_dir).revoke_expired()
        except Exception as exc:
            print(f"Nettoyage Google Drive impossible : {exc}")
            return 1
        print(f"Nettoyage terminé : {revoked} lien(s) révoqué(s), {failed} à réessayer.")
        return 1 if failed else 0
    return None


# ---------------------------------------------------------------- test d'envoi de mail

def _sample_photo(folder: Path) -> Path:
    image = np.zeros((360, 640, 3), np.uint8)
    image[:, :, 0] = np.linspace(40, 220, 640, dtype=np.uint8)[None, :]
    image[:, :, 2] = np.linspace(220, 40, 640, dtype=np.uint8)[None, :]
    cv2.putText(image, "TEST Photobooth", (60, 195), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 3, cv2.LINE_AA)
    path = folder / "test.jpg"
    ok, buffer = cv2.imencode(".jpg", image)
    path.write_bytes(buffer.tobytes())
    return path


def test_mail(argv: list[str] | None = None, sender_factory=SmtpSender) -> int:
    """Envoie une photo de test avec les réglages de [mail] ; affiche la cause précise en cas d'échec."""
    args = argv or []
    config = Config.load()
    settings = MailSettings.from_config(config)
    recipient = normalize_email(args[0] if args else config.adresse_organisateur)

    print(f"Serveur : {settings.host}:{settings.port} (sécurité {settings.resolved_security()})")
    print(f"Expéditeur : {settings.sender or '(vide)'} | identifiant : {settings.user or '(vide)'} | "
          f"mot de passe : {'renseigné' if settings.password else '(vide)'}")
    if not settings.configured:
        print("\nIl manque l'adresse expéditeur ou le serveur : renseigne la section [mail] de config.ini.")
        return 2
    if not is_valid_email(recipient):
        print(f"\nAdresse de destination invalide ou absente : {recipient!r}\n"
              "Donne-la en argument, ou renseigne adresse_organisateur dans config.ini.")
        return 2

    with tempfile.TemporaryDirectory() as tmp:
        job = MailJob(0, GUEST, recipient, "Test", "", "", _sample_photo(Path(tmp)), 0)
        print(f"\nEnvoi d'un mail de test à {recipient}…")
        try:
            sender_factory(settings).send(job)
        except PermanentMailError as exc:
            print(f"\nÉCHEC (à corriger dans config.ini) : {exc}")
            return 1
        except NetworkError as exc:
            print(f"\nÉCHEC (réseau) : {exc}\nVérifie ta connexion internet, le serveur et le port.")
            return 1
        except TemporaryMailError as exc:
            print(f"\nÉCHEC provisoire : {exc}\nRéessaie dans un instant.")
            return 1
    print(f"\nOK : mail envoyé à {recipient}. Vérifie sa réception (et le dossier spam).")
    return 0


# ---------------------------------------------------------------- téléchargement des modèles

def _download_one(name: str, folder: Path, force: bool) -> bool:
    spec = MODELS[name]
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


def download_models(argv: list[str] | None = None) -> int:
    """Télécharge les modèles dans le dossier `dossier_modeles` de config.ini (models/ par défaut)."""
    args = argv or []
    names = [a for a in args if not a.startswith("--")]
    unknown = [n for n in names if n not in MODEL_NAMES]
    if unknown:
        print(f"Modèle inconnu : {', '.join(unknown)}. Choix possibles : {', '.join(MODEL_NAMES)}")
        return 2
    selected = list(MODEL_NAMES) if "--tous" in args else (names or list(DEFAULT_DOWNLOADS))
    folder = Config.load().dossier_modeles
    return 0 if all([_download_one(name, folder, "--force" in args) for name in selected]) else 1
