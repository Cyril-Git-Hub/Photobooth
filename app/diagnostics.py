"""Diagnostic « avant la fête » : vérifie en quelques secondes que tout est prêt (caméra, modèle, mails, écrans...).

    photobooth-outils.exe --autotest     (ou : python main.py --autotest)

Chaque contrôle renvoie [OK], [ATTENTION] (la borne marche, mais pas au mieux) ou [ECHEC] (à corriger).
Le rapport est aussi écrit dans logs/diagnostic.txt.
"""
from __future__ import annotations

import importlib
import platform
import shutil
import socket
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import __version__, paths
from .config import Config
from .core import backgrounds, guests
from .core.mailer import MailSettings
from .core.segmentation import SegmentationError, create_segmenter

OK, WARN, FAIL = "ok", "warn", "fail"
_MARKERS = {OK: "[OK]", WARN: "[ATTENTION]", FAIL: "[ECHEC]"}
MIN_FREE_GB, COMFORT_FREE_GB = 0.2, 2.0
SLOW_MS = 120

_LIBRARIES = (   # (module, nom, attribut de version)
    ("PyQt6.QtCore", "PyQt6", "PYQT_VERSION_STR"),
    ("cv2", "OpenCV", "__version__"),
    ("numpy", "NumPy", "__version__"),
    ("PIL", "Pillow", "__version__"),
    ("openpyxl", "openpyxl", "__version__"),
    ("mediapipe", "MediaPipe", "__version__"),
)


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    detail: str


# ---------------------------------------------------------------- sondes réelles (remplaçables dans les tests)

def _default_open_camera(config: Config):
    from .core import webcam
    cap = webcam.open_capture(config.camera_index, config.resolution_largeur, config.resolution_hauteur)
    if cap is None:
        return None
    try:
        import cv2
        return int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    finally:
        cap.release()


def _default_load_model(config: Config) -> float:
    """Charge le modèle, détoure une image vide et renvoie le temps moyen par image (ms). Lève SegmentationError."""
    import numpy as np
    segmenter = create_segmenter(config)
    try:
        frame = np.zeros((720, 1280, 3), np.uint8)
        segmenter.segment(frame)                           # échauffement
        start = time.perf_counter()
        for _ in range(3):
            segmenter.segment(frame)
        return 1000 * (time.perf_counter() - start) / 3
    finally:
        segmenter.close()


def _default_can_connect(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=5):
            return True
    except OSError:
        return False


@dataclass
class Probes:
    import_module: Callable = importlib.import_module
    open_camera: Callable = _default_open_camera
    load_model: Callable = _default_load_model
    can_connect: Callable = _default_can_connect
    disk_usage: Callable = shutil.disk_usage


# ---------------------------------------------------------------- contrôles

def _check_software(config: Config) -> Check:
    mode = "exécutable" if getattr(sys, "frozen", False) else "développement"
    return Check("Logiciel", OK, f"Photo Booth {__version__} ({mode}), Python {platform.python_version()}, "
                                 f"dossier {paths.app_dir()}")


def _check_libraries(config: Config, probes: Probes) -> list[Check]:
    found, missing, optional_missing = [], [], []
    for module_name, label, version_attr in _LIBRARIES:
        try:
            module = probes.import_module(module_name)
        except Exception as exc:                            # ImportError, mais aussi DLL manquante : OSError
            required = label != "MediaPipe" or config.mode_detourage == "ia"
            (missing if required else optional_missing).append(f"{label} ({type(exc).__name__}: {exc})")
            continue
        found.append(f"{label} {getattr(module, version_attr, '?')}")
    checks = []
    if missing:
        checks.append(Check("Bibliothèques", FAIL, "manquantes : " + " ; ".join(missing)))
    else:
        detail = ", ".join(found) + (f" | non utilisé(es) : {', '.join(optional_missing)}" if optional_missing else "")
        checks.append(Check("Bibliothèques", OK, detail))
    try:
        cv2 = probes.import_module("cv2")
        if not hasattr(cv2, "ximgproc"):
            checks.append(Check("OpenCV contrib", WARN, "module absent : contours du détourage moins précis "
                                                       "(installer opencv-contrib-python)"))
    except Exception:
        pass
    return checks


def _check_folders(config: Config) -> list[Check]:
    checks = []
    for label, folder in (("photos", config.dossier_photos), ("données", config.dossier_donnees),
                          ("journaux", config.dossier_logs)):
        try:
            folder.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryFile(dir=folder):
                pass
            checks.append(Check(f"Dossier {label}", OK, f"{folder} (écriture possible)"))
        except OSError as exc:
            checks.append(Check(f"Dossier {label}", FAIL, f"{folder} : écriture impossible ({exc})"))
    return checks


def _check_disk(config: Config, probes: Probes) -> Check:
    try:
        folder = config.dossier_photos if config.dossier_photos.exists() else config.dossier_photos.parent
        free_gb = probes.disk_usage(folder).free / 1e9
    except OSError as exc:
        return Check("Espace disque", WARN, f"mesure impossible ({exc})")
    if free_gb < MIN_FREE_GB:
        return Check("Espace disque", FAIL, f"{free_gb:.1f} Go libres : les photos ne pourront plus être enregistrées")
    if free_gb < COMFORT_FREE_GB:
        return Check("Espace disque", WARN, f"{free_gb:.1f} Go libres : prévois plus de place pour la soirée")
    return Check("Espace disque", OK, f"{free_gb:.1f} Go libres")


