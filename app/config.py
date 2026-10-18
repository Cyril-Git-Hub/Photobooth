"""Lecture / écriture de config.ini, avec valeurs par défaut et validation.

Une valeur invalide ne fait jamais planter le logiciel : elle est signalée dans
les logs et remplacée par la valeur par défaut.
"""
from __future__ import annotations

import configparser
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

from . import paths
from .ui.scale import MAX_MANUAL, MIN_MANUAL
from .core.mail_defaults import (
    DEFAULT_BODY, DEFAULT_SENDER_NAME, DEFAULT_SUBJECT, escape_newlines, unescape_newlines,
)
from .core.models import MODEL_NAMES, MODELS

log = logging.getLogger(__name__)

DETOURAGE_MODES = ("ia", "fond_vert")
MAIL_SECURITIES = ("auto", "starttls", "ssl", "aucune")
DIAPORAMA_ORDERS = ("chronologique", "aleatoire")
THEMES_PAR_DEFAUT = ("films", "series", "dessins animés", "animes japonais")

DEFAULTS: dict[str, dict[str, str]] = {
    "general": {
        "mode_detourage": "ia",
        "nb_poses": "4",
        "duree_decompte": "3",
        "camera_index": "0",
        "resolution_largeur": "1920",
        "resolution_hauteur": "1080",
        "son_active": "true",
        "son_volume": "70",
        "second_ecran_active": "true",
        "plein_ecran": "true",
        "miroir": "true",
        "apercu_incruste": "true",
        "apercu_largeur": "960",
        "ia_modele": "paysage",
        "ia_inverser_masque": "false",
        "inactivite_secondes": "60",
        "code_admin": "1234",
        "indicateur_organisateur": "true",
        "echelle_interface": "auto",
        "theme": "classique",
    },
    "chemins": {
        "dossier_photos": "photos",
        "fichier_invites": "invites.xlsx",
        "dossier_fonds": "fonds",
        "dossier_cadres": "cadres",
        "dossier_modeles": "models",
    },
    "sauvegarde": {
        "actif": "true",
        "dossier": "",
    },
    "diaporama": {
        "duree": "6",
        "ordre": "chronologique",
    },
    "photomaton": {
        "decompte_entre_poses": "2",
        "titre": "",
        "couleur_fond": "#ffffff",
        "couleur_texte": "#1c1c1c",
    },
    "gif": {
        "actif": "true",
        "limite_mo": "8",
        "poses_espacees": "5",
        "poses_rafale": "8",
        "intervalle_rafale_ms": "180",
        "duree_image_ms": "350",
        "pause_derniere_image_ms": "1200",
    },
    "qr_drive": {
        "actif": "false",
    },
    "livre_or": {
        "actif": "false",
    },
    "defis": {
        "actif": "true",
    },
    "fond_vert": {
        "teinte_min": "35",
        "teinte_max": "85",
        "saturation_min": "70",
        "valeur_min": "40",
        "adoucissement": "2",
        "despill": "true",
    },
    "mail": {
        "actif": "true",
        "smtp_hote": "smtp.gmail.com",
        "smtp_port": "587",
        "expediteur": "",
        "mot_de_passe_application": "",
        "adresse_organisateur": "",
        "obligatoire": "false",
        "utilisateur": "",
        "securite": "auto",
        "nom_expediteur": DEFAULT_SENDER_NAME,
        "objet": DEFAULT_SUBJECT,
        "message": escape_newlines(DEFAULT_BODY),
    },
}

