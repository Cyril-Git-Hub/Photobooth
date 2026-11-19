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
    "badge_error": "#e5484d", "man": "#3988e8", "man_pressed": "#2465b8",
    "woman": "#f36da8", "woman_pressed": "#cf477f", "green": "#39a96b",
    "green_pressed": "#247a4b", "surprise": "#8b5cf6", "surprise_pressed": "#6336c9",
    "guestbook": "#ffd166", "guestbook_pressed": "#ffb347", "panel": "#201d40",
    "panel_hover": "#29264f", "panel_selected": "#302b5d", "slideshow_top": "#1a1a2e",
    "reference_border": "#ffc44d", "challenge_title": "#ffcd5f", "challenge_panel": "#12102a",
    "white": "#ffffff", "challenge_description": "#ffffff",
}


@dataclass(frozen=True)
class Theme:
    name: str
    folder: Path
    colors: dict[str, str]
    welcome_title: str
    welcome_message: str
    welcome_tagline: str
    start_button: str
    app_title: str
    guestbook_title: str
    guestbook_invitation_title: str
    guestbook_invitation: str
    screensaver_message: str
    slideshow_message: str
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
    root_manifest = config.base_dir / "theme.ini"
    theme_manifest = folder / "theme.ini"
    theme_parser = configparser.ConfigParser(interpolation=None)

    def read_manifest(target: configparser.ConfigParser, path: Path) -> None:
        try:
            if path.is_file():
                with path.open(encoding="utf-8-sig") as stream:
                    target.read_file(stream)
        except (OSError, configparser.Error, UnicodeDecodeError):
            log.exception("Fichier de thème illisible : %s", path)

    read_manifest(parser, root_manifest)
    read_manifest(theme_parser, theme_manifest)
    for section in theme_parser.sections():
        if not parser.has_section(section):
            parser.add_section(section)
        for key, value in theme_parser.items(section, raw=True):
            parser.set(section, key, value)

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

    resources = "ressources"

    def optional_image(raw: str, key: str) -> Path | None:
        if not raw:
            return None
        source_folder = folder if theme_parser.has_option(resources, key) else config.base_dir
        path = (source_folder / raw).resolve()
        try:
            path.relative_to(source_folder.resolve())
        except ValueError:
            log.warning("Ressource hors de son dossier de configuration ignorée : %s", raw)
            return None
        return path if path.is_file() else None

    screen_frame = optional_image(parser.get(resources, "cadre_interface", fallback=""), "cadre_interface")
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
        welcome_title=value("textes", "accueil_titre", "Photobooth"),
        welcome_message=value("textes", "accueil_message", "Silence, ça tourne ! À vous de jouer !"),
        welcome_tagline=value("textes", "accueil_sous_titre", "Entrez dans le décor, prenez la pose et repartez avec votre scène culte !"),
        start_button=value("textes", "bouton_commencer", "Commencer"),
        app_title=value("textes", "titre_fenetre", "Photobooth"),
        guestbook_title=value("textes", "livre_or_titre", "Livre d'or"),
        guestbook_invitation_title=value("textes", "livre_or_accroche", "🎬 À VOUS DE JOUER !"),
        guestbook_invitation=value("textes", "livre_or_message", "Laissez votre réplique !\\nPrenez la caméra, faites passer un message, racontez une anecdote ou souhaitez le meilleur. Le clap est lancé pour 15 secondes !").replace("\\n", "\n"),
        screensaver_message=value("textes", "veille_message", "Touchez pour commencer"),
        slideshow_message=value("textes", "diaporama_message", "Les photos de la soirée apparaîtront ici !"),
        mail_sender=value("mail", "nom_expediteur", "Photobooth"),
        mail_subject=value("mail", "objet", "Ta photo du photobooth est prête !"),
        mail_body=value("mail", "message", "{salutation}\\n\\nTa photo du photobooth est en pièce jointe.\\n\\nÀ très vite !").replace("\\n", "\n"),
        welcome_image=optional_image(parser.get(resources, "image_accueil", fallback=""), "image_accueil"),
        logo=optional_image(parser.get(resources, "logo", fallback=""), "logo"),
        screen_frame=screen_frame,
        backgrounds=folder / "fonds", frames=folder / "cadres", sounds=folder / "sons",
    )