def _check_model(config: Config, probes: Probes) -> Check:
    if config.mode_detourage == "fond_vert":
        return Check("Détourage", OK, "mode fond vert : aucun modèle nécessaire")
    path = config.fichier_modele_ia
    if not path.is_file():
        return Check("Détourage", FAIL, f"modèle « {config.ia_modele} » absent ({path.name}). Lance : "
                                        "photobooth-outils.exe --telecharger-modeles")
    try:
        ms = probes.load_model(config)
    except SegmentationError as exc:
        return Check("Détourage", FAIL, str(exc.args[0]).splitlines()[0])
    except Exception as exc:
        return Check("Détourage", FAIL, f"erreur au chargement du modèle : {exc!r}")
    if ms > SLOW_MS:
        return Check("Détourage", WARN, f"modèle « {config.ia_modele} » chargé mais lent ({ms:.0f} ms par image) : "
                                        "réduis apercu_largeur dans config.ini")
    return Check("Détourage", OK, f"modèle « {config.ia_modele} » chargé ({ms:.0f} ms par image)")


def _check_backgrounds(config: Config) -> Check:
    themes = backgrounds.scan_backgrounds(config.dossier_fonds)
    count = sum(len(theme.images) for theme in themes)
    if not count:
        return Check("Décors", WARN, f"aucune image dans {config.dossier_fonds} : seul « Sans décor » fonctionnera")
    return Check("Décors", OK, f"{count} image(s) dans {len(themes)} thème(s)")


def _check_guests(config: Config) -> Check:
    path = config.fichier_invites
    if not path.exists():
        return Check("Invités", WARN, f"{path.name} absent (il sera créé vide au lancement de la borne)")
    try:
        people = guests.load_guests(path)
    except guests.GuestListError as exc:
        return Check("Invités", FAIL, str(exc.args[0]).splitlines()[0])
    if not people:
        return Check("Invités", WARN, f"{path.name} est vide : les invités devront saisir leur adresse")
    with_mail = sum(1 for person in people if person.email)
    return Check("Invités", OK, f"{len(people)} invité(s), dont {with_mail} avec une adresse mail")


def _check_mail(config: Config, probes: Probes) -> Check:
    settings = MailSettings.from_config(config)
    if not settings.configured:
        return Check("Mails", WARN, "non configuré : les photos sont enregistrées mais pas envoyées "
                                    "(section [mail] de config.ini)")
    notes = []
    if not settings.password:
        notes.append("mot de passe d'application vide")
    if not config.adresse_organisateur:
        notes.append("adresse_organisateur vide : tu ne recevras pas de copie")
    if not probes.can_connect(settings.host, settings.port):
        return Check("Mails", WARN, f"serveur {settings.host}:{settings.port} injoignable (pas d'internet ?) : "
                                    "les envois attendront le retour du réseau")
    detail = f"serveur {settings.host}:{settings.port} joignable ; vérifie les identifiants avec --test-mail"
    return Check("Mails", WARN if notes else OK, detail + (" | " + " ; ".join(notes) if notes else ""))


def _check_screens(config: Config, screen_count: int | None) -> Check | None:
    if screen_count is None:
        return None
    if not config.second_ecran_active:
        return Check("Écrans", OK, f"{screen_count} écran(s) ; diaporama désactivé (second_ecran_active = false)")
    if screen_count >= 2:
        return Check("Écrans", OK, f"{screen_count} écrans : le diaporama s'affichera sur le second")
    return Check("Écrans", WARN, "un seul écran : pas de diaporama (branche un écran et choisis « Étendre » avec Windows + P)")


def _check_camera(config: Config, probes: Probes) -> Check:
    try:
        size = probes.open_camera(config)
    except Exception as exc:
        return Check("Caméra", FAIL, f"erreur à l'ouverture : {exc!r}")
    if size is None:
        return Check("Caméra", FAIL, f"caméra {config.camera_index} introuvable ou occupée par un autre logiciel "
                                     "(Teams, Zoom, application Caméra de Windows...)")
    return Check("Caméra", OK, f"image {size[0]}x{size[1]}")


def run_checks(config: Config, screen_count: int | None = None, probes: Probes | None = None) -> list[Check]:
    probes = probes or Probes()
    checks: list[Check] = [_check_software(config), Check("Configuration", OK, str(config.config_path))]
    checks += _check_libraries(config, probes)
    checks += _check_folders(config)
    checks += [_check_disk(config, probes), _check_camera(config, probes), _check_model(config, probes),
               _check_backgrounds(config), _check_guests(config), _check_mail(config, probes)]
    screens = _check_screens(config, screen_count)
    if screens is not None:
        checks.append(screens)
    return checks


def format_report(checks: list[Check]) -> str:
    lines = [f"{_MARKERS[c.status]:<12} {c.name} : {c.detail}" for c in checks]
    failures = sum(1 for c in checks if c.status == FAIL)
    warnings = sum(1 for c in checks if c.status == WARN)
    if failures:
        summary = f"{failures} problème(s) à corriger avant la fête."
    elif warnings:
        summary = f"La borne peut démarrer ; {warnings} point(s) d'attention ci-dessus."
    else:
        summary = "Tout est prêt."
    return "\n".join(["Diagnostic Photo Booth", "", *lines, "", summary])


def exit_code(checks: list[Check]) -> int:
    return 1 if any(c.status == FAIL for c in checks) else 0


def run(config: Config, screen_count: int | None = None, probes: Probes | None = None) -> tuple[str, int]:
    """Lance tous les contrôles, écrit logs/diagnostic.txt et renvoie (rapport, code de sortie)."""
    checks = run_checks(config, screen_count, probes)
    report = format_report(checks)
    try:
        config.dossier_logs.mkdir(parents=True, exist_ok=True)
        (config.dossier_logs / "diagnostic.txt").write_text(report + "\n", encoding="utf-8")
    except OSError:
        pass
    return report, exit_code(checks)