# Fichier généré si config.ini est absent (avec des commentaires, contrairement à configparser).
TEMPLATE = """\
# Configuration du Photo Booth.
# Les chemins relatifs sont interprétés par rapport au dossier du logiciel.
# Après modification : relancer le logiciel (ou « Recharger la configuration » en mode admin).

[general]
# Détourage des invités : ia (par défaut, sans fond vert) ou fond_vert
mode_detourage = ia
# Nombre de poses en mode photomaton (1 à 6)
nb_poses = 4
# Durée du décompte avant chaque photo, en secondes
duree_decompte = 3
# Index de la caméra (0 = première caméra)
camera_index = 0
resolution_largeur = 1920
resolution_hauteur = 1080
son_active = true
# Volume des effets sonores (0 à 100)
son_volume = 70
second_ecran_active = true
plein_ecran = true
# Image en miroir (comme devant une glace). S'applique à l'aperçu ET à la photo finale :
# la photo est exactement ce que l'invité a vu, donc bien placée par rapport au décor.
# Attention : en miroir, les textes sur les vêtements apparaissent inversés. false = ni aperçu ni photo en miroir.
miroir = true
# Aperçu en direct avec le décor. false = aperçu brut, le décor n'est appliqué qu'à la photo (si l'ordinateur est lent)
apercu_incruste = true
# Largeur de l'image d'aperçu, en pixels (320 à 1920). Plus petit = plus fluide ; la photo finale reste en pleine résolution
apercu_largeur = 960
# Modèle de détourage IA : paysage (léger, 16/9, conseillé), carre ou multiclasse (plus précis, plus lent)
ia_modele = paysage
# Mettre true si le détourage IA est inversé (la personne disparaît, le fond reste)
ia_inverser_masque = false
# Écran de veille après N secondes d'inactivité ; dans le parcours, revient aussi à l'accueil (0 = désactivé)
inactivite_secondes = 60
# Code du mode administrateur (à changer !)
code_admin = 1234
# Petit voyant en haut à droite de la borne quand les mails sont hors-ligne, en attente ou en échec (jamais en temps normal)
indicateur_organisateur = true
# Taille de l'interface : auto (adaptée à l'écran) ou un nombre entre 0.4 et 2.0 (1.0 = écran 1920x1080, 0.7 = plus petit).
# Si des boutons du bas sont coupés, essaie 0.7. Ne prend effet qu'au prochain lancement de la borne.
echelle_interface = auto
# Thème visuel chargé depuis themes/<nom>/theme.ini
theme = classique

[chemins]
dossier_photos = photos
# Liste d'invités au format .xlsx, .xls ou .ods
fichier_invites = invites.xlsx
dossier_fonds = fonds
# Dossier des cadres PNG/WebP transparents pour les photos uniques sans décor
dossier_cadres = cadres
# Dossier des modèles de détourage IA (téléchargés par tools/telecharger_modele.py)
dossier_modeles = models

[sauvegarde]
# Activer la copie automatique (nécessite un dossier configuré ci-dessous)
actif = true
# Dossier où recopier automatiquement chaque photo validée : clé USB, disque externe, dossier synchronisé...
# Laisser vide pour désactiver. Exemple : E:/sauvegarde-photos
dossier =

[diaporama]
# Diaporama sur le second écran (à activer ou non avec second_ecran_active dans [general])
# Durée d'affichage de chaque photo, en secondes (2 à 60)
duree = 6
# Ordre : chronologique ou aleatoire. Dans les deux cas, une nouvelle photo s'affiche tout de suite
ordre = chronologique

[photomaton]
# Mode photomaton : bande verticale de nb_poses photos (réglage nb_poses dans [general])
# Décompte avant les poses suivantes, en secondes (le décompte de la première pose est duree_decompte)
decompte_entre_poses = 2
# Titre imprimé en bas de la bande (laisser vide pour n'afficher que la date)
titre =
# Couleurs de la bande, au format #rrggbb
couleur_fond = #ffffff
couleur_texte = #1c1c1c

[gif]
# Proposer le format GIF animé dans le parcours
actif = true
# Taille maximale du fichier final (en Mo)
limite_mo = 8
# Nombre d'images en mode poses espacées / rafale courte
poses_espacees = 5
poses_rafale = 8
# Intervalle entre les images d'une rafale (en millisecondes)
intervalle_rafale_ms = 180
# Durée d'affichage normale de chaque image (en millisecondes)
duree_image_ms = 350
# Durée de la dernière image si l'option est activée
pause_derniere_image_ms = 1200

[qr_drive]
# Partage des photos/GIF par QR code (demande une configuration OAuth Google Drive)
actif = false

[livre_or]
# Proposer un message vidéo avec son après une photo, pour la soirée active
actif = false

[defis]
# Proposer le bouton « Défi surprise » dans le parcours
actif = true

[fond_vert]
# Réglages du mode fond_vert (teinte de 0 à 179 : le vert est autour de 60)
teinte_min = 35
teinte_max = 85
# Plus la saturation / luminosité minimales sont basses, plus le vert pâle ou sombre est retiré
saturation_min = 70
valeur_min = 40
# Adoucissement des contours (0 à 10) et suppression du halo vert sur les bords
adoucissement = 2
despill = true

[mail]
actif = true
smtp_hote = smtp.gmail.com
smtp_port = 587
expediteur =
# Mot de passe d'application Gmail (ne partagez pas ce fichier)
mot_de_passe_application =
# Adresse qui reçoit une copie de chaque photo
adresse_organisateur =
# true : l'invité doit donner son adresse mail ; false : un bouton « Passer » est proposé
obligatoire = false
# Identifiant de connexion au serveur (laisser vide pour utiliser l'adresse de l'expéditeur)
utilisateur =
# Sécurité de la connexion : auto (port 465 = ssl, sinon starttls), starttls, ssl ou aucune
securite = auto
# Nom affiché comme expéditeur
nom_expediteur = @@SENDER@@
# Objet et texte du mail envoyé à l'invité. Variables : {prenom} {nom} {salutation} {titre} {date}
# Écris @@NL@@ pour un retour à la ligne
objet = @@SUBJECT@@
message = @@BODY@@
"""
TEMPLATE = (TEMPLATE.replace("@@NL@@", "\\n").replace("@@SENDER@@", DEFAULT_SENDER_NAME)
            .replace("@@SUBJECT@@", DEFAULT_SUBJECT).replace("@@BODY@@", escape_newlines(DEFAULT_BODY)))


