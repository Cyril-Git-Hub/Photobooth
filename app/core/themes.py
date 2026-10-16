"""Chargement des thèmes utilisateur (couleurs, textes et ressources optionnelles)."""
from __future__ import annotations

import configparser
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtGui import QImageReader

from ..config import Config

log = logging.getLogger(__name__)
_COLOR = re.compile(r"#[0-9a-fA-F]{6}\Z")
_DEFAULT_COLORS = {
    "background": "#14122b", "text": "#f4f1ff", "accent": "#ffd166", "muted": "#b8b2d9",
    "summary": "#8f89b5", "primary": "#ff4d8d", "primary_pressed": "#d93a75",
    "secondary": "#2b2757", "secondary_pressed": "#3b3680", "mail_background": "#0b0a1a",
    "error": "#ff6b6b", "warning": "#ffb347", "danger": "#b3261e", "danger_pressed": "#8c1d18",
    "badge_error": "#e5484d",
}


@dataclass(frozen=True)
class Theme:
    name: str
    folder: Path
    colors: dict[str, str]
    welcome_title: str
    welcome_message: str
    start_button: str
    app_title: str
    mail_sender: str
    mail_subject: str
    mail_body: str
    welcome_image: Path | None
    logo: Path | None
    screen_frame: Path | None
    backgrounds: Path
    frames: Path
    sounds: Path


def load_theme(config: Config) -> Theme:
    """Charge le thème sélectionné ; les champs invalides retombent sur l'apparence actuelle."""
    folder = config.dossier_theme
    parser = configparser.ConfigParser(interpolation=None)
    manifest = folder / "theme.ini"
    try:
        if manifest.is_file():
            with manifest.open(encoding="utf-8-sig") as stream:
                parser.read_file(stream)
    except (OSError, configparser.Error, UnicodeDecodeError):
        log.exception("Manifeste de thème illisible : %s ; thème classique utilisé", manifest)
        folder = config.dossier_themes / "classique"
        parser = configparser.ConfigParser(interpolation=None)
        try:
            with (folder / "theme.ini").open(encoding="utf-8-sig") as stream:
                parser.read_file(stream)
        except (OSError, configparser.Error, UnicodeDecodeError):
            parser = configparser.ConfigParser(interpolation=None)

    colors = dict(_DEFAULT_COLORS)
    if parser.has_section("couleurs"):
        for key in colors:
            value = parser.get("couleurs", key, fallback=colors[key]).strip()
            if _COLOR.fullmatch(value):
                colors[key] = value.lower()
            else:
                log.warning("Thème %s : couleur %s invalide (%r), valeur classique utilisée", config.theme, key, value)

    def value(section: str, key: str, default: str) -> str:
        result = parser.get(section, key, fallback=default).strip()
        return result or default

    def optional_image(raw: str) -> Path | None:
        if not raw:
            return None
        path = (folder / raw).resolve()
        try:
            path.relative_to(folder.resolve())
        except ValueError:
            log.warning("Ressource de thème hors de son dossier ignorée : %s", raw)
            return None
        return path if path.is_file() else None

    resources = "ressources"
    screen_frame = optional_image(parser.get(resources, "cadre_interface", fallback=""))
    if screen_frame is not None:
        if screen_frame.suffix.casefold() not in {".png", ".webp"}:
            log.warning("Cadre d'interface ignoré (PNG/WebP transparent attendu) : %s", screen_frame)
            screen_frame = None
        else:
            image = QImageReader(str(screen_frame)).read()
            center_is_opaque = (not image.isNull()
                                and image.pixelColor(image.width() // 2, image.height() // 2).alpha() == 255)
            if image.isNull() or not image.hasAlphaChannel() or center_is_opaque:
                log.warning("Cadre d'interface ignoré (image illisible ou sans transparence) : %s", screen_frame)
                screen_frame = None
    return Theme(
        name=value("theme", "nom", config.theme), folder=folder, colors=colors,
        welcome_title=value("textes", "accueil_titre", "Photo Booth"),
        welcome_message=value("textes", "accueil_message", "Prêt à créer un souvenir ?"),
        start_button=value("textes", "bouton_commencer", "Commencer"),
        app_title=value("textes", "titre_fenetre", "Photo Booth"),
        mail_sender=value("mail", "nom_expediteur", "Photo Booth"),
        mail_subject=value("mail", "objet", "Ta photo du photobooth est prête !"),
        mail_body=value("mail", "message", "{salutation}\\n\\nTa photo du photobooth est en pièce jointe.\\n\\nÀ très vite !").replace("\\n", "\n"),
        welcome_image=optional_image(parser.get(resources, "image_accueil", fallback="")),
        logo=optional_image(parser.get(resources, "logo", fallback="")),
        screen_frame=screen_frame,
        backgrounds=folder / "fonds", frames=folder / "cadres", sounds=folder / "sons",
    )