@dataclass
class Config:
    base_dir: Path
    config_path: Path
    # [general]
    mode_detourage: str = "ia"
    nb_poses: int = 4
    duree_decompte: int = 3
    camera_index: int = 0
    resolution_largeur: int = 1920
    resolution_hauteur: int = 1080
    son_active: bool = True
    son_volume: int = 70
    second_ecran_active: bool = True
    plein_ecran: bool = True
    miroir: bool = True
    apercu_incruste: bool = True
    apercu_largeur: int = 960
    ia_modele: str = "paysage"
    ia_inverser_masque: bool = False
    inactivite_secondes: int = 60
    code_admin: str = "1234"
    indicateur_organisateur: bool = True
    echelle_interface: float | None = None      # None : automatique
    theme: str = "classique"
    active_theme: object | None = None
    # [chemins]
    dossier_photos: Path = Path("photos")
    fichier_invites: Path = Path("invites.xlsx")
    dossier_fonds: Path = Path("fonds")
    dossier_cadres: Path = Path("cadres")
    dossier_modeles: Path = Path("models")
    # [photomaton]
    pm_decompte_entre_poses: int = 2
    pm_titre: str = ""
    pm_couleur_fond: str = "#ffffff"
    pm_couleur_texte: str = "#1c1c1c"
    # [gif]
    gif_actif: bool = True
    gif_limite_mo: int = 8
    gif_poses_espacees: int = 5
    gif_poses_rafale: int = 8
    gif_intervalle_rafale_ms: int = 180
    gif_duree_image_ms: int = 350
    gif_pause_derniere_image_ms: int = 1200
    qr_drive_actif: bool = False
    livre_or_actif: bool = False
    defis_actifs: bool = True
    # [sauvegarde]
    sauvegarde_active: bool = True
    dossier_sauvegarde: Path | None = None
    # [diaporama]
    dp_duree: int = 6
    dp_ordre: str = "chronologique"
    # [fond_vert]
    fv_teinte_min: int = 35
    fv_teinte_max: int = 85
    fv_saturation_min: int = 70
    fv_valeur_min: int = 40
    fv_adoucissement: int = 2
    fv_despill: bool = True
    # [mail]
    mail_actif: bool = True
    smtp_hote: str = "smtp.gmail.com"
    smtp_port: int = 587
    expediteur: str = ""
    mot_de_passe_application: str = ""
    adresse_organisateur: str = ""
    mail_obligatoire: bool = False
    mail_utilisateur: str = ""
    mail_securite: str = "auto"
    mail_nom_expediteur: str = DEFAULT_SENDER_NAME
    mail_objet: str = DEFAULT_SUBJECT
    mail_message: str = DEFAULT_BODY

    @property
    def dossier_logs(self) -> Path:
        return self.base_dir / "logs"

    @property
    def dossier_themes(self) -> Path:
        return self.base_dir / "themes"

    @property
    def dossier_theme(self) -> Path:
        name = self.theme if re.fullmatch(r"[A-Za-z0-9_-]+", self.theme) else "classique"
        return self.dossier_themes / name

    @property
    def dossier_masques(self) -> Path:
        return self.base_dir / "masques"

    @property
    def dossier_donnees(self) -> Path:
        return self.base_dir / "data"

    @property
    def fichier_envois(self) -> Path:
        """File d'attente des mails (SQLite)."""
        return self.dossier_donnees / "envois.sqlite3"

    @property
    def dossier_exports(self) -> Path:
        """Exports de secours des envois non partis."""
        return self.base_dir / "exports"

    @property
    def dossier_livre_or(self) -> Path:
        """Messages vidéo conservés localement par soirée."""
        return self.base_dir / "livre-or"

    @property
    def fichier_diaporama(self) -> Path:
        """Journal des photos validées, pour le diaporama."""
        return self.dossier_donnees / "diaporama.jsonl"

    @property
    def fichier_modele_ia(self) -> Path:
        """Fichier du modèle choisi par `ia_modele`."""
        return self.dossier_modeles / MODELS[self.ia_modele].filename

    @classmethod
    def load(cls, config_path: Path | None = None, base_dir: Path | None = None) -> "Config":
        base = (base_dir or paths.app_dir()).resolve()
        path = Path(config_path) if config_path else base / "config.ini"

        if not path.exists():
            log.warning("config.ini introuvable, création avec les valeurs par défaut : %s", path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(TEMPLATE, encoding="utf-8")

        parser = cls._new_parser()
        try:
            # utf-8-sig : tolère le BOM ajouté par le Bloc-notes de Windows
            with path.open(encoding="utf-8-sig") as f:
                parser.read_file(f)
        except (configparser.Error, OSError, UnicodeDecodeError) as exc:
            log.error("config.ini illisible (%s) : valeurs par défaut utilisées", exc)
            parser = cls._new_parser()

        def get_int(section: str, key: str, minimum: int, maximum: int) -> int:
            try:
                value = parser.getint(section, key)
            except ValueError:
                value = None
            if value is None or not (minimum <= value <= maximum):
                default = int(DEFAULTS[section][key])
                log.warning("[%s] %s invalide (%r) : valeur par défaut %s",
                            section, key, parser.get(section, key), default)
                return default
            return value

        def get_bool(section: str, key: str) -> bool:
            try:
                return parser.getboolean(section, key)
            except ValueError:
                default = DEFAULTS[section][key].lower() == "true"
                log.warning("[%s] %s invalide (%r) : valeur par défaut %s",
                            section, key, parser.get(section, key), default)
                return default

        def get_str(section: str, key: str) -> str:
            return parser.get(section, key).strip()

        def get_color(section: str, key: str) -> str:
            value = get_str(section, key)
            if re.fullmatch(r"#[0-9a-fA-F]{6}", value):
                return value.lower()
            log.warning("[%s] %s invalide (%r, format attendu #rrggbb) : valeur par défaut %s",
                        section, key, value, DEFAULTS[section][key])
            return DEFAULTS[section][key]

        def get_path(section: str, key: str) -> Path:
            return paths.resolve(get_str(section, key) or DEFAULTS[section][key], base)

        mode = get_str("general", "mode_detourage").lower()
        if mode not in DETOURAGE_MODES:
            log.warning("[general] mode_detourage invalide (%r) : valeur par défaut ia", mode)
            mode = "ia"

        echelle: float | None = None
        raw_scale = get_str("general", "echelle_interface").lower()
        if raw_scale not in ("", "auto"):
            try:
                echelle = float(raw_scale.replace(",", "."))
            except ValueError:
                echelle = None
            if echelle is None or not (MIN_MANUAL <= echelle <= MAX_MANUAL):
                log.warning("[general] echelle_interface invalide (%r) : automatique", raw_scale)
                echelle = None
        theme_name = get_str("general", "theme")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", theme_name):
            log.warning("[general] theme invalide (%r) : thème classique utilisé", theme_name)
            theme_name = "classique"
        ia_modele = get_str("general", "ia_modele").lower()
        if ia_modele not in MODEL_NAMES:
            log.warning("[general] ia_modele invalide (%r) : valeur par défaut %s", ia_modele, DEFAULTS["general"]["ia_modele"])
            ia_modele = DEFAULTS["general"]["ia_modele"]
        securite = get_str("mail", "securite").lower()
        if securite not in MAIL_SECURITIES:
            log.warning("[mail] securite invalide (%r) : valeur par défaut auto", securite)
            securite = "auto"
        ordre = get_str("diaporama", "ordre").lower()
        if ordre not in DIAPORAMA_ORDERS:
            log.warning("[diaporama] ordre invalide (%r) : valeur par défaut chronologique", ordre)
            ordre = "chronologique"
        teinte_min = get_int("fond_vert", "teinte_min", 0, 179)
        teinte_max = get_int("fond_vert", "teinte_max", 0, 179)
        if teinte_min > teinte_max:
            log.warning("[fond_vert] teinte_min > teinte_max : valeurs par défaut")
            teinte_min, teinte_max = int(DEFAULTS["fond_vert"]["teinte_min"]), int(DEFAULTS["fond_vert"]["teinte_max"])

        return cls(
            base_dir=base,
            config_path=path,
            mode_detourage=mode,
            nb_poses=get_int("general", "nb_poses", 1, 6),
            duree_decompte=get_int("general", "duree_decompte", 1, 10),
            camera_index=get_int("general", "camera_index", 0, 20),
            resolution_largeur=get_int("general", "resolution_largeur", 320, 7680),
            resolution_hauteur=get_int("general", "resolution_hauteur", 240, 4320),
            son_active=get_bool("general", "son_active"),
            son_volume=get_int("general", "son_volume", 0, 100),
            second_ecran_active=get_bool("general", "second_ecran_active"),
            plein_ecran=get_bool("general", "plein_ecran"),
            miroir=get_bool("general", "miroir"),
            apercu_incruste=get_bool("general", "apercu_incruste"),
            apercu_largeur=get_int("general", "apercu_largeur", 320, 1920),
            ia_modele=ia_modele,
            ia_inverser_masque=get_bool("general", "ia_inverser_masque"),
            inactivite_secondes=get_int("general", "inactivite_secondes", 0, 3600),
            code_admin=get_str("general", "code_admin") or DEFAULTS["general"]["code_admin"],
            indicateur_organisateur=get_bool("general", "indicateur_organisateur"),
            echelle_interface=echelle,
            theme=theme_name or "classique",
            dossier_photos=get_path("chemins", "dossier_photos"),
            fichier_invites=get_path("chemins", "fichier_invites"),
            dossier_fonds=get_path("chemins", "dossier_fonds"),
            dossier_cadres=get_path("chemins", "dossier_cadres"),
            dossier_modeles=get_path("chemins", "dossier_modeles"),
            pm_decompte_entre_poses=get_int("photomaton", "decompte_entre_poses", 1, 10),
            pm_titre=get_str("photomaton", "titre"),
            pm_couleur_fond=get_color("photomaton", "couleur_fond"),
            pm_couleur_texte=get_color("photomaton", "couleur_texte"),
            gif_actif=get_bool("gif", "actif"),
            gif_limite_mo=get_int("gif", "limite_mo", 1, 50),
            gif_poses_espacees=get_int("gif", "poses_espacees", 2, 12),
            gif_poses_rafale=get_int("gif", "poses_rafale", 2, 20),
            gif_intervalle_rafale_ms=get_int("gif", "intervalle_rafale_ms", 80, 1000),
            gif_duree_image_ms=get_int("gif", "duree_image_ms", 80, 2000),
            gif_pause_derniere_image_ms=get_int("gif", "pause_derniere_image_ms", 300, 5000),
            qr_drive_actif=get_bool("qr_drive", "actif"),
            livre_or_actif=get_bool("livre_or", "actif"),
            defis_actifs=get_bool("defis", "actif"),
            sauvegarde_active=get_bool("sauvegarde", "actif"),
            dossier_sauvegarde=(paths.resolve(get_str("sauvegarde", "dossier"), base) if get_str("sauvegarde", "dossier") else None),
            dp_duree=get_int("diaporama", "duree", 2, 60),
            dp_ordre=ordre,
            fv_teinte_min=teinte_min,
            fv_teinte_max=teinte_max,
            fv_saturation_min=get_int("fond_vert", "saturation_min", 0, 255),
            fv_valeur_min=get_int("fond_vert", "valeur_min", 0, 255),
            fv_adoucissement=get_int("fond_vert", "adoucissement", 0, 10),
            fv_despill=get_bool("fond_vert", "despill"),
            mail_actif=get_bool("mail", "actif"),
            smtp_hote=get_str("mail", "smtp_hote"),
            smtp_port=get_int("mail", "smtp_port", 1, 65535),
            expediteur=get_str("mail", "expediteur"),
            mot_de_passe_application=get_str("mail", "mot_de_passe_application"),
            adresse_organisateur=get_str("mail", "adresse_organisateur"),
            mail_obligatoire=get_bool("mail", "obligatoire"),
            mail_utilisateur=get_str("mail", "utilisateur"),
            mail_securite=securite,
            mail_nom_expediteur=get_str("mail", "nom_expediteur") or DEFAULT_SENDER_NAME,
            mail_objet=get_str("mail", "objet") or DEFAULT_SUBJECT,
            mail_message=unescape_newlines(get_str("mail", "message")) or DEFAULT_BODY,
        )

    @staticmethod
    def _new_parser() -> configparser.ConfigParser:
        # interpolation=None : un « % » dans un mot de passe ne doit pas être interprété
        parser = configparser.ConfigParser(interpolation=None)
        parser.read_dict(DEFAULTS)
        return parser

    def reload(self) -> None:
        """Relit config.ini en place (les écrans gardent la même référence)."""
        fresh = Config.load(self.config_path, self.base_dir)
        self.__dict__.update(fresh.__dict__)

    def save_sound_settings(self, active: bool, volume: int) -> None:
        """Enregistre les réglages sonores en préservant le reste du fichier de configuration."""
        volume = max(0, min(100, int(volume)))
        lines = self.config_path.read_text(encoding="utf-8-sig").splitlines()
        section_start = next((index for index, line in enumerate(lines)
                              if re.match(r"^\s*\[general\]\s*(?:[;#].*)?$", line, re.IGNORECASE)), None)
        if section_start is None:
            lines.extend(["", "[general]"])
            section_start = len(lines) - 1
        section_end = next((index for index in range(section_start + 1, len(lines))
                            if re.match(r"^\s*\[[^\]]+\]", lines[index])), len(lines))
        updates = {"son_active": "true" if active else "false", "son_volume": str(volume)}
        found: set[str] = set()
        for index in range(section_start + 1, section_end):
            match = re.match(r"^(\s*)(son_active|son_volume)(\s*=).*$", lines[index], re.IGNORECASE)
            if match:
                key = match.group(2).lower()
                lines[index] = f"{match.group(1)}{key}{match.group(3)} {updates[key]}"
                found.add(key)
        insertion = section_end
        for key, value in updates.items():
            if key not in found:
                lines.insert(insertion, f"{key} = {value}")
                insertion += 1
        content = "\n".join(lines) + "\n"
        backup = self.config_path.with_suffix(".ini.bak")
        temporary = self.config_path.with_suffix(self.config_path.suffix + ".tmp")
        original = self.config_path.read_bytes()
        backup.write_bytes(original)
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, self.config_path)
        self.son_active = bool(active)
        self.son_volume = volume

    def save_activation_settings(self, settings: dict[tuple[str, str], bool]) -> None:
        """Met à jour les interrupteurs de fonctionnalités sans réécrire les autres réglages."""
        lines = self.config_path.read_text(encoding="utf-8-sig").splitlines()
        sections: dict[str, dict[str, str]] = {}
        for (section, key), value in settings.items():
            sections.setdefault(section, {})[key] = "true" if value else "false"

        for section, updates in sections.items():
            section_start = next((index for index, line in enumerate(lines)
                                  if re.match(rf"^\s*\[{re.escape(section)}\]\s*(?:[;#].*)?$", line, re.IGNORECASE)), None)
            if section_start is None:
                lines.extend(["", f"[{section}]"])
                section_start = len(lines) - 1
            section_end = next((index for index in range(section_start + 1, len(lines))
                                if re.match(r"^\s*\[[^\]]+\]", lines[index])), len(lines))
            found: set[str] = set()
            for index in range(section_start + 1, section_end):
                match = re.match(r"^(\s*)([^=:#\s]+)(\s*=).*$", lines[index])
                if match and match.group(2).lower() in updates:
                    key = match.group(2).lower()
                    lines[index] = f"{match.group(1)}{key}{match.group(3)} {updates[key]}"
                    found.add(key)
            insertion = section_end
            for key, value in updates.items():
                if key not in found:
                    lines.insert(insertion, f"{key} = {value}")
                    insertion += 1

        content = "\n".join(lines) + "\n"
        backup = self.config_path.with_suffix(".ini.bak")
        temporary = self.config_path.with_suffix(self.config_path.suffix + ".tmp")
        backup.write_bytes(self.config_path.read_bytes())
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, self.config_path)
        self.reload()

    def ensure_directories(self) -> None:
        """Crée les dossiers de travail, cadres, masques et thèmes par défaut."""
        self.dossier_logs.mkdir(parents=True, exist_ok=True)
        self.dossier_photos.mkdir(parents=True, exist_ok=True)
        self.dossier_modeles.mkdir(parents=True, exist_ok=True)
        self.dossier_donnees.mkdir(parents=True, exist_ok=True)
        if self.livre_or_actif:
            self.dossier_livre_or.mkdir(parents=True, exist_ok=True)
        self.dossier_cadres.mkdir(parents=True, exist_ok=True)
        self.dossier_masques.mkdir(parents=True, exist_ok=True)
        for folder in ("fonds", "cadres", "visuels", "sons"):
            (self.dossier_themes / "classique" / folder).mkdir(parents=True, exist_ok=True)
        if not self.dossier_fonds.exists():
            for theme in THEMES_PAR_DEFAUT:
                (self.dossier_fonds / theme).mkdir(parents=True, exist_ok=True)
            log.info("Dossier de fonds créé avec les thèmes par défaut : %s", self.dossier_fonds)


# ---------------------------------------------------------------- complétion de config.ini

_SECTION_RE = re.compile(r"^\s*\[([^\]]+)\]")


def _template_sections() -> dict[str, list[tuple[str | None, list[str]]]]:
    """Modèle découpé : section -> [(clé, lignes à écrire : commentaires qui précèdent + ligne de la clé)]."""
    sections: dict[str, list[tuple[str | None, list[str]]]] = {}
    current = None
    pending: list[str] = []
    for line in TEMPLATE.splitlines():
        header = _SECTION_RE.match(line)
        if header:
            current, pending = header.group(1).strip(), []
            sections[current] = []
            continue
        stripped = line.strip()
        if current is None:
            continue
        if not stripped:
            pending = []
        elif stripped.startswith("#"):
            pending.append(line)
        elif "=" in stripped:
            sections[current].append((stripped.split("=", 1)[0].strip().lower(), pending + [line]))
            pending = []
    return sections


def complete_missing(path: Path) -> list[str]:
    """Version sûre de _complete_missing : toute erreur imprévue est journalisée et le fichier reste intact."""
    try:
        return _complete_missing(path)
    except Exception:
        log.exception("Complétion de config.ini impossible : fichier laissé tel quel")
        return []


def _complete_missing(path: Path) -> list[str]:
    """Ajoute à config.ini les réglages (et sections) du modèle qui lui manquent, sans toucher à ce qui existe.

    Les valeurs, commentaires et lignes de l'utilisateur sont conservés tels quels ; chaque réglage manquant
    est inséré à la fin de sa section, avec son commentaire. L'ancienne version est gardée dans config.ini.bak.
    Renvoie la liste des ajouts (vide si rien à faire ou si le fichier est illisible : on n'y touche pas).
    """
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return []
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read_string(text)
    except configparser.Error:
        return []

    lines = text.splitlines()
    headers = [(i, m.group(1).strip()) for i, line in enumerate(lines) if (m := _SECTION_RE.match(line))]
    added: list[str] = []
    inserts: list[tuple[int, list[str]]] = []      # (position d'insertion, lignes)
    appended: list[str] = []

    for name, entries in _template_sections().items():
        if not parser.has_section(name):
            appended += ["", f"[{name}]"] + [line for _, block in entries for line in block]
            added.append(f"[{name}]")
            continue
        present = {key.lower() for key in parser[name]}
        missing = [(key, block) for key, block in entries if key not in present]
        if not missing:
            continue
        index = next((n for n, (_, header_name) in enumerate(headers) if header_name == name), None)
        if index is None:                       # en-tête que je ne sais pas localiser : on n'y touche pas
            continue
        start = headers[index][0]
        end = headers[index + 1][0] if index + 1 < len(headers) else len(lines)
        last_used = max((i for i in range(start, end) if lines[i].strip()), default=start)
        inserts.append((last_used + 1, [line for _, block in missing for line in block]))
        added += [f"{name}.{key}" for key, _ in missing]

    if not added:
        return []
    for position, block in sorted(inserts, reverse=True):      # de bas en haut : les positions restent valables
        lines[position:position] = block
    lines += appended
    try:
        path.with_suffix(".ini.bak").write_text(text, encoding="utf-8")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError:
        log.exception("config.ini n'a pas pu être complété")
        return []
    log.info("config.ini complété (%d ajout(s)) : %s", len(added), ", ".join(added))
    return added
